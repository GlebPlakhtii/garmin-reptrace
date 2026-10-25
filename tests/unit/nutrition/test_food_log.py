import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import Mock, patch

from reptrace.nutrition.estimation import FoodEstimator
from reptrace.telegram.bot import Bot
from reptrace.storage.state import WebState


SAMPLE = {
    "name": "Three bananas",
    "items": [{"name": "Banana", "portion": "3 medium"}],
    "calories": 315,
    "protein_g": 3.9,
    "carbs_g": 81,
    "fat_g": 1.2,
    "note": "Size is estimated.",
}


class FoodTests(unittest.TestCase):
    def test_storage_is_idempotent_and_deletable(self):
        with tempfile.TemporaryDirectory() as directory:
            state = WebState(Path(directory) / "state.sqlite")
            identity = str(uuid.uuid4())
            body = {
                "action": "add",
                "id": identity,
                "time": datetime.now(timezone.utc).isoformat(),
                "description": "3 bananas",
                **SAMPLE,
            }
            first = state.food_action(body)["entry"]
            self.assertEqual(first["calories"], 315)
            self.assertEqual(state.food_action(body)["entry"], first)
            self.assertEqual(len(state.food_entries()), 1)
            self.assertEqual(len(state.export_records()["FoodLog"]), 1)
            state.food_action({"action": "delete", "id": identity})
            self.assertEqual(state.food_entries(), [])
            with self.assertRaises(ValueError):
                state.food_action({**body, "id": str(uuid.uuid4()), "calories": -1})

    def test_estimator_sends_image_and_hand_scale_instruction(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps(
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps({"is_food": True, **SAMPLE}),
                            }
                        ],
                    }
                ],
            }
        ).encode()
        with patch("urllib.request.urlopen", return_value=response) as call:
            result = FoodEstimator("private-key", "gpt-6-sol", 19).estimate(
                "rice, hand for scale", b"jpeg", "image/jpeg"
            )
        self.assertEqual(result["calories"], 315)
        request = json.loads(call.call_args.args[0].data)
        self.assertFalse(request["store"])
        self.assertIn("visible hand", request["instructions"])
        self.assertIn("19 cm", request["instructions"])
        self.assertEqual(request["input"][0]["content"][1]["type"], "input_image")
        self.assertNotIn("private-key", str(request))

    def test_estimator_combines_food_and_multiple_labels_in_one_request(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps(
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps({"is_food": True, **SAMPLE}),
                            }
                        ],
                    }
                ],
            }
        ).encode()
        with patch("urllib.request.urlopen", return_value=response) as call:
            FoodEstimator("key").estimate(
                "200 g yogurt, 30 g cereal",
                images=[
                    (b"meal", "image/jpeg"),
                    (b"yogurt label", "image/png"),
                    (b"cereal label", "image/webp"),
                ],
            )
        call.assert_called_once()
        request = json.loads(call.call_args.args[0].data)
        content = request["input"][0]["content"]
        self.assertEqual(len(content), 4)
        self.assertEqual(content[0]["text"], "200 g yogurt, 30 g cereal")
        self.assertTrue(content[2]["image_url"].startswith("data:image/png;base64,"))
        self.assertIn("per 100 g", request["instructions"])
        self.assertIn("Do not double-count", request["instructions"])

    def test_estimator_rejects_invalid_or_oversized_albums_before_request(self):
        for images in (
            [(b"x", "image/jpeg")] * 11,
            [(b"", "image/png")],
            [(b"x", "image/tiff")],
            [(b"x" * 10_000_001, "image/jpeg")] * 3,
        ):
            with (
                self.subTest(count=len(images)),
                patch("urllib.request.urlopen") as call,
            ):
                with self.assertRaises(ValueError):
                    FoodEstimator("key").estimate(images=images)
                call.assert_not_called()

    def test_album_across_polls_and_restart_produces_one_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            api.download_photo.side_effect = lambda file_id: (
                file_id.encode(),
                "image/jpeg",
            )
            estimator = Mock()
            estimator.estimate.return_value = SAMPLE
            action = Mock()
            now = [datetime(2026, 10, 24, tzinfo=timezone.utc)]

            def bot():
                return Bot(
                    api,
                    lambda: [],
                    Path(directory) / "bot.json",
                    "42",
                    food_estimator=estimator,
                    food_action=action,
                    clock=lambda: now[0],
                )

            def photo(identity, album="meal", sender=42):
                message = {
                    "message_id": identity,
                    "from": {"id": sender},
                    "chat": {"id": sender, "type": "private"},
                    "media_group_id": album,
                    "date": 1792756800,
                }
                if identity == 1:
                    message.update(
                        photo=[{"file_id": "small"}, {"file_id": "meal"}],
                        caption="200 g yogurt",
                    )
                else:
                    message.update(
                        document={"file_id": "label", "mime_type": "image/png"},
                        caption="label for the yogurt",
                    )
                return {"update_id": identity, "message": message}

            b = bot()
            api.call.return_value = [photo(1)]
            b.poll_once()
            estimator.estimate.assert_not_called()
            now[0] += timedelta(seconds=1)
            b = bot()
            api.call.return_value = [photo(2)]
            b.poll_once()
            self.assertEqual(api.call.call_args.args[1]["timeout"], 1)
            estimator.estimate.assert_not_called()
            now[0] += timedelta(seconds=3)
            api.call.return_value = []
            b.poll_once()
            estimator.estimate.assert_called_once_with(
                "200 g yogurt\nlabel for the yogurt",
                images=[(b"meal", "image/jpeg"), (b"label", "image/png")],
            )
            self.assertEqual(len(b.state["pendingFood"]), 1)
            self.assertFalse(b.state["foodAlbums"])
            action.assert_not_called()
            previews = [
                c for c in api.call.call_args_list if c.args[0] == "sendMessage"
            ]
            self.assertEqual(len(previews), 1)
            self.assertIn("Save food entry", str(previews[0]))
            b.poll_once()
            estimator.estimate.assert_called_once()
            b.handle(photo(3, sender=11))
            self.assertFalse(b.state["foodAlbums"])

    def test_separate_albums_are_not_combined_and_duplicate_items_are_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [datetime(2026, 10, 24, tzinfo=timezone.utc)]
            api = Mock()
            api.download_photo.return_value = (b"photo", "image/jpeg")
            estimator = Mock()
            estimator.estimate.return_value = SAMPLE
            b = Bot(
                api,
                lambda: [],
                Path(directory) / "bot.json",
                "42",
                food_estimator=estimator,
                clock=lambda: now[0],
            )
            for identity, group in [(1, "a"), (1, "a"), (2, "b")]:
                b.handle(
                    {
                        "update_id": identity,
                        "message": {
                            "message_id": identity,
                            "media_group_id": group,
                            "from": {"id": 42},
                            "chat": {"id": 42, "type": "private"},
                            "photo": [{"file_id": "photo"}],
                        },
                    }
                )
            now[0] += timedelta(seconds=3)
            b.flush_food_albums()
            self.assertEqual(estimator.estimate.call_count, 2)
            self.assertEqual(len(b.state["pendingFood"]), 2)
            self.assertEqual(api.download_photo.call_count, 2)

    def test_failed_album_image_does_not_estimate_an_incomplete_meal(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            api.download_photo.side_effect = [
                (b"meal", "image/jpeg"),
                RuntimeError("Could not download the food photo."),
            ]
            estimator = Mock()
            b = Bot(
                api,
                lambda: [],
                Path(directory) / "bot.json",
                "42",
                food_estimator=estimator,
            )
            b.handle_food(
                "meal with label",
                "album",
                {},
                attachments=[
                    {"photo": [{"file_id": "meal"}]},
                    {"photo": [{"file_id": "label"}]},
                ],
            )
            estimator.estimate.assert_not_called()
            self.assertFalse(b.state.get("pendingFood"))
            self.assertIn("Could not download", api.call.call_args.args[1]["text"])

    def test_bot_requires_approval_for_photo_and_text_then_allows_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            api.download_photo.return_value = (b"jpeg", "image/jpeg")
            estimator = Mock()
            estimator.estimate.return_value = SAMPLE
            saved = {}

            def action(body):
                if body["action"] == "delete":
                    saved.pop(body["id"], None)
                    return {"ok": True}
                saved[body["id"]] = body
                return {"entry": body}

            bot = Bot(
                api,
                lambda: [],
                Path(directory) / "bot.json",
                "42",
                food_estimator=estimator,
                food_action=action,
            )

            def callback(command, update_id):
                return {
                    "update_id": update_id,
                    "callback_query": {
                        "id": "callback",
                        "from": {"id": 42},
                        "message": {"chat": {"id": 42, "type": "private"}},
                        "data": command,
                    },
                }

            photo = {
                "update_id": 21,
                "message": {
                    "from": {"id": 42},
                    "chat": {"id": 42, "type": "private"},
                    "photo": [{"file_id": "small"}, {"file_id": "large"}],
                    "caption": "hand for scale",
                    "date": 1792756800,
                },
            }
            bot.handle(photo)
            self.assertEqual(len(saved), 0)
            estimator.estimate.assert_called_with(
                "hand for scale", b"jpeg", "image/jpeg"
            )
            self.assertEqual(api.download_photo.call_args.args, ("large",))
            self.assertIn("315 kcal", api.call.call_args.args[1]["text"])
            self.assertIn("NOT SAVED", api.call.call_args.args[1]["text"])
            first_id = next(iter(bot.state["pendingFood"]))
            self.assertEqual(bot.state["pendingFood"][first_id]["status"], "pending")
            bot = Bot(
                api,
                lambda: [],
                Path(directory) / "bot.json",
                "42",
                food_estimator=estimator,
                food_action=action,
            )
            self.assertEqual(bot.state["pendingFood"][first_id]["status"], "pending")
            bot.handle(callback("food:save:" + first_id, 22))
            self.assertEqual(len(saved), 1)
            self.assertEqual(bot.state["pendingFood"][first_id]["status"], "saved")
            bot.handle(callback("food:save:" + first_id, 23))
            self.assertEqual(len(saved), 1)
            bot.handle(
                {
                    "update_id": 24,
                    "message": {
                        "from": {"id": 42},
                        "chat": {"id": 42, "type": "private"},
                        "text": "3 bananas",
                        "date": 1792756800,
                    },
                }
            )
            self.assertEqual(len(saved), 1)
            second_id = next(key for key in bot.state["pendingFood"] if key != first_id)
            bot.handle(callback("food:cancel:" + second_id, 25))
            bot.handle(callback("food:save:" + second_id, 26))
            self.assertEqual(len(saved), 1)
            self.assertEqual(bot.state["pendingFood"][second_id]["status"], "cancelled")
            bot.handle(callback("food:delete:" + first_id, 27))
            self.assertEqual(len(saved), 0)
            bot.handle(
                {
                    "update_id": 28,
                    "message": {
                        "from": {"id": 11},
                        "chat": {"id": 11, "type": "private"},
                        "text": "3 bananas",
                    },
                }
            )
            self.assertEqual(len(saved), 0)

    def test_expired_food_preview_cannot_be_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            estimator = Mock()
            estimator.estimate.return_value = SAMPLE
            save = Mock()
            bot = Bot(
                api,
                lambda: [],
                Path(directory) / "bot.json",
                "42",
                food_estimator=estimator,
                food_action=save,
            )
            bot.handle(
                {
                    "update_id": 31,
                    "message": {
                        "from": {"id": 42},
                        "chat": {"id": 42, "type": "private"},
                        "text": "3 bananas",
                    },
                }
            )
            identity = next(iter(bot.state["pendingFood"]))
            bot.state["pendingFood"][identity]["expires"] = "2000-01-01T00:00:00+00:00"
            bot.save()
            bot.handle(
                {
                    "update_id": 32,
                    "callback_query": {
                        "id": "callback",
                        "from": {"id": 42},
                        "message": {"chat": {"id": 42, "type": "private"}},
                        "data": "food:save:" + identity,
                    },
                }
            )
            save.assert_not_called()
            self.assertEqual(bot.state["pendingFood"][identity]["status"], "expired")

    def test_non_food_plain_text_falls_through_to_coach(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            estimator = Mock()
            estimator.estimate.return_value = None
            bot = Bot(
                api,
                lambda: [],
                Path(directory) / "bot.json",
                "42",
                food_estimator=estimator,
            )
            with patch.object(bot, "handle_chat") as chat:
                bot.handle(
                    {
                        "update_id": 25,
                        "message": {
                            "from": {"id": 42},
                            "chat": {"id": 42, "type": "private"},
                            "text": "How was my last workout?",
                        },
                    }
                )
            chat.assert_called_once()


if __name__ == "__main__":
    unittest.main()
