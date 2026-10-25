import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from reptrace.telegram.bot import Bot, TelegramError
from reptrace.telegram.card_demo import CardDemo


class DemoTests(unittest.TestCase):
    def test_all_callbacks_are_isolated_persistent_and_duplicate_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            api.call.return_value = {"message_id": 123}
            forbidden = Mock(side_effect=AssertionError("Real action reached"))
            bot = Bot(
                api,
                forbidden,
                Path(directory) / "bot.json",
                "42",
                database=forbidden,
                garmin=forbidden,
                food_action=forbidden,
            )
            demo = CardDemo(api, str(bot.path) + ".demo.sqlite3", 42)
            demo.send("fixture")
            self.assertEqual(api.call.call_args.args[0], "sendRichMessage")
            before = bot.path.read_bytes()
            for action in ("weight", "exercise", "details", "save", "reset"):
                state = demo.read("fixture")
                cb = {
                    "id": action,
                    "from": {"id": 42},
                    "message": {
                        "message_id": 123,
                        "chat": {"id": 42, "type": "private"},
                    },
                    "data": f"demo:fixture:{state['revision']}:{action}",
                }
                bot.handle({"update_id": 5, "callback_query": cb})
                after = demo.read("fixture")
                bot.handle({"update_id": 5, "callback_query": cb})
                self.assertEqual(after, demo.read("fixture"))
                self.assertEqual(api.call.call_args.args[0], "editMessageText")
                self.assertEqual(api.call.call_args.args[1]["message_id"], 123)
                self.assertEqual(bot.path.read_bytes(), before)
                if action == "weight":
                    self.assertEqual(after["weight"], 22.5)
                if action == "exercise":
                    self.assertEqual(after["exercise"], "Incline dumbbell press")
                if action == "details":
                    self.assertTrue(after["details"])
                if action == "save":
                    self.assertTrue(after["saved"])
                if action == "reset":
                    self.assertFalse(after["saved"])
            forbidden.assert_not_called()
            self.assertEqual(CardDemo(api, demo.path, 42).read("fixture"), after)
            self.assertNotIn("pendingEdits", bot.state)

    def test_fallback_and_uncertain_send(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            api.call.side_effect = [TelegramError(404), {"message_id": 55}]
            demo = CardDemo(api, Path(directory) / "demo.sqlite", 42)
            self.assertFalse(demo.send("fallback")["rich"])
            self.assertEqual(api.call.call_args.args[0], "sendMessage")
            api.call.side_effect = TelegramError("network")
            with self.assertRaises(TelegramError):
                demo.send("uncertain")
            count = api.call.call_count
            self.assertEqual(demo.send("uncertain")["status"], "sending")
            self.assertEqual(api.call.call_count, count)

    def test_forged_callbacks_do_not_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            api.call.return_value = {"message_id": 12}
            demo = CardDemo(api, Path(directory) / "demo.sqlite", 42)
            original = demo.send("fixture")
            for who, mid, action in [
                (43, 12, "save"),
                (42, 13, "save"),
                (42, 12, "apply"),
            ]:
                api.reset_mock()
                demo.callback(
                    {
                        "data": "demo:fixture:0:" + action,
                        "from": {"id": who},
                        "message": {"message_id": mid, "chat": {"id": 42}},
                    }
                )
                api.call.assert_not_called()
                self.assertEqual(demo.read("fixture"), original)
