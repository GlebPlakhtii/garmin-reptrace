import copy
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw

from reptrace.reports.workout_sheet import (
    workout_sheet_facts,
    render_workout_sheet,
    photo_suitable,
    text_lines,
)
from reptrace.exports.plans import font
from reptrace.telegram.bot import Bot, MENU, Telegram, TelegramError
from tests.unit.reports.test_training_reports import records, row
from tests.unit.telegram.test_telegram_bot import update


class WorkoutSheetTests(unittest.TestCase):
    def test_every_record_including_unknown_uses_canonical_volume_without_mutation(
        self,
    ):
        data = records()
        data["volumeSettings"] = {
            "exercises": {"Barbell Bench Press": {"multiplier": 1.5, "loadCopies": 2}}
        }
        data["sets"] = [
            row("c", "2026-10-20", 20, 10),
            row("c", "2026-10-20", 0, 0, order=2),
            row("c", "2026-10-20", None, None, exercise="Unknown", order=3),
        ]
        original = copy.deepcopy(data)
        facts = workout_sheet_facts(data, "c")
        self.assertEqual(facts["totals"]["sets"], 3)
        self.assertEqual(facts["totals"]["volume"], 600)  # 20 * 10 * 1.5 * 2
        self.assertEqual(facts["totals"]["volumeKnown"], 1)
        self.assertEqual(facts["exercises"][0]["sets"][1]["weight"], 0)
        self.assertEqual(facts["exercises"][0]["sets"][1]["reps"], 0)
        self.assertEqual(facts["totals"]["repsKnown"], 2)
        self.assertEqual(facts["exercises"][1]["exercise"], "Unknown")
        self.assertEqual(data, original)

    def test_long_image_contains_all_rows_names_missing_values_and_last_set(self):
        data = records()
        data["sets"] = [
            row(
                "c",
                "2026-10-20",
                i + 1,
                5,
                duration=30,
                rest=90,
                source="manual",
                order=i,
            )
            for i in range(80)
        ]
        data["sets"].append(
            row(
                "c",
                "2026-10-20",
                None,
                None,
                exercise="Final exercise with missing measurements",
                order=81,
            )
        )
        text = []
        original = ImageDraw.ImageDraw.text

        def capture(draw, xy, value, *args, **kwargs):
            text.append(value)
            return original(draw, xy, value, *args, **kwargs)

        with patch.object(ImageDraw.ImageDraw, "text", capture):
            png = render_workout_sheet(workout_sheet_facts(data, "c"))
        self.assertIn("80", text)
        self.assertIn("Final exercise with missing measurements", text)
        self.assertIn("—", text)
        self.assertIn("0:30", text)
        self.assertIn("1:30", text)
        self.assertEqual(text.count("manual"), 80)
        self.assertFalse(photo_suitable(png))
        with Image.open(BytesIO(png)) as image:
            self.assertGreater(image.height, 4500)
            self.assertEqual(image.width, 1440)

    def test_long_unbroken_names_wrap_without_losing_characters_and_empty_is_rendered(
        self,
    ):
        measure = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        text = "ДовгаНазва" * 20
        lines = text_lines(text, measure, font(30), 500)
        self.assertEqual("".join(lines), text)
        self.assertTrue(
            all(measure.textlength(line, font=font(30)) <= 500 for line in lines)
        )
        data = records()
        data["sets"] = []
        png = render_workout_sheet(workout_sheet_facts(data, "c"))
        self.assertTrue(photo_suitable(png))


class WorkoutImageDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.api = Mock()
        self.data = records()
        self.fetch = Mock(return_value=self.data)
        self.bot = Bot(
            self.api,
            Mock(),
            Path(self.directory.name) / "state.json",
            42,
            fetch_data=self.fetch,
            clock=lambda: datetime(2026, 11, 10, tzinfo=timezone.utc),
        )

    def test_owner_command_and_old_widget_alias_send_one_complete_image(self):
        for command in ("/workout", "/widget"):
            self.api.reset_mock()
            self.bot.handle(update(text=command))
            self.api.call.assert_called_once()
            method, values = self.api.call.call_args.args
            self.assertEqual(method, "sendPhoto")
            self.assertEqual(values["chat_id"], 42)
            self.assertIn("all 1 recorded sets", values["caption"])
            self.assertNotIn("reply_markup", values)
            self.assertTrue(
                self.api.call.call_args.kwargs["photo"].startswith(b"\x89PNG")
            )
        self.assertTrue(
            any(
                b["callback_data"] == "workout:latest"
                for row in MENU["inline_keyboard"]
                for b in row
            )
        )

    def test_strangers_groups_and_empty_history_do_not_send_workout_images(self):
        self.bot.handle(update(text="/workout", sender=11))
        self.bot.handle(update(text="/workout", chat_type="group"))
        self.api.call.assert_not_called()
        self.fetch.assert_not_called()
        self.data["workouts"] = []
        self.bot.handle(update(text="/workout"))
        self.assertIn("No completed", self.api.call.call_args.args[1]["text"])

    def test_old_menu_buttons_send_image_instead_of_creating_more_widgets(self):
        self.bot.handle(
            {
                "update_id": 2,
                "callback_query": {
                    "id": "cb",
                    "from": {"id": 42},
                    "message": {"chat": {"id": 42, "type": "private"}},
                    "data": "widget:latest",
                },
            }
        )
        self.assertEqual(
            [c.args[0] for c in self.api.call.call_args_list],
            ["answerCallbackQuery", "sendPhoto"],
        )

    @patch("reptrace.telegram.bot.photo_suitable", return_value=False)
    def test_long_workout_uses_a_single_original_png_document(self, _):
        self.bot.handle(update(text="/workout"))
        self.api.call.assert_called_once()
        self.assertEqual(self.api.call.call_args.args[0], "sendDocument")
        self.assertEqual(
            self.api.call.call_args.kwargs["filename"], "workout-2026-10-20.png"
        )
        self.assertTrue(
            self.api.call.call_args.kwargs["document"].startswith(b"\x89PNG")
        )

    def test_photo_rejection_falls_back_to_original_but_network_failure_does_not_duplicate(
        self,
    ):
        self.api.call.side_effect = [TelegramError(400), {}]
        self.bot.handle(update(text="/workout"))
        calls = self.api.call.call_args_list
        self.assertEqual([c.args[0] for c in calls], ["sendPhoto", "sendDocument"])
        self.assertEqual(calls[0].kwargs["photo"], calls[1].kwargs["document"])
        self.api.reset_mock()
        self.api.call.side_effect = TelegramError("network")
        with self.assertRaises(TelegramError):
            self.bot.handle(update(text="/workout"))
        self.api.call.assert_called_once()

    def test_png_document_transport_uses_image_mime(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"ok":true,"result":{}}'
        with patch("urllib.request.urlopen", return_value=response) as request:
            Telegram("token").call(
                "sendDocument", {"chat_id": 42}, document=b"png", filename="workout.png"
            )
        self.assertIn(b'filename="workout.png"', request.call_args.args[0].data)
        self.assertIn(b"Content-Type: image/png", request.call_args.args[0].data)


if __name__ == "__main__":
    unittest.main()
