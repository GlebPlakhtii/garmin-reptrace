from datetime import datetime, timezone
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zlib

from reptrace.reports.facts import session_facts
from reptrace.telegram.bot import Bot, TelegramError
from reptrace.telegram.conversation import Runtime
from reptrace.telegram.workout_widgets import (
    MAX_AGE,
    MAX_WIDGETS,
    WorkoutWidgets,
    page,
    snapshot,
    widget_html,
)
from tests.unit.reports.test_training_reports import records, row


def query(**changes):
    return {
        "id": "query-1",
        "from": {"id": 42},
        "chat": {"id": 42, "type": "private"},
        "message_id": 90,
        "type": {"type": "data"},
        "data": "view:0:0",
        **changes,
    }


class WidgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "widgets.sqlite3"
        self.api = Mock()
        self.api.call.return_value = {"message_id": 90}
        self.store = WorkoutWidgets(self.path, 42, self.api, clock=lambda: 1000)
        self.data = records()
        self.data["sets"] = [row("c", "2026-10-20", 10 + i, i) for i in range(9)]
        self.data["sets"].append(
            row("c", "2026-10-20", None, None, exercise="Custom exercise")
        )
        self.data["volumeSettings"] = {
            "exercises": {"Barbell Bench Press": {"multiplier": 2}}
        }
        self.facts = session_facts(self.data, "c")

    def send(self):
        self.store.send("request", self.facts)
        self.api.reset_mock()

    def test_private_state_uses_canonical_volume_and_keeps_zero_and_missing(self):
        original = copy.deepcopy(self.data)
        self.store.send("request", self.facts)
        method, values = self.api.call.call_args.args
        self.assertEqual(method, "sendWidget")
        self.assertNotIn("public_data", values)
        self.assertNotIn("is_shared", values)
        self.assertTrue(values["protect_content"])
        state = json.loads(values["chat_data"])
        self.assertEqual(state["volume"], "1128 kg·reps")  # sum((10+i)*i*2), i=0..8
        self.assertEqual(state["coverage"], "9/10 sets with volume")
        self.assertEqual(state["rows"][0], ["10", "0"])
        missing = json.loads(page(snapshot(self.facts), 1))
        self.assertEqual(missing["rows"], [["—", "—"]])
        self.assertEqual(self.data, original)
        self.assertNotIn("recovery", values["chat_data"])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_paginated_navigation_survives_restart_and_answers_before_edit(self):
        self.send()
        restored = WorkoutWidgets(self.path, 42, self.api, clock=lambda: 1001)
        restored.query(query(data="view:0:2"))
        calls = self.api.call.call_args_list
        self.assertEqual(
            [call.args[0] for call in calls],
            ["answerWidgetQuery", "editMessageWidgetData"],
        )
        state = json.loads(calls[0].args[1]["data"])
        self.assertEqual(state["rows"], [["18", "8"]])
        self.assertEqual(state["pc"], 3)
        self.assertEqual(calls[1].args[1]["chat_data"], calls[0].args[1]["data"])
        self.assertNotIn("public_data", calls[1].args[1])
        self.api.reset_mock()
        restored.send("request", self.facts)
        self.api.call.assert_not_called()

    def test_invalid_and_foreign_queries_cannot_read_snapshots_or_edit_messages(self):
        self.send()
        for changes in [
            {"from": {"id": 7}},
            {"chat": {"id": 7, "type": "private"}},
            {"chat": {"id": 42, "type": "group"}},
            {"chat": {}},
            {"message_id": 91},
            {"message_id": "90"},
            {"inline_message_id": "inline"},
            {"widget_id": "shared"},
            {"type": {"type": "sign_data"}},
            {"data": "view:999:0"},
            {"data": "view:0:3"},
            {"data": "view:-1:0"},
            {"data": "view:0:0\n"},
            {"data": "save:anything"},
            {"data": "x" * 1000},
        ]:
            with self.subTest(changes=changes):
                self.api.reset_mock()
                self.store.query(query(**changes))
                self.api.call.assert_called_once()
                method, values = self.api.call.call_args.args
                self.assertEqual(method, "answerWidgetQuery")
                self.assertIn("error", json.loads(values["data"]))
        self.api.reset_mock()
        WorkoutWidgets(self.path, None, self.api).query(query())
        self.assertIn("error", json.loads(self.api.call.call_args.args[1]["data"]))

    def test_expiry_retention_and_missing_local_snapshot(self):
        self.send()
        WorkoutWidgets(self.path, 42, self.api, clock=lambda: 1001 + MAX_AGE).query(
            query()
        )
        self.assertIn("error", json.loads(self.api.call.call_args.args[1]["data"]))
        self.api.reset_mock()
        with patch.object(self.store, "connect", side_effect=OSError("private path")):
            self.store.query(query())
        self.assertIn("error", json.loads(self.api.call.call_args.args[1]["data"]))
        db = self.store.connect()
        try:
            with db:
                db.executemany(
                    "INSERT INTO widgets VALUES (?,?,?,?,?)",
                    [
                        (42, f"r{i}", i + 100, 1000, "{}")
                        for i in range(MAX_WIDGETS + 5)
                    ],
                )
                self.store.prune(db)
            self.assertEqual(
                db.execute("SELECT count(*) FROM widgets").fetchone()[0], MAX_WIDGETS
            )
        finally:
            db.close()

    def test_payload_limits_with_unicode_and_untrusted_names(self):
        self.facts["workout"]["name"] = "🏋️" * 200
        self.facts["exercises"][0]["exercise"] = (
            '</script><img onerror="bad()">' + "ї" * 400
        )
        state = page(snapshot(self.facts))
        self.assertLessEqual(len(state.encode()), 1024)
        self.assertNotIn("onerror", widget_html())
        raw = widget_html().encode()
        self.assertLessEqual(len(raw), 32768)
        self.assertLessEqual(len(zlib.compress(raw, 9)), 4096)

    def test_answer_failure_and_edit_failure_do_not_stall_expired_queries(self):
        self.send()
        self.api.call.side_effect = TelegramError(400)
        self.store.query(query())
        self.assertEqual(self.api.call.call_count, 1)
        self.api.reset_mock()
        self.api.call.side_effect = [True, TelegramError(429)]
        self.store.query(query())
        self.assertEqual(self.api.call.call_count, 2)

    def bot(self):
        return Bot(
            self.api,
            Mock(),
            Path(self.temp.name) / "state.json",
            42,
            fetch_data=Mock(return_value=self.data),
            clock=lambda: datetime(2026, 11, 10, tzinfo=timezone.utc),
        )

    def test_runtime_queries_bypass_busy_worker_and_advance_offset(self):
        bot = self.bot()
        runtime = Runtime(bot)
        self.addCleanup(runtime.store.db.close)
        bot.workout_widgets().send("legacy-widget", self.facts)
        self.api.reset_mock()
        bot.fetch_data.reset_mock()
        runtime.active = "slow-coach-request"
        runtime.receive({"update_id": 12, "widget_query": query()})
        self.assertEqual(self.api.call.call_args_list[0].args[0], "answerWidgetQuery")
        self.assertEqual(runtime.active, "slow-coach-request")
        self.assertEqual(runtime.store.offset(), 13)
        self.assertIsNone(runtime.store.next())
        bot.fetch_data.assert_not_called()
        self.api.call.return_value = []
        runtime.poll()
        self.assertIn(
            "widget_query", self.api.call.call_args.args[1]["allowed_updates"]
        )


if __name__ == "__main__":
    unittest.main()
