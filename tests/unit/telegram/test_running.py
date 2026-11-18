from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from reptrace.telegram.bot import Bot, TelegramError
from reptrace.coaching.assistant import TrainingTools
from reptrace.reports.running import render_running_report
from reptrace.web.running_demo import demo_detail
from tests.unit.telegram.test_telegram_bot import update

RUN = {
    "id": "123",
    "name": "<Synthetic run>",
    "type": "running",
    "time": "2026-11-01T09:00:00Z",
    "date": "2026-11-01",
    "distanceKm": 5,
    "movingSeconds": 1500,
    "averageHR": 145,
}


class TelegramRunningTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.api = Mock()
        self.fetch = Mock(return_value={"runs": [RUN]})
        self.detail = demo_detail(RUN)
        self.reader = Mock(return_value=self.detail)
        self.bot = Bot(
            self.api,
            Mock(),
            Path(self.directory.name) / "bot.json",
            "42",
            fetch_data=self.fetch,
            running=self.reader,
            clock=lambda: datetime(2026, 11, 11, tzinfo=timezone.utc),
        )

    def tearDown(self):
        self.directory.cleanup()

    def test_strangers_and_group_chats_cannot_read_run_data(self):
        self.bot.handle(update(sender=11, text="/run latest"))
        self.bot.handle(update(text="/runs", chat_type="group"))
        self.api.call.assert_not_called()
        self.reader.assert_not_called()
        self.fetch.assert_not_called()

    def test_overview_and_report_commands_deliver_normalized_metrics_and_html(self):
        self.bot.handle(update(text="/running 30"))
        self.assertIn("5.00 km", self.api.call.call_args.args[1]["text"])
        self.assertEqual(
            self.api.call.call_args.args[1]["reply_markup"]["inline_keyboard"][-1][0][
                "callback_data"
            ],
            "run:123",
        )
        self.bot.handle(update(text="/run latest", identity=2))
        self.reader.assert_called_once_with({"id": "123"})
        calls = self.api.call.call_args_list
        self.assertEqual(calls[-1].args[0], "sendDocument")
        html = calls[-1].kwargs["document"].decode()
        self.assertIn("Ground contact time", html)
        self.assertIn("Laps & intervals", html)
        self.assertIn("&lt;Synthetic run&gt;", html)
        self.assertNotIn("<Synthetic run>", html)
        self.assertTrue(all(c.args[1]["chat_id"] == 42 for c in calls))

    def test_failed_document_retry_does_not_resend_summary(self):
        self.api.call.side_effect = [{"message_id": 1}, TelegramError(500)]
        with self.assertRaises(TelegramError):
            self.bot.handle(update(text="/run latest"))
        self.api.call.reset_mock(side_effect=True)
        self.bot.handle(update(text="/run latest"))
        self.assertEqual(self.api.call.call_count, 1)
        self.assertEqual(self.api.call.call_args.args[0], "sendDocument")
        self.reader.assert_called_once()

    def test_unknown_id_does_not_invoke_remote_reader(self):
        self.bot.handle(update(text="/run 999"))
        self.reader.assert_not_called()
        self.assertIn("Choose a recorded run", self.api.call.call_args.args[1]["text"])

    def test_coach_history_detail_comparison_and_attachment_share_facts(self):
        data = {
            "sets": [],
            "runs": [
                RUN,
                {**RUN, "id": "456", "distanceKm": 10, "movingSeconds": 3600},
            ],
        }
        tools = TrainingTools(data, {}, running=self.reader)
        history = tools.call(
            "get_running_history", {"from_date": None, "to_date": None, "limit": 1}
        )
        self.assertEqual(history["summary"]["distanceKm"], 15)
        self.assertEqual(history["summary"]["movingPace"], 340)
        self.assertTrue(history["truncated"])
        detail = tools.call("get_running_detail", {"run_id": "123"})
        self.assertNotIn("samples", detail)
        self.assertEqual(detail["chartSampleCount"], 301)
        self.assertEqual(detail["summary"]["strideLengthM"], 1.06)
        result = tools.call("export_running_report", {"run_id": "123"})
        self.assertTrue(result["queued"])
        self.assertEqual(tools.artifacts[0]["kind"], "html_report")
        self.assertEqual(tools.artifacts[0]["html"], render_running_report(self.detail))
        with self.assertRaises(ValueError):
            tools.call("get_running_detail", {"run_id": "999"})

    def test_compare_defaults_to_latest_two_recorded_runs(self):
        older = {
            **RUN,
            "id": "456",
            "date": "2026-10-01",
            "time": "2026-10-01T09:00:00Z",
            "movingSeconds": 1800,
        }
        self.fetch.return_value = {"runs": [older, RUN]}
        self.reader.side_effect = lambda body: demo_detail(
            RUN if body["id"] == "123" else older
        )
        self.bot.handle(update(text="/runcompare"))
        self.assertEqual(
            [c.args[0]["id"] for c in self.reader.call_args_list], ["123", "456"]
        )
        self.assertIn("Run comparison", self.api.call.call_args.args[1]["text"])

    def test_running_callback_is_owner_only_and_returns_report(self):
        callback = {
            "update_id": 3,
            "callback_query": {
                "id": "cb",
                "from": {"id": 11},
                "message": {"chat": {"id": 42, "type": "private"}},
                "data": "run:123",
            },
        }
        self.bot.handle(callback)
        self.reader.assert_not_called()
        callback["callback_query"]["from"]["id"] = 42
        self.bot.handle(callback)
        self.reader.assert_called_once_with({"id": "123"})
        self.assertEqual(self.api.call.call_args.args[0], "sendDocument")
