from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from reptrace.telegram.bot import Bot, Telegram, TelegramError


def update(sender=42, text="/upper1", chat_type="private", identity=1):
    return {
        "update_id": identity,
        "message": {
            "from": {"id": sender},
            "chat": {"id": sender, "type": chat_type},
            "text": text,
        },
    }


def plans():
    return [
        {
            "type": "upper1",
            "name": "Upper 1",
            "baselineDate": "2026-10-20",
            "imagePages": 1,
        }
    ]


class BotTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "state.json"
        self.api = Mock()
        self.fetch = Mock(return_value=plans())

    def tearDown(self):
        self.directory.cleanup()

    def bot(self, owner="42"):
        return Bot(
            self.api, self.fetch, self.path, owner, pairing_code="private-pairing-code"
        )

    def test_strangers_and_groups_cannot_request_health_data(self):
        b = self.bot()
        b.handle(update(sender=11))
        b.handle(update(chat_type="group"))
        self.api.call.assert_not_called()
        self.fetch.assert_not_called()

    def test_unpaired_bot_requires_secret_not_first_start(self):
        b = self.bot(None)
        b.handle(update(text="/start"))
        b.handle(update(text="/start wrong"))
        self.assertIsNone(b.owner)
        self.api.call.assert_not_called()
        b.handle(update(text="/start private-pairing-code"))
        self.assertEqual(b.owner, 42)
        self.assertEqual(json.loads(self.path.read_text())["owner"], 42)
        b.handle(update(sender=11, text="/start private-pairing-code"))
        self.fetch.assert_not_called()

    @patch("reptrace.telegram.bot.render_plan", return_value=b"\x89PNG test")
    def test_command_sends_one_complete_png_only_to_owner(self, render):
        self.bot().handle(update())
        self.fetch.assert_called_once()
        self.assertEqual(self.api.call.call_count, 1)
        for call in self.api.call.call_args_list:
            self.assertEqual(call.args[0], "sendPhoto")
            self.assertEqual(call.args[1]["chat_id"], 42)
            self.assertTrue(call.kwargs["photo"].startswith(b"\x89PNG"))
        render.assert_called_once_with(plans()[0])

    @patch("reptrace.telegram.bot.render_plan", return_value=b"png")
    def test_saved_garmin_targets_are_labelled_in_photo_and_text_fallback(self, render):
        self.fetch.return_value = [dict(plans()[0], source="garmin_template", notice="Saved Garmin targets", exercises=[{
            "name": "Synthetic Press", "proposed": [{"weight": 72.5, "reps": 11}],
            "reason": "Saved Garmin targets; no automatic progression applied.",
        }])]
        self.api.call.side_effect = [TelegramError(500), {"message_id": 12}]
        self.bot().handle(update())
        calls = self.api.call.call_args_list
        self.assertIn("saved Garmin targets", calls[0].args[1]["caption"])
        self.assertIn("72.5 kg × 11 reps", calls[1].args[1]["text"])
        self.assertIn("saved Garmin targets", calls[1].args[1]["text"])

    @patch("reptrace.telegram.bot.render_plan", return_value=b"png")
    def test_plan_upload_server_failure_delivers_all_targets_as_text(self, render):
        plan = dict(plans()[0], exercises=[{
            "name": "Synthetic Press",
            "proposed": [{"weight": 30, "reps": 8}, {"weight": None, "reps": 9}],
            "reason": "Review missing load before training.",
        }])
        self.fetch.return_value = [plan]
        self.api.call.side_effect = [TelegramError(500), {"message_id": 12}]
        self.bot().handle(update())
        calls = self.api.call.call_args_list
        self.assertEqual([c.args[0] for c in calls], ["sendPhoto", "sendMessage"])
        text = calls[1].args[1]["text"]
        self.assertIn("Set 1: 30 kg × 8 reps", text)
        self.assertIn("Set 2: — kg × 9 reps", text)
        self.assertIn(plan["exercises"][0]["reason"], text)
        self.assertEqual(calls[1].args[1]["chat_id"], 42)

    @patch("reptrace.telegram.bot.render_plan", return_value=b"png")
    def test_plan_rate_limit_and_permission_errors_stay_retryable(self, render):
        for error in (TelegramError(429), TelegramError(401), TelegramError(403)):
            with self.subTest(code=error.code):
                self.api.reset_mock()
                self.api.call.side_effect = error
                with self.assertRaises(TelegramError):
                    self.bot().handle(update())
                self.assertEqual(self.api.call.call_count, 1)

    @patch("reptrace.telegram.bot.render_plan", return_value=b"original-png")
    def test_rejected_plan_photo_falls_back_to_original_png_document(self, render):
        self.api.call.side_effect = [TelegramError(400), {"message_id": 12}]
        self.bot().handle(update())
        calls = self.api.call.call_args_list
        self.assertEqual([c.args[0] for c in calls], ["sendPhoto", "sendDocument"])
        self.assertEqual(calls[1].kwargs, {"document": b"original-png", "filename": "next-session.png"})
        self.assertEqual(calls[0].args[1], calls[1].args[1])

    @patch("reptrace.telegram.bot.render_plan", return_value=b"png")
    def test_plan_timeout_supplies_text_without_retrying_uncertain_upload(self, render):
        self.fetch.return_value = [dict(plans()[0], exercises=[{
            "name": "Synthetic Raise", "proposed": [{"weight": 9, "reps": 12}], "reason": "Shared load.",
        }])]
        self.api.call.side_effect = [TelegramError("network"), {"message_id": 12}]
        self.bot().handle(update())
        calls = self.api.call.call_args_list
        self.assertEqual([c.args[0] for c in calls], ["sendPhoto", "sendMessage"])
        self.assertIn("could not be confirmed", calls[1].args[1]["text"])
        self.assertIn("9 kg × 12 reps", calls[1].args[1]["text"])

    @patch("reptrace.telegram.bot.render_plan", return_value=b"png")
    def test_rejected_document_falls_back_to_all_text_targets(self, render):
        plan = dict(plans()[0], exercises=[{
            "name": "Synthetic Raise", "proposed": [{"weight": 9, "reps": 12}], "reason": "Shared load.",
        }])
        self.api.call.side_effect = [TelegramError(400), TelegramError(400), {"message_id": 12}]
        self.bot().send_plan(plan, 42)
        calls = self.api.call.call_args_list
        self.assertEqual([c.args[0] for c in calls], ["sendPhoto", "sendDocument", "sendMessage"])
        self.assertIn("9 kg × 12 reps", calls[-1].args[1]["text"])

    @patch("reptrace.telegram.bot.render_plan", return_value=b"png")
    def test_failed_text_fallback_remains_retryable(self, render):
        plan = dict(plans()[0], exercises=[])
        self.api.call.side_effect = [TelegramError("network"), TelegramError("network")]
        with self.assertRaises(TelegramError):
            self.bot().send_plan(plan, 42)

    @patch("reptrace.telegram.bot.render_plan", return_value=b"png")
    def test_private_callback_works_and_is_acknowledged(self, render):
        value = {
            "update_id": 2,
            "callback_query": {
                "id": "callback",
                "from": {"id": 42},
                "message": {"chat": {"id": 42, "type": "private"}},
                "data": "plan:upper1",
            },
        }
        self.bot().handle(value)
        self.assertEqual(self.api.call.call_args_list[0].args[0], "answerCallbackQuery")
        self.fetch.assert_called_once()

    def test_processed_offsets_persist_and_failed_requests_are_not_acknowledged(self):
        b = self.bot()
        self.api.call.return_value = [update(text="/next", identity=8)]
        b.poll_once()
        self.assertEqual(self.bot().state["offset"], 9)
        self.api.call.side_effect = None
        self.api.call.return_value = [update(identity=9)]
        self.fetch.side_effect = RuntimeError("offline")
        with self.assertRaises(RuntimeError):
            b.poll_once()
        self.assertEqual(json.loads(self.path.read_text())["offset"], 9)

    def test_html_document_transport_has_filename_and_html_mime_type(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"ok":true,"result":{"message_id":123}}'
        with patch("urllib.request.urlopen", return_value=response) as request:
            sent = Telegram("secret-token").call(
                "sendDocument",
                {"chat_id": 42, "caption": "Cycling progress"},
                document=b"<html><svg></svg></html>",
                filename="cycling-2026.html",
            )
            body = request.call_args.args[0].data
            self.assertIn(b'name="document"; filename="cycling-2026.html"', body)
            self.assertIn(b"text/html; charset=utf-8", body)
            self.assertIn(b"<html><svg></svg></html>", body)
            self.assertEqual(sent["message_id"], 123)

    def test_transport_uses_png_multipart_and_does_not_expose_token_in_errors(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"ok":true,"result":{}}'
        with patch("urllib.request.urlopen", return_value=response) as request:
            Telegram("secret-token").call(
                "sendPhoto", {"chat_id": 42, "caption": "Upper 1"}, photo=b"png-data"
            )
            body = request.call_args.args[0].data
            self.assertIn(b"image/png", body)
            self.assertIn(b"png-data", body)
        with patch(
            "urllib.request.urlopen", side_effect=OSError("https://bot/secret-token")
        ):
            with self.assertLogs(level="WARNING") as logs, self.assertRaises(TelegramError) as caught:
                Telegram("secret-token").call("getMe", {})
            self.assertNotIn("secret-token", str(caught.exception))
            self.assertNotIn("secret-token", " ".join(logs.output))
            self.assertIn("getMe transport failed (OSError)", " ".join(logs.output))


if __name__ == "__main__":
    unittest.main()
