from pathlib import Path
from io import BytesIO
import sys
import tempfile
import unittest
from unittest.mock import Mock
from PIL import Image

from reptrace.coaching.assistant import TrainingTools
from reptrace.telegram.bot import Bot
from reptrace.exports.garmin_preview import render_garmin_preview_image

PREVIEW = {
    "previewId": "preview-token",
    "name": "Upper 1",
    "editable": [],
    "changes": [
        {
            "exercise": "Bench",
            "stepOrder": 2,
            "sets": 3,
            "field": "weight",
            "before": 80,
            "after": 82.5,
        }
    ],
    "skipped": [],
}


def callback(data, sender=42):
    return {
        "update_id": 3,
        "callback_query": {
            "id": "cb",
            "from": {"id": sender},
            "message": {"chat": {"id": sender, "type": "private"}},
            "data": data,
        },
    }


class GarminTelegramTests(unittest.TestCase):
    def test_coach_can_draft_but_cannot_apply(self):
        service = Mock(return_value=PREVIEW)
        state = {}
        tools = TrainingTools({}, state, request_id="test", garmin=service)
        result = tools.call(
            "propose_garmin_workout_update",
            {"workout_id": 123, "use_suggestions": True, "targets": []},
        )
        self.assertFalse(result["saved"])
        self.assertEqual(
            [c.args[0]["operation"] for c in service.call_args_list],
            ["preview", "revise"],
        )
        self.assertEqual(
            state["pendingEdits"][result["draftId"]]["body"]["action"],
            "garmin_workout_update",
        )
        with self.assertRaises(ValueError):
            tools.call("apply_garmin_workout", {})

    def test_owner_only_save_commits_once_and_has_no_incorrect_undo_button(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            service = Mock(return_value=PREVIEW)
            bot = Bot(
                api, lambda: [], Path(directory) / "state.json", "42", garmin=service
            )
            bot.handle(callback("garmin:123", sender=9))
            service.assert_not_called()
            bot.handle(callback("garmin:123"))
            identity = next(iter(bot.state["pendingEdits"]))
            self.assertEqual(
                [c.args[0]["operation"] for c in service.call_args_list],
                ["preview", "revise"],
            )
            sent = api.call.call_args_list
            self.assertEqual(sent[-1].args[0], "sendPhoto")
            self.assertTrue(sent[-1].kwargs["photo"].startswith(b"\x89PNG"))
            image = Image.open(BytesIO(sent[-1].kwargs["photo"]))
            self.assertEqual(image.format, "PNG")
            self.assertIn("reply_markup", sent[-1].args[1])
            service.return_value = {"ok": True}
            bot.handle(callback("edit:save:" + identity))
            bot.handle(callback("edit:save:" + identity))
            self.assertEqual(
                [c.args[0]["operation"] for c in service.call_args_list].count("apply"),
                1,
            )
            self.assertNotIn("reply_markup", api.call.call_args.args[1])
            self.assertIn("Garmin workout", api.call.call_args.args[1]["text"])

    def test_image_preview_renders_untrusted_garmin_data_as_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            preview = {
                **PREVIEW,
                "name": "<script>alert(1)</script>",
                "changes": [
                    {
                        **PREVIEW["changes"][0],
                        "exercise": "<img src=x onerror=alert(1)>",
                    }
                ],
                "skipped": [
                    {"exercise": "<b>x</b>", "reason": "<script>bad()</script>"}
                ],
            }
            bot = Bot(
                api,
                lambda: [],
                Path(directory) / "state.json",
                "42",
                garmin=Mock(return_value=preview),
            )
            bot.handle(callback("garmin:123"))
            sent = api.call.call_args_list[-1]
            self.assertEqual(sent.args[0], "sendPhoto")
            image = Image.open(BytesIO(sent.kwargs["photo"]))
            self.assertEqual(image.format, "PNG")
            self.assertNotIn(b"<script>", sent.kwargs["photo"])

    def test_long_preview_sends_one_image_with_all_sections_and_buttons(self):
        preview = {
            **PREVIEW,
            "changes": PREVIEW["changes"] * 23,
            "skipped": [{"exercise": "Bench", "reason": "Repeat expanded"}] * 7,
        }
        image = Image.open(BytesIO(render_garmin_preview_image(preview)))
        self.assertEqual(image.format, "PNG")
        self.assertLess(image.width + image.height, 10000)
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            bot = Bot(
                api,
                lambda: [],
                Path(directory) / "state.json",
                "42",
                garmin=Mock(return_value=preview),
            )
            bot.handle(callback("garmin:123"))
            photos = [
                call for call in api.call.call_args_list if call.args[0] == "sendPhoto"
            ]
            self.assertEqual(len(photos), 1)
            self.assertIn("reply_markup", photos[0].args[1])

    def test_garmin_command_lists_templates_without_coach(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            service = Mock(return_value={"workouts": [{"id": 123, "name": "Upper 1"}]})
            bot = Bot(
                api, lambda: [], Path(directory) / "state.json", "42", garmin=service
            )
            bot.handle(
                {
                    "update_id": 4,
                    "message": {
                        "from": {"id": 42},
                        "chat": {"id": 42, "type": "private"},
                        "text": "/garmin",
                    },
                }
            )
            self.assertEqual(
                api.call.call_args.args[1]["reply_markup"]["inline_keyboard"][0][0][
                    "callback_data"
                ],
                "garmin:123",
            )
