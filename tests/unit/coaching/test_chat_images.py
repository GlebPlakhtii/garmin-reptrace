import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

from reptrace.telegram.bot import Bot
from reptrace.coaching.assistant import TrainingCoach, TrainingTools


class ChatImageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.api = Mock()
        self.api.download_photo.side_effect = lambda identity: (
            identity.encode(),
            "image/jpeg",
        )
        self.coach = Mock(configured=True)
        self.coach.answer.return_value = {
            "text": "Here is the chart analysis.",
            "artifacts": [],
        }
        self.food = Mock()
        self.food.estimate.return_value = None
        self.now = datetime(2026, 10, 25, tzinfo=timezone.utc)
        self.bot = self.make_bot()

    def make_bot(self):
        return Bot(
            self.api,
            lambda: [],
            self.path,
            "42",
            fetch_data=lambda: {},
            coach=self.coach,
            food_estimator=self.food,
            clock=lambda: self.now,
        )

    def image(self, identity=1, caption="Explain this chart", **extra):
        return {
            "update_id": identity,
            "message": {
                "message_id": identity,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "photo": [{"file_id": "chart"}],
                "caption": caption,
                **extra,
            },
        }

    def test_non_food_image_reaches_coach_and_persists_only_references(self):
        self.bot.handle(self.image())
        self.assertEqual(self.coach.answer.call_args.args[0], "Explain this chart")
        self.assertEqual(
            self.coach.answer.call_args.kwargs["images"], [(b"chart", "image/jpeg")]
        )
        self.food.estimate.assert_not_called()
        self.api.download_photo.assert_called_once_with("chart")
        state = json.loads(self.path.read_text())
        self.assertEqual(
            state["coachHistory"][0]["imageSources"],
            [{"photo": [{"file_id": "chart"}]}],
        )
        self.assertNotIn("base64", self.path.read_text())
        self.assertFalse(state.get("pendingFood"))

    def test_ask_caption_bypasses_food_even_for_a_food_image(self):
        self.bot.handle(self.image(caption="/ask Compare these nutrition labels"))
        self.food.estimate.assert_not_called()
        self.coach.answer.assert_called_once()

    def test_captionless_non_food_photo_and_image_document_work(self):
        value = self.image(caption="")
        value["message"].pop("photo")
        value["message"]["document"] = {
            "file_id": "screenshot",
            "mime_type": "image/png",
        }
        self.bot.handle(value)
        self.assertEqual(
            self.coach.answer.call_args.kwargs["images"], [(b"screenshot", "image/png")]
        )
        self.assertIn("without a caption", self.coach.answer.call_args.args[0])

    def test_plain_text_also_goes_directly_to_model_for_tool_selection(self):
        value = self.image()
        value["message"].pop("photo")
        value["message"]["text"] = "3 bananas"
        self.bot.handle(value)
        self.coach.answer.assert_called_once()
        self.food.estimate.assert_not_called()
        self.assertEqual(self.coach.answer.call_args.args[0], "3 bananas")

    def test_model_selects_food_tool_and_preview_still_requires_save(self):
        from tests.unit.nutrition.test_food_log import SAMPLE

        self.food.estimate.return_value = SAMPLE

        def answer(message, tools, *args, **kwargs):
            result = tools.call(
                "propose_food_entry", {"description": "3 bananas", "revision_id": None}
            )
            self.assertFalse(result["saved"])
            return {
                "text": "Review the food estimate below.",
                "artifacts": tools.artifacts,
            }

        self.coach.answer.side_effect = answer
        value = self.image(caption="3 bananas")
        self.bot.handle(value)
        draft = next(iter(self.bot.state["pendingFood"].values()))
        self.assertEqual(draft["status"], "pending")
        self.assertEqual(draft["sources"], [{"photo": [{"file_id": "chart"}]}])
        self.assertIn("Save food entry", str(self.api.call.call_args_list))
        self.assertEqual(self.coach.answer.call_count, 1)
        self.food.estimate.assert_called_once()
        self.api.download_photo.assert_called_once_with("chart")

    def test_model_can_question_a_food_preview_without_revising_it(self):
        from tests.unit.nutrition.test_food_log import SAMPLE

        self.food.estimate.return_value = SAMPLE
        self.api.call.return_value = {"message_id": 100}
        self.bot.handle_food("3 bananas", "original", {})
        self.food.estimate.reset_mock()
        self.coach.answer.reset_mock()
        value = self.image()
        value["message"].pop("photo")
        value["message"].update(
            text="Why this many calories?", reply_to_message={"message_id": 100}
        )
        self.bot.handle(value)
        self.coach.answer.assert_called_once()
        self.food.estimate.assert_not_called()
        self.assertEqual(len(self.bot.state["pendingFood"]), 1)

    def test_model_resolves_natural_food_correction_with_tools(self):
        from tests.unit.nutrition.test_food_log import SAMPLE

        self.food.estimate.return_value = SAMPLE
        self.bot.handle_food("3 bananas", "original", {"photo": [{"file_id": "meal"}]})
        original = next(iter(self.bot.state["pendingFood"]))

        def answer(message, tools, *args, **kwargs):
            drafts = tools.call("get_food_drafts", {})["drafts"]
            self.assertEqual(drafts[0]["id"], original)
            result = tools.call(
                "propose_food_entry",
                {"description": "only half of that", "revision_id": original},
            )
            self.assertFalse(result["saved"])
            return {"text": "Revised estimate below.", "artifacts": tools.artifacts}

        self.coach.answer.side_effect = answer
        value = self.image(2)
        value["message"].pop("photo")
        value["message"]["text"] = "Actually only half of that"
        self.bot.handle(value)
        self.assertEqual(
            self.bot.state["pendingFood"][original]["status"], "superseded"
        )
        self.assertEqual(
            self.food.estimate.call_args.kwargs["images"], [(b"meal", "image/jpeg")]
        )

    def test_album_survives_restart_and_reaches_coach_as_one_request(self):
        self.bot.handle(self.image(media_group_id="charts"))
        value = self.image(2, caption="", media_group_id="charts")
        value["message"]["photo"] = [{"file_id": "second"}]
        self.bot.handle(value)
        self.coach.answer.assert_not_called()
        self.now += timedelta(seconds=3)
        self.make_bot().flush_food_albums()
        self.coach.answer.assert_called_once()
        self.assertEqual(
            self.coach.answer.call_args.kwargs["images"],
            [(b"chart", "image/jpeg"), (b"second", "image/jpeg")],
        )
        self.assertFalse(json.loads(self.path.read_text())["foodAlbums"])

    def test_text_followup_reloads_image_after_restart_and_reset_clears_it(self):
        self.bot.handle(self.image())
        self.coach.answer.reset_mock()
        bot = self.make_bot()
        value = self.image(2)
        value["message"].pop("photo")
        value["message"]["text"] = "/ask What does the red line mean?"
        bot.handle(value)
        self.assertEqual(
            self.coach.answer.call_args.kwargs["images"], [(b"chart", "image/jpeg")]
        )
        self.assertIn("earlier message", self.coach.answer.call_args.args[0])
        value["message"]["text"] = "/reset"
        bot.handle(value)
        self.coach.answer.reset_mock()
        value["message"]["text"] = "/ask What now?"
        bot.handle(value)
        self.assertNotIn("images", self.coach.answer.call_args.kwargs)

    def test_incomplete_album_does_not_reach_either_model(self):
        self.api.download_photo.side_effect = [
            (b"chart", "image/jpeg"),
            RuntimeError("Image unavailable"),
        ]
        self.bot.handle_images(
            "Explain these",
            "album",
            [
                self.image()["message"],
                {**self.image()["message"], "photo": [{"file_id": "second"}]},
            ],
        )
        self.food.estimate.assert_not_called()
        self.coach.answer.assert_not_called()

    def test_responses_request_contains_images_through_tool_roundtrip(self):
        coach = TrainingCoach("key", "gpt-6-sol")
        coach.request = Mock(
            side_effect=[
                {
                    "output": [
                        {
                            "type": "function_call",
                            "name": "get_training_overview",
                            "arguments": "{}",
                            "call_id": "overview",
                        }
                    ]
                },
                {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {"type": "output_text", "text": "Chart explained."}
                            ],
                        }
                    ]
                },
            ]
        )
        tools = TrainingTools({}, {})
        tools.call = Mock(return_value={"workouts": 3})
        coach.answer(
            "Explain this chart",
            tools,
            images=[(b"chart", "image/png"), (b"second", "image/jpeg")],
        )
        for call in coach.request.call_args_list:
            body = call.args[0]
            self.assertFalse(body["store"])
            content = body["input"][0]["content"]
            self.assertEqual(content[0]["text"], "Explain this chart")
            self.assertEqual(content[1]["image_url"], "data:image/png;base64,Y2hhcnQ=")
            self.assertEqual(content[2]["type"], "input_image")


if __name__ == "__main__":
    unittest.main()
