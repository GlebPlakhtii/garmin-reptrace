from copy import deepcopy
from datetime import date
from pathlib import Path
import json, sys, tempfile, unittest
from unittest.mock import Mock

from reptrace.coaching.assistant import (
    TrainingTools,
    TrainingCoach,
    quality_review,
    TOOLS,
)
from reptrace.training.planning import build_next_sessions
from reptrace.telegram.bot import Bot
from tests.unit.reports.test_training_reports import records, row, workout


class CoachToolsTests(unittest.TestCase):
    def tools(self, allow=False):
        return TrainingTools(
            records(),
            {},
            today=date(2026, 10, 22),
            request_id="test-turn",
            allow_memory=allow,
        )

    def test_history_returns_actual_totals_and_missing_values(self):
        tools = self.tools()
        result = tools.call(
            "get_exercise_history",
            {
                "exercise": "Barbell Bench Press",
                "from_date": None,
                "to_date": None,
                "limit": 2,
            },
        )
        self.assertEqual(result["sessionCount"], 3)
        self.assertEqual(result["sessions"][0]["date"], "2026-10-20")
        self.assertEqual(result["sessions"][0]["totals"]["volumeKgReps"], 850)
        tools.data["sets"][-1]["reps"] = None
        tools.data["sets"][-1]["volume"] = None
        result = tools.call(
            "get_exercise_history",
            {
                "exercise": "Barbell Bench Press",
                "from_date": "2026-10-20",
                "to_date": "2026-10-20",
                "limit": 2,
            },
        )
        self.assertIsNone(result["sessions"][0]["totals"]["reps"])

    def test_preferences_need_explicit_memory_intent_and_forgetting_is_supported(self):
        tools = self.tools()
        with self.assertRaises(ValueError):
            tools.call("remember_preference", {"key": "session_minutes", "value": "40"})
        tools.allow_memory = True
        tools.call("remember_preference", {"key": "session_minutes", "value": "40"})
        self.assertEqual(tools.preferences()["preferences"]["session_minutes"], "40")
        tools.call("remember_fact", {"fact": "Dumbbell weights are per hand."})
        tools.call("remember_fact", {"fact": "Dumbbell weights are per hand."})
        self.assertEqual(len(tools.preferences()["memory"]), 1)
        tools.call("forget_memory", {"key_or_id": "all"})
        self.assertEqual(tools.preferences(), {"preferences": {}, "memory": []})

    def test_shared_progression_rules_validate_and_keep_request_identity(self):
        tools = self.tools(True)
        tools.save_action = Mock(return_value={"ok": True})
        args = {
            "exercise": "Barbell Bench Press",
            "rep_min": 6,
            "rep_max": 10,
            "weight_step": 2.5,
        }
        tools.call("set_progression_rule", args)
        tools.call("set_progression_rule", args)
        self.assertEqual(
            tools.save_action.call_args_list[0].args[0]["requestId"],
            tools.save_action.call_args_list[1].args[0]["requestId"],
        )
        self.assertEqual(
            tools.data["progressionRules"]["Barbell Bench Press"]["repMax"], 10
        )
        with self.assertRaises(ValueError):
            tools.call("set_progression_rule", dict(args, rep_min=12))

    def test_adaptation_is_a_separate_time_bounded_proposal(self):
        data = records()
        data["sets"] += [
            row(
                "c",
                "2026-10-20",
                exercise="Cable Biceps Curl",
                order=i + 2,
                id="curl" + str(i),
            )
            for i in range(5)
        ]
        before = deepcopy(data)
        tools = TrainingTools(data, {}, today=date(2026, 10, 22), request_id="adapt")
        plan = tools.call(
            "adapt_workout",
            {
                "workout_type": "upper1",
                "time_minutes": 10,
                "unavailable_exercises": [],
                "substitutions": [],
                "notes": "Today only",
            },
        )
        self.assertTrue(plan["adapted"])
        self.assertEqual(data, before)
        self.assertEqual(tools.preferences()["preferences"], {})
        self.assertLessEqual(plan["adaptation"]["estimatedMinutes"], 10)
        self.assertEqual(len(tools.state["adaptedPlans"]), 1)
        self.assertEqual(len(tools.artifacts), 1)

    def test_substitution_uses_replacement_history_not_equivalent_load(self):
        data = records()
        data["sets"].append(
            row("b", "2026-10-13", 22, 9, exercise="Incline Dumbbell Bench Press")
        )
        tools = TrainingTools(data, {}, today=date(2026, 10, 22))
        p = tools.call(
            "adapt_workout",
            {
                "workout_type": "upper1",
                "time_minutes": None,
                "unavailable_exercises": ["Barbell Bench Press"],
                "substitutions": [
                    {
                        "from_exercise": "Barbell Bench Press",
                        "to_exercise": "Incline Dumbbell Bench Press",
                    }
                ],
                "notes": "",
            },
        )
        self.assertEqual(p["exercises"][0]["proposed"][0]["weight"], 22)

    def test_quality_review_never_treats_repeated_sets_as_duplicate_workouts(self):
        data = records()
        data["sets"].append(deepcopy(data["sets"][-1]))
        before = deepcopy(data)
        result = quality_review(data)
        self.assertFalse(
            any(r["kind"] == "possible_duplicate_workouts" for r in result["flags"])
        )
        self.assertEqual(data, before)
        data["sets"].append(row("c", "2026-10-20", weight=None, reps=None))
        self.assertTrue(
            any(r["kind"] == "missing_load" for r in quality_review(data)["flags"])
        )

    def test_tool_schemas_are_strict_and_do_not_expose_arbitrary_sql_or_shell(self):
        for tool in TOOLS:
            self.assertTrue(tool["strict"])
            self.assertFalse(tool["parameters"]["additionalProperties"])
            self.assertEqual(
                set(tool["parameters"]["required"]),
                set(tool["parameters"]["properties"]),
            )
        self.assertFalse(any("sql" in t["name"] or "shell" in t["name"] for t in TOOLS))

    def test_database_tools_route_to_service_and_feed_all_time_record_to_model(self):
        tools = self.tools()
        tools.database = Mock(
            return_value={
                "rows": [{"time": "2020-01-01T00:00:00Z", "value": 154}],
                "truncated": False,
            }
        )
        tools.call("get_database_schema", {"table": None})
        tools.database.assert_called_with("schema", table=None)
        args = {
            "table": "HRV_Intraday",
            "fields": ["hrvValue"],
            "aggregate": "max",
            "from_time": None,
            "to_time": None,
            "filters": [],
            "order": "desc",
            "limit": 1,
            "offset": 0,
        }
        coach = TrainingCoach("key", "gpt-6-sol")
        coach.request = Mock(
            side_effect=[
                {
                    "output": [
                        {
                            "type": "function_call",
                            "name": "query_database",
                            "arguments": json.dumps(args),
                            "call_id": "hrv1",
                        }
                    ]
                },
                {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "Highest individual HRV: 154 ms on 2020-01-01.",
                                }
                            ],
                        }
                    ]
                },
            ]
        )
        self.assertIn("154", coach.answer("Max HRV ever?", tools)["text"])
        tools.database.assert_called_with("query", **args)
        response = next(
            r
            for r in coach.request.call_args_list[1].args[0]["input"]
            if r.get("type") == "function_call_output"
        )
        self.assertEqual(json.loads(response["output"])["rows"][0]["value"], 154)
        tools.database = None
        with self.assertRaises(ValueError):
            tools.call("get_database_schema", {"table": None})

    def test_custom_html_report_is_uploaded_as_file_and_not_pasted_into_chat(self):
        tools = self.tools()
        coach = TrainingCoach("key", "gpt-6-sol")
        args = {
            "title": "Cycling progress",
            "filename": "cycling-2026.html",
            "html": '<html><h1>Cycling</h1><svg viewBox="0 0 100 50"><path d="M0 50L100 0"/></svg></html>',
        }
        coach.request = Mock(
            side_effect=[
                {
                    "output": [
                        {
                            "type": "function_call",
                            "name": "create_html_report",
                            "arguments": json.dumps(args),
                            "call_id": "html",
                        }
                    ]
                },
                {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "Your cycling report follows as an HTML file.",
                                }
                            ],
                        }
                    ]
                },
            ]
        )
        result = coach.answer("Send the cycling graphs as an HTML file", tools)
        self.assertEqual(result["artifacts"][0]["filename"], "cycling-2026.html")
        self.assertIn("Content-Security-Policy", result["artifacts"][0]["html"])
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            fake_coach = Mock(configured=True)
            fake_coach.answer.return_value = result
            bot = Bot(
                api,
                lambda: [],
                Path(directory) / "state.json",
                "42",
                fetch_data=records,
                coach=fake_coach,
            )
            bot.handle_chat("Send HTML as file", "html")
            message = api.call.call_args_list[0]
            self.assertNotIn("<svg", message.args[1]["text"])
            sent = api.call.call_args_list[-1]
            self.assertEqual(sent.args[0], "sendDocument")
            self.assertEqual(sent.kwargs["filename"], "cycling-2026.html")
            self.assertIn(b"<svg", sent.kwargs["document"])
            self.assertFalse(bot.state["chatOutbox"])

    def test_custom_html_validates_filename_size_and_retains_attachment_on_retry(self):
        tools = self.tools()
        args = {"title": "Report", "filename": "report.html", "html": "<h1>Report</h1>"}
        for invalid in [
            dict(filename="../report.html"),
            dict(filename="report.html\r\n"),
            dict(filename="report.txt"),
            dict(html="x" * 200001),
            dict(title=""),
        ]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                tools.call("create_html_report", args | invalid)
        tools.call("create_html_report", args)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            api = Mock()
            coach = Mock(configured=True)
            coach.answer.return_value = {
                "text": "Report follows.",
                "artifacts": tools.artifacts,
            }
            api.call.side_effect = [{}, RuntimeError("upload failed")]
            bot = Bot(api, lambda: [], path, "42", fetch_data=records, coach=coach)
            with self.assertRaises(RuntimeError):
                bot.handle_chat("Create report", "retry")
            self.assertEqual(bot.state["chatOutbox"]["retry"]["next"], 1)
            api.call.side_effect = None
            restarted = Bot(
                api, lambda: [], path, "42", fetch_data=records, coach=coach
            )
            restarted.handle_chat("Create report", "retry")
            coach.answer.assert_called_once()
            self.assertEqual(api.call.call_args.args[0], "sendDocument")
            self.assertFalse(restarted.state["chatOutbox"])

    def test_bulk_extrema_queues_full_report_and_finishes_in_one_tool_call(self):
        tools = self.tools()
        report = {
            "metrics": [
                {
                    "table": "HRV_Intraday",
                    "field": "hrvValue",
                    "min": 18,
                    "max": 175,
                    "count": 1000,
                }
            ],
            "metricCount": 1,
            "fromTime": None,
            "toTime": None,
            "failedTables": [],
            "excludedTables": [],
            "notes": "Raw units.",
        }
        tools.database = Mock(return_value=report)
        coach = TrainingCoach("key", "gpt-6-sol")
        coach.request = Mock(
            side_effect=[
                {
                    "output": [
                        {
                            "type": "function_call",
                            "name": "get_database_extrema",
                            "arguments": '{"from_time":null,"to_time":null}',
                            "call_id": "stats",
                        }
                    ]
                },
                {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "HRV ranges from 18 to 175 ms. Complete report attached.",
                                }
                            ],
                        }
                    ]
                },
            ]
        )
        result = coach.answer("For all useful metrics give max and min", tools)
        tools.database.assert_called_once_with("extrema", from_time=None, to_time=None)
        self.assertEqual(
            result["artifacts"], [{"kind": "database_extrema", "report": report}]
        )
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            fake_coach = Mock(configured=True)
            fake_coach.answer.return_value = result
            bot = Bot(
                api,
                lambda: [],
                Path(directory) / "state.json",
                "42",
                fetch_data=records,
                coach=fake_coach,
            )
            bot.handle_chat("All metrics", "stats")
            self.assertEqual(api.call.call_args.args[0], "sendDocument")
            self.assertIn(b"175", api.call.call_args.kwargs["document"])

    def test_tool_budget_reserves_final_answer_instead_of_discarding_results(self):
        calls = [
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "get_training_overview",
                        "arguments": "{}",
                        "call_id": "c" + str(i),
                    }
                ]
            }
            for i in range(9)
        ]
        coach = TrainingCoach("key", "gpt-6-sol")
        coach.request = Mock(
            side_effect=calls
            + [
                {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "Here are the results checked so far.",
                                }
                            ],
                        }
                    ]
                }
            ]
        )
        self.assertIn(
            "results", coach.answer("Analyze everything", self.tools())["text"]
        )
        self.assertEqual(coach.request.call_args.args[0]["tool_choice"], "none")

    def test_tool_roundtrip_feeds_calculated_results_back_to_model(self):
        coach = TrainingCoach("key", "gpt-6-sol")
        coach.request = Mock(
            side_effect=[
                {
                    "output": [
                        {
                            "type": "function_call",
                            "name": "get_training_overview",
                            "arguments": "{}",
                            "call_id": "call1",
                            "id": "fc1",
                            "status": "completed",
                        }
                    ]
                },
                {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "Three workouts are recorded.",
                                }
                            ],
                        }
                    ]
                },
            ]
        )
        result = coach.answer("How many workouts?", self.tools())
        self.assertEqual(result["text"], "Three workouts are recorded.")
        inputs = coach.request.call_args_list[1].args[0]["input"]
        answer = next(r for r in inputs if r.get("type") == "function_call_output")
        self.assertEqual(json.loads(answer["output"])["workouts"], 3)


