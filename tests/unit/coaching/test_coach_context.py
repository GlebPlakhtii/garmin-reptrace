from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

from reptrace.coaching.assistant import TrainingCoach, TrainingTools
from reptrace.telegram.bot import Bot
from tests.unit.reports.test_training_reports import records


def response(text):
    return {
        "status": "completed",
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": text}]}
        ],
    }


def history():
    return [
        {"role": role, "content": f"{role} message {number}"}
        for number in range(7)
        for role in ("user", "assistant")
    ]


class CoachContextTests(unittest.TestCase):
    def test_compaction_merges_summary_and_retains_recent_messages(self):
        original = history()
        state = {
            "coachHistory": deepcopy(original),
            "coachSummary": "Earlier: user trains at home.",
        }
        save = Mock()
        tools = TrainingTools(records(), state, save)
        coach = TrainingCoach("key")
        coach.request = Mock(
            side_effect=[
                response(
                    "User trains at home. Earlier question concerned bench progress."
                ),
                response("Current answer."),
            ]
        )
        coach.answer("What next?", tools, state["coachHistory"])
        self.assertEqual(state["coachHistory"], original[-8:])
        save.assert_called_once()
        self.assertIn("bench progress", state["coachSummary"])
        summary_request = coach.request.call_args_list[0].args[0]
        self.assertFalse(summary_request["store"])
        self.assertNotIn("tools", summary_request)
        payload = json.loads(summary_request["input"][0]["content"])
        self.assertEqual(payload["older_messages"], original[:-8])
        self.assertEqual(payload["earlier_summary"], "Earlier: user trains at home.")
        answer_request = coach.request.call_args_list[1].args[0]
        inputs = answer_request["input"]
        self.assertIn("historical data", inputs[0]["content"])
        self.assertIn("bench progress", inputs[0]["content"])
        self.assertEqual(inputs[1:-1], original[-8:])
        self.assertEqual(inputs[-1]["content"], "What next?")
        self.assertIn("tool results take precedence", answer_request["instructions"])

    def test_short_history_uses_saved_summary_without_resummarizing(self):
        state = {"coachSummary": "User temporarily has 30 minutes on 2026-10-23."}
        coach = TrainingCoach("key")
        coach.request = Mock(return_value=response("Answer."))
        coach.answer("Hi", TrainingTools(records(), state), history()[-4:])
        coach.request.assert_called_once()
        self.assertIn(
            "2026-10-23", coach.request.call_args.args[0]["input"][0]["content"]
        )

    def test_failed_summary_preserves_raw_history_and_uses_it_in_current_answer(self):
        original = history()
        state = {"coachHistory": deepcopy(original), "coachSummary": "Existing summary"}
        coach = TrainingCoach("key")
        coach.request = Mock(
            side_effect=[RuntimeError("unavailable"), response("Answer.")]
        )
        coach.answer("Question", TrainingTools(records(), state), state["coachHistory"])
        self.assertEqual(state["coachHistory"], original)
        self.assertEqual(state["coachSummary"], "Existing summary")
        inputs = coach.request.call_args.args[0]["input"]
        self.assertEqual(inputs[1:-1], original)

    def test_invalid_summary_does_not_overwrite_context(self):
        for summary in ("", "x" * 6001):
            state = {"coachHistory": history(), "coachSummary": "Keep me"}
            coach = TrainingCoach("key")
            coach.request = Mock(side_effect=[response(summary), response("Answer")])
            coach.answer(
                "Hello", TrainingTools(records(), state), state["coachHistory"]
            )
            self.assertEqual(state["coachSummary"], "Keep me")
            self.assertEqual(len(state["coachHistory"]), 14)

    def test_summary_persists_and_reset_clears_it_while_preserving_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            coach = TrainingCoach("key")
            coach.request = Mock(
                side_effect=[
                    response("Historical conversation summary"),
                    response("Answer"),
                ]
            )
            path = Path(directory) / "state.json"
            bot = Bot(api, lambda: [], path, "42", fetch_data=records, coach=coach)
            bot.state.update(
                coachHistory=history(), coachPreferences={"equipment": "home gym"}
            )
            bot.save()
            bot.handle_chat("What next?", "turn")
            bot = Bot(api, lambda: [], path, "42", fetch_data=records, coach=coach)
            self.assertEqual(
                bot.state["coachSummary"], "Historical conversation summary"
            )
            self.assertEqual(len(bot.state["coachHistory"]), 10)
            self.assertFalse(bot.state["chatOutbox"])

            def command(text):
                bot.handle(
                    {
                        "update_id": 100,
                        "message": {
                            "from": {"id": 42},
                            "chat": {"id": 42, "type": "private"},
                            "text": text,
                        },
                    }
                )

            command("/memory")
            self.assertIn(
                "Historical conversation summary", api.call.call_args.args[1]["text"]
            )
            command("/reset")
            saved = json.loads(path.read_text())
            self.assertNotIn("coachSummary", saved)
            self.assertEqual(saved["coachHistory"], [])
            self.assertEqual(saved["coachPreferences"], {"equipment": "home gym"})

    def test_forgetting_memory_also_discards_summary(self):
        for target in ("all", "equipment"):
            state = {
                "coachSummary": "User uses a home gym",
                "coachHistory": history(),
                "coachPreferences": {"equipment": "home gym"},
            }
            tools = TrainingTools(records(), state, allow_memory=True)
            tools.call("forget_memory", {"key_or_id": target})
            self.assertNotIn("coachSummary", state)
            self.assertEqual(state["coachHistory"], [])
