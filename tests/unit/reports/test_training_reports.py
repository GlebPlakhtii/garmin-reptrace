from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import copy, json, sys, tempfile, unittest
from unittest.mock import Mock, patch

from reptrace.reports.facts import (
    weekly_facts,
    weekly_text,
    session_facts,
    ReportWriter,
)
from reptrace.telegram.bot import Bot, split_text


def workout(identity, day):
    return {
        "id": identity,
        "name": "Upper 1",
        "date": day,
        "time": day + "T10:00:00Z",
        "duration": 3600,
        "dateOnly": False,
        "averageHR": 120,
        "maxHR": 155,
        "calories": 300,
    }


def row(identity, day, weight=80, reps=10, **extra):
    return {
        "id": identity + ":1",
        "sessionId": identity,
        "exercise": "Barbell Bench Press",
        "date": day,
        "weight": weight,
        "reps": reps,
        "volume": weight * reps if weight is not None and reps is not None else None,
        "order": 1,
        **extra,
    }


def records():
    return {
        "workouts": [
            workout("a", "2026-10-11"),
            workout("b", "2026-10-13"),
            workout("c", "2026-10-20"),
        ],
        "sets": [
            row("a", "2026-10-11"),
            row("b", "2026-10-13", reps=11),
            row("c", "2026-10-20", 85),
        ],
        "recovery": [
            {"date": "2026-10-13", "sleepHours": 7, "hrv": 50, "restingHR": 49}
        ],
        "goals": [],
        "nextSessions": [],
    }


class ReportMathTests(unittest.TestCase):
    def test_previous_full_week_excludes_current_and_counts_actual_same_load_progress(
        self,
    ):
        facts = weekly_facts(records(), "2026-10-21")
        self.assertEqual((facts["from"], facts["to"]), ("2026-10-12", "2026-10-18"))
        self.assertEqual(facts["current"]["workouts"], 1)
        self.assertEqual(facts["current"]["sets"], 1)
        self.assertEqual(facts["sameLoadRepRecords"][0]["after"], 11)
        self.assertEqual(facts["loadRecords"], [])
        self.assertEqual(facts["current"]["recovery"]["hrv"]["days"], 1)

    def test_first_record_is_not_claimed_as_an_all_time_record_and_missing_values_stay_missing(
        self,
    ):
        data = records()
        data["sets"] = [row("b", "2026-10-13", weight=None, reps=None)]
        facts = weekly_facts(data, "2026-10-21")
        self.assertEqual(facts["loadRecords"], [])
        self.assertIsNone(facts["current"]["volume"])
        self.assertEqual(facts["current"]["volumeKnown"], 0)
        self.assertIn("First recorded appearances", weekly_text(facts))

    def test_year_boundary_week_and_unidentified_exercise_exclusion(self):
        facts = weekly_facts({"sets": [], "workouts": []}, "2027-01-04")
        self.assertEqual((facts["from"], facts["to"]), ("2026-12-28", "2027-01-03"))
        data = records()
        data["sets"].append(row("b", "2026-10-13", exercise="Unknown"))
        self.assertEqual(weekly_facts(data, "2026-10-21")["current"]["sets"], 1)

    def test_llm_context_keeps_all_available_categories_but_excludes_record_identifiers(
        self,
    ):
        data = records()
        facts = session_facts(data, "c")
        self.assertEqual(facts["workout"]["averageHR"], 120)
        self.assertEqual(
            facts["exercises"][0]["priorSameType"][0]["sets"][0]["reps"], 11
        )
        self.assertIsNone(facts["sameDayRecovery"])
        self.assertEqual(facts["effortRIR"], "not recorded")
        self.assertNotIn("sessionId", json.dumps(facts))
        self.assertNotIn("revision", json.dumps(facts))

    def test_load_increase_is_not_confused_with_rep_or_top_set_volume_increase(self):
        facts = session_facts(records(), "c")
        comparison = facts["exercises"][0]["comparisonToPrevious"]
        self.assertEqual(comparison["topLoadChange"], 5)
        self.assertEqual(comparison["repChange"], -1)
        self.assertEqual(comparison["volumeChange"], -30)
        self.assertEqual(comparison["before"]["topSet"]["reps"], 11)
        self.assertEqual(comparison["after"]["topSet"]["reps"], 10)

    def test_openai_request_is_stateless_and_parses_message_output(self):
        result = {
            "status": "completed",
            "output": [
                {"type": "reasoning"},
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Useful report."}],
                },
            ],
        }
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps(result).encode()
        with patch("urllib.request.urlopen", return_value=response) as request:
            self.assertEqual(
                ReportWriter("private-key").write({"sets": 3}), "Useful report."
            )
            body = json.loads(request.call_args.args[0].data)
            self.assertFalse(body["store"])
            self.assertEqual(body["model"], "gpt-6-sol")
            self.assertNotIn("private-key", body["input"])
            self.assertEqual(body["reasoning"]["effort"], "medium")
        with patch("urllib.request.urlopen", side_effect=OSError("private-key")):
            with self.assertRaises(RuntimeError) as caught:
                ReportWriter("private-key").write({})
            self.assertNotIn("private-key", str(caught.exception))


class ReportDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "state.json"
        self.now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
        self.data = records()
        self.api = Mock()
        self.fetch = Mock(side_effect=lambda: copy.deepcopy(self.data))
        self.writer = Mock(configured=True, model="test-model")
        self.writer.write.return_value = "Analysis."

    def tearDown(self):
        self.directory.cleanup()

    def bot(self, **options):
        return Bot(
            self.api,
            lambda: [],
            self.path,
            "42",
            fetch_data=self.fetch,
            reporter=self.writer,
            clock=lambda: self.now,
            **options,
        )

    def test_garmin_plan_review_is_in_after_workout_facts(self):
        self.data["workouts"][-1]["source"] = "garmin"
        review = Mock(
            return_value={
                "name": "Upper 1",
                "source": "current_template",
                "plannedSets": [
                    {"exercise": "Barbell Bench Press", "weight": 85, "reps": 10}
                ],
            }
        )
        facts = self.bot(garmin_review=review).session_report_facts(self.data, "c")
        self.assertEqual(facts["planReview"]["counts"]["matched"], 1)
        review.assert_called_once_with(
            {
                "operation": "review",
                "workoutName": "Upper 1",
                "sessionTime": "2026-10-20T10:00:00Z",
            }
        )

    def test_monday_time_observes_kyiv_clock_change_and_survives_restart(self):
        bot = self.bot(post_enabled=False)
        bot.run_reports(force=True)
        self.api.call.assert_not_called()
        self.now = datetime(2026, 10, 26, 6, 59, tzinfo=timezone.utc)
        bot.run_reports(force=True)
        self.api.call.assert_not_called()
        self.now += timedelta(minutes=1)
        bot.run_reports(force=True)
        self.assertTrue(self.api.call.called)
        self.assertEqual(bot.state["weeklyLastSent"], "2026-10-25")
        self.api.reset_mock()
        self.bot(post_enabled=False).run_reports(force=True)
        self.api.call.assert_not_called()

    def test_existing_history_is_not_flooded_and_new_workout_waits_for_stable_data(
        self,
    ):
        bot = self.bot(weekly_enabled=False)
        bot.run_reports(force=True)
        self.writer.write.assert_not_called()
        self.data["workouts"].append(workout("new", "2026-10-21"))
        self.data["sets"].append(row("new", "2026-10-21"))
        bot.run_reports(force=True)
        self.writer.write.assert_not_called()
        self.now += timedelta(minutes=4)
        bot.run_reports(force=True)
        self.writer.write.assert_not_called()
        self.data["sets"][-1]["reps"] = 12
        bot.run_reports(force=True)
        self.now += timedelta(minutes=5)
        bot.run_reports(force=True)
        self.writer.write.assert_called_once()
        self.assertIn("new", bot.state["workoutReportsSent"])
        self.writer.reset_mock()
        self.bot(weekly_enabled=False).run_reports(force=True)
        self.writer.write.assert_not_called()

    def test_weekly_delivery_catches_up_after_downtime_without_sending_every_missed_week(
        self,
    ):
        bot = self.bot(post_enabled=False)
        self.now = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
        bot.run_reports(force=True)
        self.assertEqual(bot.state["weeklyLastSent"], "2026-11-01")

    def test_outbox_retries_only_the_remaining_parts(self):
        bot = self.bot()
        text = "a" * 3500 + "\n" + "remaining"
        self.api.call.side_effect = [{}, RuntimeError("offline")]
        with self.assertRaises(RuntimeError):
            bot.deliver("test", text)
        self.assertEqual(bot.state["reportOutbox"]["test"]["next"], 1)
        self.api.call.side_effect = None
        self.api.reset_mock()
        self.bot().deliver("test")
        self.api.call.assert_called_once()
        self.assertEqual(self.api.call.call_args.args[1]["text"], "remaining")

    def test_owner_only_can_request_manual_reports(self):
        bot = self.bot()
        value = {
            "update_id": 3,
            "message": {
                "from": {"id": 11},
                "chat": {"id": 11, "type": "private"},
                "text": "/report",
            },
        }
        bot.handle(value)
        self.fetch.assert_not_called()
        value["message"]["from"]["id"] = 42
        value["message"]["chat"]["id"] = 42
        bot.handle(value)
        self.writer.write.assert_called_once()
        self.assertEqual(self.api.call.call_args.args[1]["chat_id"], 42)

    def test_split_text_keeps_each_message_bounded(self):
        parts = split_text(("workout stats\n" * 1000))
        self.assertTrue(all(len(p) <= 3500 for p in parts))


if __name__ == "__main__":
    unittest.main()
