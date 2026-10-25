from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from reptrace.coaching.assistant import TrainingTools
from reptrace.storage.state import WebState, Conflict
from reptrace.telegram.bot import Bot
from tests.unit.reports.test_training_reports import records


class WebParityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = WebState(self.root / "state.sqlite")
        self.refresh()

    def refresh(self):
        self.data = records() | self.store.read()
        self.tools = TrainingTools(self.data, {}, request_id=str(uuid.uuid4()), today=date(2026, 10, 25))

    def apply(self, body):
        return self.store.apply(body, Mock(side_effect=AssertionError("No Influx writes expected")), "test", ZoneInfo("UTC"))

    def body(self, result):
        return self.tools.state["pendingEdits"][result["draftId"]]["body"]

    def test_settings_preserve_unrelated_values_retry_conflict_and_undo(self):
        result = self.tools.call("propose_settings_change", {
            "section": "equipment", "changes_json": json.dumps({
                "profiles": {"db": {"name": "Dumbbells per hand", "loads": [5, 10, 15]}},
                "assignments": {"Dumbbell Curl": "db"},
            }),
        })
        self.assertFalse(result["saved"])
        self.assertEqual(self.store.read()["equipment"]["profiles"], {})
        body = self.body(result)
        self.apply(body)
        self.assertEqual(self.apply(body), {"ok": True})
        with self.assertRaises(Conflict):
            self.apply(dict(body, requestId=str(uuid.uuid4())))
        self.refresh()
        result = self.tools.call("propose_settings_change", {
            "section": "equipment", "changes_json": '{"profiles":{"db":{"loads":[5,10,15,20]}}}',
        })
        self.assertEqual(self.body(result)["value"]["profiles"]["db"]["name"], "Dumbbells per hand")
        self.assertEqual(self.body(result)["value"]["assignments"], {"Dumbbell Curl": "db"})
        self.apply(self.body(result))
        self.refresh()
        history = self.tools.call("get_change_history", {})
        undo = self.tools.call("propose_undo_change", {"change_id": history["settings"][0]["id"]})
        self.apply(self.body(undo))
        self.assertEqual(self.store.read()["equipment"]["profiles"]["db"]["loads"], [5, 10, 15])

    def test_volume_partial_patch_and_validation(self):
        result = self.tools.call("propose_settings_change", {
            "section": "volume", "changes_json": '{"bodyWeightKg":80,"exercises":{"Custom":{"multiplier":2,"bodyweight":0,"loadCopies":2,"reviewed":true}}}',
        })
        self.apply(self.body(result))
        self.refresh()
        result = self.tools.call("propose_settings_change", {
            "section": "volume", "changes_json": '{"exercises":{"Custom":{"multiplier":1.5}}}',
        })
        value = self.body(result)["value"]
        self.assertEqual(value["bodyWeightKg"], 80)
        self.assertEqual(value["exercises"]["Custom"]["loadCopies"], 2)
        self.apply(self.body(result))
        with self.assertRaises(ValueError):
            self.tools.call("propose_settings_change", {"section": "volume", "changes_json": '{"bodyWeightKg":0}'})

    def test_goal_archive_restore_and_revision_checked_undo(self):
        result = self.tools.call("propose_record_change", {
            "entity": "goal", "operation": "save", "key": None,
            "value_json": '{"exercise":"Bench","mode":"load_reps","weight":50,"reps":10}',
        })
        self.apply(self.body(result))
        self.refresh()
        goal = self.data["goals"][0]
        result = self.tools.call("propose_record_change", {
            "entity": "goal", "operation": "archive", "key": goal["id"], "value_json": None,
        })
        self.apply(self.body(result))
        self.assertEqual(self.store.read()["goals"], [])
        self.refresh()
        result = self.tools.call("propose_record_change", {
            "entity": "goal", "operation": "restore", "key": goal["id"], "value_json": None,
        })
        self.apply(self.body(result))
        self.assertEqual(self.store.read()["goals"], [goal])

    def test_garmin_full_edit_only_previews_and_keeps_revision(self):
        self.tools.garmin = Mock(return_value={"previewId": "p", "name": "Upper", "fullEdit": True,
                                               "changes": [{"label": "Rest", "before": 60, "after": 90}]})
        result = self.tools.call("propose_garmin_structure_change", {
            "workout_id": 1, "expected_revision": "revision", "name": "Upper",
            "description": "", "segments_json": '[{"workoutSteps":[]}]',
        })
        self.assertFalse(result["saved"])
        self.tools.garmin.assert_called_once()
        self.assertEqual(self.tools.garmin.call_args.args[0]["operation"], "edit")
        self.assertEqual(self.tools.garmin.call_args.args[0]["expectedRevision"], "revision")
        self.assertEqual(self.body(result)["action"], "garmin_workout_update")

    def test_dashboard_bridge_validation_and_exports(self):
        result = self.tools.call("get_dashboard_view", {"view": "overview", "source": "all", "offset": 0, "limit": 10})
        self.assertEqual(result["sets"], 3)
        result = self.tools.call("export_dashboard_csv", {"dataset": "sets", "source": "all"})
        self.assertEqual(result["rows"], 3)
        self.assertEqual(self.tools.artifacts[0]["kind"], "csv")
        self.assertTrue(self.tools.call("export_next_workout_image", {"workout_type": "upper1"})["queued"])
        for options in ('{"window":true}', '{"grouping":"invalid"}', '{"surprise":1}', '{"weekly":1}'):
            with self.assertRaises(ValueError):
                self.tools.call("get_dashboard_view", {"view": "overview", "options_json": options})
        with patch("reptrace.coaching.parity.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(RuntimeError, "Node"):
                self.tools.call("get_dashboard_view", {"view": "overview"})

    def test_exports_are_delivered_and_preview_only_saves_after_confirmation(self):
        api = Mock()
        coach = Mock(configured=True)
        def answer(message, tools, *args, **kwargs):
            tools.call("export_dashboard_csv", {"dataset": "recovery", "source": "all"})
            tools.call("export_next_workout_image", {"workout_type": "upper1"})
            tools.call("propose_settings_change", {
                "section": "equipment", "changes_json": '{"profiles":{"db":{"name":"DB","loads":[5,10]}}}',
            })
            return {"text": "Review the preview.", "artifacts": tools.artifacts}
        coach.answer.side_effect = answer
        bot = Bot(api, lambda: [], self.root / "delivery.json", "42", coach=coach,
                  fetch_data=lambda: self.data)
        with patch("reptrace.telegram.bot.save_action", side_effect=self.apply) as save:
            bot.handle_chat("Send files and change equipment", "turn")
            save.assert_not_called()
            methods = [c.args[0] for c in api.call.call_args_list]
            self.assertIn("sendDocument", methods)
            self.assertIn("sendPhoto", methods)
            draft = next(iter(bot.state["pendingEdits"]))
            bot.handle_edit("edit:save:" + draft)
            bot.handle_edit("edit:save:" + draft)
            save.assert_called_once()
        self.assertEqual(self.store.read()["equipment"]["profiles"]["db"]["loads"], [5, 10])

    def test_food_entries_local_dates_and_pagination(self):
        self.tools.data.update(timezone="Europe/Kyiv", foodLog=[
            {"id": "a", "time": "2026-10-22T22:30:00Z"},
            {"id": "b", "time": "2026-10-23T09:00:00Z"},
        ])
        result = self.tools.call("get_food_entries", {
            "from_date": "2026-10-23", "to_date": "2026-10-23", "offset": 1, "limit": 1,
        })
        self.assertEqual(result["matchingEntries"], 2)
        self.assertEqual(result["entries"][0]["id"], "a")
        self.assertFalse(result["truncated"])

    def test_food_delete_preview_conflict_and_uncertain_retry(self):
        entry = self.store.food_action({
            "action": "add", "id": str(uuid.uuid4()), "time": "2026-10-01T12:00:00Z",
            "name": "Meal", "calories": 500, "protein_g": 30, "carbs_g": 40, "fat_g": 10,
        })["entry"]
        self.tools.data["foodLog"] = [entry]
        result = self.tools.call("propose_food_delete", {"entry_id": entry["id"]})
        body = self.body(result)
        self.assertEqual(self.store.food_entries(), [entry])
        bot = Bot(Mock(), lambda: [], self.root / "bot.json", "42", food_action=self.store.food_action)
        bot.state["pendingEdits"] = deepcopy(self.tools.state["pendingEdits"])
        bot.handle_edit("edit:cancel:" + result["draftId"])
        self.assertEqual(self.store.food_entries(), [entry])
        bot.state["pendingEdits"] = deepcopy(self.tools.state["pendingEdits"])
        bot.handle_edit("edit:save:" + result["draftId"])
        self.assertEqual(self.store.food_entries(), [])
        self.assertNotIn("reply_markup", bot.api.call.call_args.args[1])
        self.assertTrue(self.store.food_action(dict(body, action="delete"))["ok"])
        with self.assertRaises(ValueError):
            self.store.food_action(dict(body, action="delete", requestId=str(uuid.uuid4())))
