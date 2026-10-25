import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from reptrace.coaching.assistant import TrainingCoach, TrainingTools
from reptrace.telegram.bot import Bot, TelegramDraft, TelegramError


def stream(events):
    return io.BytesIO(
        b"".join(
            ("event: " + e["type"] + "\ndata: " + json.dumps(e) + "\n\n").encode()
            for e in events
        )
    )


class StreamingTests(unittest.TestCase):
    def test_text_stream_and_completed_tool_round_trip(self):
        call = {
            "type": "function_call",
            "name": "get_training_overview",
            "arguments": "{}",
            "call_id": "c1",
        }
        final = {
            "type": "message",
            "content": [{"type": "output_text", "text": "Hello world"}],
        }
        responses = [
            stream(
                [
                    {
                        "type": "response.completed",
                        "response": {"status": "completed", "output": [call]},
                    }
                ]
            ),
            stream(
                [
                    {"type": "response.reasoning_text.delta", "delta": "private"},
                    {"type": "response.output_text.delta", "delta": "Hello"},
                    {"type": "response.output_text.delta", "delta": " world"},
                    {
                        "type": "response.completed",
                        "response": {"status": "completed", "output": [final]},
                    },
                ]
            ),
        ]
        callback = Mock()
        coach = TrainingCoach("test-key")
        tools = TrainingTools({"sets": []}, {})
        with patch("urllib.request.urlopen", side_effect=responses) as request:
            result = coach.answer("Hello", tools, on_text=callback)
        self.assertEqual(result["text"], "Hello world")
        self.assertEqual(
            [c.args[0] for c in callback.call_args_list], ["Hello", "Hello world"]
        )
        bodies = [json.loads(c.args[0].data) for c in request.call_args_list]
        self.assertTrue(all(b["stream"] for b in bodies))
        self.assertTrue(
            any(
                i.get("call_id") == "c1" and i["type"] == "function_call_output"
                for i in bodies[1]["input"]
            )
        )

    def test_failed_or_truncated_stream_is_not_success(self):
        for events in (
            [],
            [{"type": "response.output_text.delta", "delta": "Partial"}],
            [{"type": "response.failed"}],
            [{"type": "response.incomplete"}],
            [{"type": "error"}],
        ):
            with (
                self.subTest(events=events),
                patch("urllib.request.urlopen", return_value=stream(events)),
            ):
                with self.assertRaises(RuntimeError):
                    TrainingCoach("test-key").request({}, on_text=Mock())

    def test_preview_throttles_and_obeys_retry_after(self):
        api = Mock()
        draft = TelegramDraft(api, 42)
        with patch("reptrace.telegram.bot.time.monotonic", return_value=10) as clock:
            draft.update("First")
            draft.update("Second")
            self.assertEqual(api.call.call_count, 1)
            clock.return_value = 12
            api.call.side_effect = TelegramError(429, 5)
            draft.update("Third")
            api.call.side_effect = None
            clock.return_value = 16
            draft.update("Fourth")
            self.assertEqual(api.call.call_count, 2)
            clock.return_value = 18
            draft.update("🙂" * 3000)
        values = api.call.call_args.args[1]
        self.assertEqual(values["draft_id"], draft.draft_id)
        self.assertLessEqual(len(values["text"].encode("utf-16-le")) // 2, 4096)

    def test_preview_failure_keeps_final_reply_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            coach = Mock(configured=True)

            def answer(message, tools, history, on_text):
                on_text("Hello")
                on_text("Hello world")
                return {"text": "**Hello world**", "artifacts": []}

            coach.answer.side_effect = answer

            def send(method, values, **kwargs):
                if method == "sendMessageDraft":
                    raise TelegramError(400)

            api.call.side_effect = send
            bot = Bot(
                api,
                lambda: [],
                Path(directory) / "state.json",
                allowed_user=42,
                fetch_data=lambda: {"sets": []},
                coach=coach,
            )
            bot.handle_chat("Hi", "turn")
            self.assertEqual(
                [c.args[0] for c in api.call.call_args_list],
                ["sendMessageDraft", "sendMessage"],
            )
            self.assertEqual(
                bot.state["coachHistory"][-1]["content"], "**Hello world**"
            )
            self.assertFalse(bot.state["chatOutbox"])
