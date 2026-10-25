from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import Mock

from reptrace.coaching.assistant import TrainingTools
from reptrace.storage.state import WebState
from reptrace.telegram.bot import Bot
from tests.unit.nutrition.test_food_log import SAMPLE


class SavedFoodCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.store = WebState(self.root / "db.sqlite")
        self.entry = self.store.food_action(dict(
            SAMPLE, action="add", id=str(uuid.uuid4()),
            time=datetime.now(timezone.utc).isoformat(), description="3 bananas",
        ))["entry"]
        self.api = Mock()
        self.api.call.return_value = {"message_id": 20}
        self.estimator = Mock()
        self.estimator.estimate.return_value = dict(
            SAMPLE, calories=157.5, protein_g=1.95, carbs_g=40.5, fat_g=0.6,
            items=[{"name": "Banana", "portion": "1.5 medium"}],
        )
        self.bot = self.restart()

    def restart(self):
        return Bot(self.api, lambda: [], self.root / "bot.json", "42",
                   fetch_data=lambda: {"foodLog": self.store.food_entries()},
                   food_action=self.store.food_action, food_estimator=self.estimator)

    def draft(self, request="correction", revision=None):
        return self.bot.handle_food("half the portion", request, {},
                                    revision_of=revision or self.entry["id"],
                                    defer_preview=True)["draftId"]

    def test_tool_preview_cancel_and_restart_save_replace_one_entry(self):
        tools = TrainingTools({"foodLog": [self.entry]}, {})
        tools.food_preview = lambda desc, rev: self.bot.handle_food(
            desc, "tool", {}, revision_of=rev, defer_preview=True)
        result = tools.call("propose_food_entry", {
            "description": "half the portion", "revision_id": self.entry["id"],
        })
        draft = result["draftId"]
        self.assertFalse(result["saved"])
        self.assertEqual(self.store.food_entries(), [self.entry])
        self.bot.send_food_preview(draft)
        self.assertIn("EDIT SAVED FOOD", self.api.call.call_args.args[1]["text"])
        self.bot.handle_food_review("food:cancel:" + draft)
        self.assertEqual(self.store.food_entries(), [self.entry])
        draft = self.draft()
        self.bot = self.restart()
        self.bot.handle_food_review("food:save:" + draft)
        entries = self.store.food_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["id"], self.entry["id"])
        self.assertEqual(entries[0]["time"], self.entry["time"])
        self.assertEqual(entries[0]["calories"], 157.5)
        self.assertEqual(entries[0]["protein_g"], 1.95)
        button = self.api.call.call_args.args[1]["reply_markup"]["inline_keyboard"][0][0]
        self.assertEqual(button["callback_data"], "food:delete:" + self.entry["id"])

    def test_uncertain_retry_conflict_deleted_and_original_audit(self):
        draft = self.draft()
        body = self.bot.state["pendingFood"][draft]["body"]
        first = self.store.food_action(body)  # server committed, reply lost
        self.store = WebState(self.root / "db.sqlite")
        self.assertEqual(self.store.food_action(body), first)
        with self.store.connect() as connection:
            import json
            row = connection.execute("SELECT before_data FROM audit WHERE id=?",
                                     (draft,)).fetchone()
            self.assertEqual(json.loads(row["before_data"]), self.entry)
        reused = dict(body, calories=10)
        with self.assertRaisesRegex(ValueError, "already used"):
            self.store.food_action(reused)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.store.food_action(dict(body, requestId=str(uuid.uuid4())))
        self.store.food_action({"action": "delete", "id": self.entry["id"]})
        self.assertEqual(self.store.food_action(body), first)
        self.assertEqual(self.store.food_entries(), [])
        with self.assertRaisesRegex(ValueError, "deleted"):
            self.store.food_action(dict(body, requestId=str(uuid.uuid4())))

    def test_revision_of_update_keeps_original_expected_entry(self):
        first = self.draft()
        second = self.draft("second", first)
        body = self.bot.state["pendingFood"][second]["body"]
        self.assertEqual(body["expectedEntry"], self.entry)
        self.assertEqual(body["id"], self.entry["id"])
        self.assertEqual(self.bot.state["pendingFood"][first]["status"], "superseded")
        self.assertEqual(self.store.food_entries(), [self.entry])
        self.bot.handle_food_review("food:save:" + second)
        third = self.draft("third", second)
        self.assertEqual(self.bot.state["pendingFood"][third]["body"]["expectedEntry"],
                         self.store.food_entries()[0])

    def test_invalid_update_is_atomic(self):
        draft = self.draft()
        body = deepcopy(self.bot.state["pendingFood"][draft]["body"])
        body["calories"] = -1
        with self.assertRaises(ValueError):
            self.store.food_action(body)
        self.assertEqual(self.store.food_entries(), [self.entry])
        with self.store.connect() as connection:
            self.assertIsNone(connection.execute("SELECT id FROM audit WHERE id=?",
                                                (draft,)).fetchone())
