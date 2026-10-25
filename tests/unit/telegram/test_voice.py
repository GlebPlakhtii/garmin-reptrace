import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from reptrace.telegram.bot import Bot, Telegram
from reptrace.telegram.conversation import Runtime
from reptrace.telegram.voice import transcribe, VoiceError, MAX_BYTES


class VoiceTests(unittest.TestCase):
    def test_ogg_metadata_original_language_and_decimal_transcript(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps(
            {"text": "Жим dumbbell 22.5 kg, вісім повторів"}
        ).encode()
        with patch("urllib.request.urlopen", return_value=response) as url:
            text = transcribe(b"OggSsynthetic", key="private-test")
        self.assertIn("22.5 kg", text)
        req = url.call_args.args[0]
        self.assertEqual(req.full_url, "https://api.openai.com/v1/audio/transcriptions")
        self.assertIn(b'filename="voice.ogg"', req.data)
        self.assertIn(b"Content-Type: audio/ogg", req.data)
        self.assertIn(b"gpt-transcribe", req.data)
        self.assertNotIn(b'name="language"', req.data)

    def test_empty_unsupported_and_failed_transcription(self):
        for audio in (b"", b"not audio", b"OggS" + b"0" * MAX_BYTES):
            with self.assertRaises(VoiceError):
                transcribe(audio, key="key")
        with patch("urllib.request.urlopen", side_effect=OSError("private endpoint")):
            with self.assertRaises(VoiceError) as caught:
                transcribe(b"OggSdata", key="key")
            self.assertNotIn("private endpoint", str(caught.exception))
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"text":" "}'
        with patch("urllib.request.urlopen", return_value=response):
            with self.assertRaises(VoiceError):
                transcribe(b"OggSdata", key="key")

    def test_queue_reply_context_duplicate_and_transcript_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            api.download_voice.return_value = b"OggSdata"
            api.call.return_value = {"message_id": 88}
            bot = Bot(api, Mock(), Path(directory) / "state.json", "42")
            bot.handle_chat = Mock(side_effect=RuntimeError("temporary"))
            runtime = Runtime(bot, clock=lambda: 100)
            update = {
                "update_id": 15,
                "message": {
                    "message_id": 7,
                    "from": {"id": 42},
                    "chat": {"id": 42, "type": "private"},
                    "voice": {
                        "duration": 8,
                        "file_size": 100,
                        "file_id": "fake",
                        "mime_type": "audio/ogg",
                    },
                    "reply_to_message": {"message_id": 4, "text": "Synthetic set"},
                },
            }
            runtime.receive(update)
            runtime.receive(update)
            item = runtime.store.next()
            with patch(
                "reptrace.telegram.voice.transcribe",
                return_value="Зміни вагу на 22.5 kg",
            ) as speech:
                runtime.execute(*item)
                self.assertEqual(
                    runtime.store.db.execute("SELECT status FROM requests").fetchone()[
                        0
                    ],
                    "retryable",
                )
                bot.handle_chat.side_effect = None
                runtime.execute(*item)
                speech.assert_called_once()
                api.download_voice.assert_called_once()
            self.assertEqual(
                bot.handle_chat.call_args.kwargs["source_messages"][0][
                    "reply_to_message"
                ]["message_id"],
                4,
            )
            self.assertIsNone(runtime.store.next())
            heard = [
                x
                for x in api.call.call_args_list
                if x.args[0] == "sendMessage"
                and x.args[1].get("text", "").startswith("Heard:")
            ]
            self.assertEqual(len(heard), 1)
            self.assertEqual(
                json.loads(bot.path.read_text())["voiceTranscripts"]["42:7"]["text"],
                "Зміни вагу на 22.5 kg",
            )
            runtime.store.db.close()

    def test_limits_prevent_download_and_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            bot = Bot(api, Mock(), Path(directory) / "state.json", "42")
            bot.handle_chat = Mock()
            for duration, size in [(301, 100), (5, 20_000_001), (0, 100)]:
                with self.assertRaises(VoiceError):
                    bot.handle(
                        {
                            "update_id": 1,
                            "message": {
                                "message_id": 1,
                                "from": {"id": 42},
                                "chat": {"id": 42, "type": "private"},
                                "voice": {
                                    "duration": duration,
                                    "file_size": size,
                                    "file_id": "fake",
                                },
                            },
                        }
                    )
            api.download_voice.assert_not_called()
            bot.handle_chat.assert_not_called()
