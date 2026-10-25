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
            with self.assertRaises(TelegramError) as caught:
                Telegram("secret-token").call("getMe", {})
            self.assertNotIn("secret-token", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