class CoachBotTests(unittest.TestCase):
    def test_owner_guard_chat_delivery_and_conversation_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            coach = Mock(configured=True)
            coach.answer.return_value = {"text": "Your bench history.", "artifacts": []}
            api = Mock()
            path = Path(directory) / "state.json"
            database = Mock()
            bot = Bot(
                api,
                lambda: [],
                path,
                "42",
                fetch_data=records,
                coach=coach,
                database=database,
            )

            def message(sender):
                return {
                    "update_id": 4,
                    "message": {
                        "from": {"id": sender},
                        "chat": {"id": sender, "type": "private"},
                        "text": "How is my bench?",
                    },
                }

            bot.handle(message(9))
            coach.answer.assert_not_called()
            bot.handle(message(42))
            coach.answer.assert_called_once()
            self.assertIs(coach.answer.call_args.args[1].database, database)
            self.assertEqual(
                json.loads(path.read_text())["coachHistory"][0]["content"],
                "How is my bench?",
            )

    def test_monthly_command_and_quality_are_owner_only(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            bot = Bot(
                api,
                lambda: [],
                Path(directory) / "state.json",
                "42",
                fetch_data=records,
            )
            bot.handle(
                {
                    "update_id": 5,
                    "message": {
                        "from": {"id": 42},
                        "chat": {"id": 42, "type": "private"},
                        "text": "/quality",
                    },
                }
            )
            self.assertEqual(api.call.call_args.args[0], "sendDocument")
            self.assertIn(b"Review candidates", api.call.call_args.kwargs["document"])


if __name__ == "__main__":
    unittest.main()
