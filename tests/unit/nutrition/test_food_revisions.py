from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from reptrace.nutrition.estimation import FoodEstimator
from reptrace.telegram.bot import Bot, TelegramError
from tests.unit.nutrition.test_food_log import SAMPLE


class FoodRevisionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.now = datetime(2026, 10, 24, tzinfo=timezone.utc)
        self.api = Mock()
        self.api.download_photo.side_effect = lambda fid: (fid.encode(), "image/jpeg")
        self.next_message = 100

        def send(method, values, **kwargs):
            self.next_message += 1
            return {"message_id": self.next_message}

        self.api.call.side_effect = send
        self.estimator = Mock()
        self.estimator.estimate.return_value = SAMPLE
        self.action = Mock()
        self.bot = self.restart()

    def restart(self):
        return Bot(
            self.api,
            lambda: [],
            self.path,
            "42",
            food_estimator=self.estimator,
            food_action=self.action,
            clock=lambda: self.now,
        )

    def message(self, identity, text="", reply=None, photo=None, album=None):
        message = {
            "message_id": identity,
            "from": {"id": 42},
            "chat": {"id": 42, "type": "private"},
            "date": 1792756800,
        }
        if photo:
            message.update(photo=[{"file_id": photo}], caption=text)
        else:
            message["text"] = text
        if reply:
            message["reply_to_message"] = {"message_id": reply}
        if album:
            message["media_group_id"] = album
        return {"update_id": identity, "message": message}

    def initial(self):
        self.bot.handle(self.message(1, "rice and yogurt", photo="meal"))
        identity = next(iter(self.bot.state["pendingFood"]))
        return identity, self.bot.state["pendingFood"][identity]["preview_message_id"]

    def callback(self, identity, action="save"):
        self.bot.handle(
            {
                "update_id": 90,
                "callback_query": {
                    "id": "cb",
                    "from": {"id": 42},
                    "message": {"chat": {"id": 42, "type": "private"}},
                    "data": "food:" + action + ":" + identity,
                },
            }
        )

    def test_text_correction_retires_old_buttons_and_only_saves_latest(self):
        original, preview = self.initial()
        stamp = self.bot.state["pendingFood"][original]["body"]["time"]
        self.estimator.estimate.return_value = {**SAMPLE, "calories": 200}
        self.bot = self.restart()
        self.bot.handle(self.message(2, "only half the rice", reply=preview))
        prior = self.bot.state["pendingFood"][original]
        latest = prior["replacement"]
        self.assertEqual(prior["status"], "superseded")
        self.assertEqual(self.bot.state["pendingFood"][latest]["body"]["time"], stamp)
        self.assertEqual(
            self.estimator.estimate.call_args.args, ("only half the rice",)
        )
        self.assertEqual(
            self.estimator.estimate.call_args.kwargs["images"],
            [(b"meal", "image/jpeg")],
        )
        self.assertEqual(
            self.estimator.estimate.call_args.kwargs["previous"]["calories"], 315
        )
        self.callback(original)
        self.action.assert_not_called()
        self.assertIn("replaced", self.api.call.call_args.args[1]["text"])
        self.callback(latest)
        self.callback(latest)
        self.action.assert_called_once()
        self.assertEqual(self.action.call_args.args[0]["calories"], 200)
        self.assertNotIn("sources", self.bot.state["pendingFood"][latest])

    def test_replying_to_original_preview_follows_latest_revision(self):
        original, preview = self.initial()
        self.bot.handle(self.message(2, "half the rice", reply=preview))
        first = self.bot.state["pendingFood"][original]["replacement"]
        self.bot.handle(self.message(3, "yogurt was 150 g", reply=preview))
        second = self.bot.state["pendingFood"][first]["replacement"]
        self.assertEqual(self.bot.state["pendingFood"][second]["status"], "pending")
        self.assertIn(
            "half the rice",
            self.estimator.estimate.call_args.kwargs["previous"]["description"],
        )
        self.assertEqual(
            len(
                [
                    d
                    for d in self.bot.state["pendingFood"].values()
                    if d["status"] == "pending"
                ]
            ),
            1,
        )

    def test_later_label_album_uses_original_photo_after_restart(self):
        original, preview = self.initial()
        self.bot.handle(
            self.message(
                2, "yogurt label", reply=preview, photo="label", album="labels"
            )
        )
        self.bot.handle(self.message(3, "", photo="label-back", album="labels"))
        self.estimator.estimate.assert_called_once()
        self.bot = self.restart()
        self.now += timedelta(seconds=3)
        self.bot.flush_food_albums()
        self.estimator.estimate.assert_called_with(
            "yogurt label",
            images=[
                (b"meal", "image/jpeg"),
                (b"label", "image/jpeg"),
                (b"label-back", "image/jpeg"),
            ],
            previous=self.bot.state["pendingFood"][original]["body"],
        )
        self.assertEqual(
            self.bot.state["pendingFood"][original]["status"], "superseded"
        )
        self.action.assert_not_called()

    def test_failed_revision_preserves_original_preview(self):
        original, preview = self.initial()
        self.estimator.estimate.side_effect = RuntimeError("Estimator unavailable")
        self.bot.handle(self.message(2, "half the rice", reply=preview))
        self.assertEqual(self.bot.state["pendingFood"][original]["status"], "pending")
        self.assertEqual(len(self.bot.state["pendingFood"]), 1)
        self.callback(original)
        self.action.assert_called_once()

    def test_closed_and_expired_previews_cannot_be_revised(self):
        original, preview = self.initial()
        self.callback(original, "cancel")
        self.bot.handle(self.message(2, "half the rice", reply=preview))
        self.estimator.estimate.assert_called_once()
        self.bot.state["pendingFood"][original]["status"] = "pending"
        self.now += timedelta(days=2)
        self.bot.handle(self.message(3, "half the rice", reply=preview))
        self.estimator.estimate.assert_called_once()
        self.action.assert_not_called()

    def test_delivery_failure_retries_same_revision_without_reestimating(self):
        original, preview = self.initial()
        self.api.call.side_effect = TelegramError(429)
        with self.assertRaises(TelegramError):
            self.bot.handle(self.message(2, "half the rice", reply=preview))
        self.bot = self.restart()
        self.api.call.side_effect = None
        self.api.call.return_value = {"message_id": 200}
        self.bot.handle(self.message(2, "half the rice", reply=preview))
        self.assertEqual(self.estimator.estimate.call_count, 2)
        latest = self.bot.state["pendingFood"][original]["replacement"]
        self.assertEqual(self.bot.state["pendingFood"][latest]["status"], "pending")
        self.assertEqual(
            self.bot.state["pendingFood"][latest]["preview_message_id"], 200
        )

    def test_revision_request_contains_previous_estimate_and_correction(self):
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
                "half the rice",
                images=[(b"label", "image/png")],
                previous={**SAMPLE, "id": "internal-id"},
            )
        request = json.loads(call.call_args.args[0].data)
        content = request["input"][0]["content"]
        self.assertEqual(content[0]["text"], "half the rice")
        self.assertIn("315", content[1]["text"])
        self.assertNotIn("internal-id", content[1]["text"])
        self.assertEqual(content[2]["type"], "input_image")
        self.assertIn("complete revised meal", request["instructions"])

    def test_existing_preview_without_tracking_can_be_revised(self):
        original, preview = self.initial()
        self.bot.state["pendingFood"][original].pop("preview_message_id")
        self.bot.state["pendingFood"][original].pop("sources")
        update = self.message(2, "half the rice", reply=preview)
        update["message"]["reply_to_message"].update(
            {
                "from": {"is_bot": True},
                "reply_markup": {
                    "inline_keyboard": [[{"callback_data": "food:save:" + original}]]
                },
            }
        )
        self.bot.handle(update)
        self.assertEqual(
            self.bot.state["pendingFood"][original]["status"], "superseded"
        )
        self.assertEqual(self.estimator.estimate.call_args.kwargs["images"], [])
