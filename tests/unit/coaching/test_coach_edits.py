from copy import deepcopy
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
import json, sys, tempfile, unittest, uuid
from unittest.mock import Mock, patch

from reptrace.coaching.assistant import TrainingTools
from reptrace.coaching.edits import stage
from reptrace.telegram.bot import Bot
from reptrace.web.server import DataStore
from reptrace.storage.state import (
    WebState,
    Conflict,
    plan_workout,
    snapshot_rows,
    revision,
)
from tests.unit.storage.test_web_storage import fixture, CATALOG, ZONE, request
from tests.unit.reports.test_training_reports import records


def workout_args(**changes):
    return (
        dict(
            session_id="c",
            operation="save",
            date=None,
            name=None,
            duration_minutes=None,
            set_changes=[],
            **changes,
        )
        if not changes
        else dict(workout_args(), **changes)
    )


def change(**changes):
    return dict(
        dict(
            operation="update",
            set_id=None,
            exercise=None,
            weight=None,
            reps=None,
            note=None,
            clear_fields=[],
        ),
        **changes,
    )


class DraftTests(unittest.TestCase):
    def tools(self):
        data = records()
        for w in data["workouts"]:
            w["revision"] = "rev"
        data["metadataRevision"] = "meta"
        return TrainingTools(
            data, {}, today=date(2026, 10, 22), request_id="turn", save_action=Mock()
        )

    def test_update_preserves_unknown_and_untargeted_sets_and_does_not_write(self):
        t = self.tools()
        row = deepcopy(t.data["sets"][-1])
        row.update(id="hidden", exercise="Unknown")
        t.data["sets"].append(row)
        key = next(r["id"] for r in t.data["sets"] if r["sessionId"] == "c")
        before = deepcopy(t.data)
        result = t.call(
            "propose_workout_change",
            workout_args(set_changes=[change(set_id=key, weight=82.5)]),
        )
        body = t.state["pendingEdits"][result["draftId"]]["body"]
        self.assertFalse(result["saved"])
        t.save_action.assert_not_called()
        self.assertEqual(t.data, before)
        self.assertTrue(any(r["id"] == "hidden" for r in body["sets"]))
        self.assertEqual(
            next(r for r in body["sets"] if r["id"] == key)["weight"], 82.5
        )
        self.assertEqual(
            t.call(
                "propose_workout_change",
                workout_args(set_changes=[change(set_id=key, weight=82.5)]),
            )["draftId"],
            result["draftId"],
        )

    def test_set_add_delete_and_explicit_clear(self):
        t = self.tools()
        key = next(r["id"] for r in t.data["sets"] if r["sessionId"] == "c")
        result = t.call(
            "propose_workout_change",
            workout_args(
                set_changes=[
                    change(set_id=key, clear_fields=["reps"]),
                    change(operation="add", exercise="New exercise", weight=10, reps=8),
                ]
            ),
        )
        body = t.state["pendingEdits"][result["draftId"]]["body"]
        self.assertIsNone(next(r for r in body["sets"] if r.get("id") == key)["reps"])
        self.assertEqual(body["sets"][-1]["exercise"], "New exercise")
        with self.assertRaises(ValueError):
            t.call(
                "propose_workout_change",
                workout_args(set_changes=[change(set_id="invented", weight=80)]),
            )
        with self.assertRaises(ValueError):
            t.call(
                "propose_workout_change",
                workout_args(set_changes=[change(set_id=key), change(set_id=key)]),
            )

    def test_repeated_proposal_preserves_confirmation_and_expiry(self):
        for status in ("pending", "saving", "saved", "cancelled", "undone"):
            with self.subTest(status=status):
                tools = self.tools()
                tools.save = Mock()
                body = {
                    "action": "garmin_workout_creation",
                    "operationId": "synthetic",
                }
                result = stage(tools, body, ["Reviewed synthetic workout"])
                draft = tools.state["pendingEdits"][result["draftId"]]
                draft.update(
                    status=status,
                    expires="2000-01-01T00:00:00+00:00",
                    destination="both",
                    selection=[1],
                    result={"status": "partial"},
                )
                before = deepcopy(draft)
                tools.save.reset_mock()
                repeated = stage(tools, body, ["Regenerated preview"])
                self.assertEqual(draft, before)
                self.assertEqual(
                    tools.state["pendingEdits"][result["draftId"]], before
                )
                self.assertEqual(repeated["status"], status)
                self.assertEqual(repeated["saved"], status == "saved")
                self.assertEqual(repeated["preview"], "Reviewed synthetic workout")
                tools.save.assert_not_called()

    def test_pending_save_survives_preview_retention(self):
        tools = self.tools()
        result = stage(
            tools,
            {"action": "garmin_workout_creation", "operationId": "original"},
            ["Original"],
        )
        draft = tools.state["pendingEdits"][result["draftId"]]
        draft["status"] = "saving"
        for index in range(35):
            stage(
                tools,
                {"action": "garmin_workout_creation", "operationId": str(index)},
                ["Synthetic"],
            )
        self.assertIs(tools.state["pendingEdits"][result["draftId"]], draft)

    def test_delete_and_new_session_have_reviewable_payloads(self):
        t = self.tools()
        r = t.call("propose_workout_change", workout_args(operation="delete"))
        self.assertEqual(
            t.state["pendingEdits"][r["draftId"]]["body"]["action"], "workout_delete"
        )
        r = t.call(
            "propose_workout_change",
            workout_args(
                session_id=None,
                name="Lower 1",
                date="2026-10-21",
                set_changes=[
                    change(operation="add", exercise="Squat", weight=90, reps=5)
                ],
            ),
        )
        self.assertNotIn("sessionId", t.state["pendingEdits"][r["draftId"]]["body"])

    def test_metadata_preview_includes_exact_before_and_after(self):
        t = self.tools()
        t.data["progressionRules"] = {
            "Curl": {"repMin": 8, "repMax": 12, "weightStep": 1}
        }
        r = t.call(
            "propose_record_change",
            {
                "entity": "progression",
                "operation": "save",
                "key": "Curl",
                "value_json": '{"repMin":6,"repMax":10,"weightStep":2}',
            },
        )
        self.assertIn('"repMin": 8', r["preview"])
        self.assertIn('"repMin": 6', r["preview"])
        t.save_action.assert_not_called()


class MetadataTests(unittest.TestCase):
    def test_metadata_crud_stale_rejection_and_undo(self):
        with tempfile.TemporaryDirectory() as d:
            state = WebState(Path(d) / "state.sqlite")

            def save(entity, key, value, operation="save"):
                body = request(
                    action="metadata_change",
                    metadataRevision=state.read()["metadataRevision"],
                    entity=entity,
                    key=key,
                    value=value,
                    operation=operation,
                )
                state.apply(body, None, "Test", ZONE)
                return body

            initial = state.read()
            goal = save(
                "goal",
                None,
                dict(exercise="Bench Press", weight=100, reps=5, mode="load_reps"),
            )
            self.assertEqual(
                state.read()["goals"][0]["exercise"], "Barbell Bench Press"
            )
            save("muscle", "Curl", "Biceps")
            rule = save("progression", "Curl", dict(repMin=6, repMax=10, weightStep=1))
            recovery = save("recovery", "2026-10-21", dict(sleepHours=8, hrv=60))
            self.assertEqual(state.read()["recoveryOverrides"]["2026-10-21"]["hrv"], 60)
            with self.assertRaises(Conflict):
                state.apply(
                    dict(recovery, requestId=str(uuid.uuid4())), None, "Test", ZONE
                )
            state.apply(
                request(action="undo_metadata", id=recovery["requestId"]),
                None,
                "Test",
                ZONE,
            )
            self.assertEqual(state.read()["recoveryOverrides"], {})
            with self.assertRaises(Conflict):
                state.apply(
                    request(action="undo_metadata", id=goal["requestId"]),
                    None,
                    "Test",
                    ZONE,
                )
            delete = save("goal", goal["requestId"], None, "delete")
            self.assertEqual(state.read()["goals"], [])
            state.apply(
                request(action="undo_metadata", id=delete["requestId"]),
                None,
                "Test",
                ZONE,
            )
            self.assertEqual(len(state.read()["goals"]), 1)
            before = state.read()
            with self.assertRaises(ValueError):
                save("recovery", "2026-10-21", dict(sleepHours=30))
            self.assertEqual(before, state.read())

    def test_metadata_edit_preserves_other_rules_and_null_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            state = WebState(Path(d) / "state.sqlite")
            for entity, key, value, op in [
                ("muscle", "Curl", "Biceps", "save"),
                ("muscle", "Press", "Chest", "save"),
                ("muscle", "Curl", None, "delete"),
                ("recovery", "2026-10-21", {"hrv": None}, "save"),
            ]:
                body = request(
                    action="metadata_change",
                    metadataRevision=state.read()["metadataRevision"],
                    entity=entity,
                    key=key,
                    value=value,
                    operation=op,
                )
                state.apply(body, None, "Test", ZONE)
            self.assertEqual(state.read()["muscleOverrides"], {"Press": "Chest"})
            self.assertIsNone(state.read()["recoveryOverrides"]["2026-10-21"]["hrv"])

    def test_recovery_overrides_merge_without_mutating_raw_readings(self):
        sleep = [
            {
                "time": "2026-10-21T00:00:00Z",
                "sleepTimeSeconds": 25200,
                "avgOvernightHrv": 50,
            }
        ]
        original = deepcopy(sleep)
        metadata = Mock()
        metadata.read.return_value = {
            "recoveryOverrides": {
                "2026-10-21": {"hrv": None, "sleepHours": 8},
                "2026-10-20": {"restingHR": 48},
            }
        }

        def query(q):
            return sleep if "SleepSummary" in q else []

        data = DataStore(lambda: (Mock(), query), state_store=metadata).get()[0]
        self.assertEqual(sleep, original)
        self.assertEqual(data["recovery"][0]["restingHR"], 48)
        self.assertEqual(data["recovery"][1]["sleepHours"], 8)
        self.assertIsNone(data["recovery"][1]["hrv"])
        self.assertTrue(data["recovery"][1]["manualOverride"])

    def test_manual_body_weight_is_validated_and_undoable(self):
        with tempfile.TemporaryDirectory() as d:
            state = WebState(Path(d) / "state.sqlite")
            body = request(
                action="metadata_change",
                metadataRevision=state.read()["metadataRevision"],
                entity="recovery",
                key="2026-10-21",
                value={"bodyWeightKg": 72.9},
                operation="save",
            )
            state.apply(body, None, "Test", ZONE)
            self.assertEqual(
                state.read()["recoveryOverrides"]["2026-10-21"]["bodyWeightKg"], 72.9
            )
            state.apply(
                request(action="undo_metadata", id=body["requestId"]),
                None,
                "Test",
                ZONE,
            )
            self.assertEqual(state.read()["recoveryOverrides"], {})

    def test_workout_metadata_edits_update_sets_and_preserve_hr(self):
        before = fixture()
        body = request(
            revision=revision(snapshot_rows(before)),
            name="Upper 1",
            date="2026-10-02",
            durationMinutes=45,
            sets=[dict(id="123:1", exercise="Barbell Bench Press", weight=80, reps=5)],
        )
        _, points, _ = plan_workout(
            body, before, CATALOG, "Test", ZONE, body["requestId"]
        )
        summary = next(p for p in points if p["measurement"] == "ActivitySummary")
        self.assertEqual(summary["fields"]["averageHR"], 122)
        self.assertEqual(summary["fields"]["elapsedDuration"], 2700)
        self.assertEqual(summary["fields"]["activityName"], "Upper 1")
        self.assertTrue(summary["time"].startswith("2026-10-02"))
        self.assertEqual(snapshot_rows(points)[0]["sourceDate"], "2026-10-02")


class ConfirmationTests(unittest.TestCase):
    def setup_bot(self, d):
        bot = Bot(Mock(), lambda: [], Path(d) / "state.json", "42", fetch_data=records)
        identity = str(uuid.uuid4())
        bot.state["pendingEdits"] = {
            identity: {
                "body": dict(
                    action="workout_delete",
                    requestId=identity,
                    sessionId="c",
                    revision="rev",
                ),
                "preview": "Delete session c",
                "expires": (
                    datetime.now(timezone.utc) + timedelta(hours=1)
                ).isoformat(),
                "status": "pending",
            }
        }
        bot.save()
        return bot, identity

    def callback(self, identity, action="save", sender=42):
        return {
            "update_id": 5,
            "callback_query": {
                "id": "cb",
                "from": {"id": sender},
                "message": {"chat": {"id": sender, "type": "private"}},
                "data": f"edit:{action}:{identity}",
            },
        }

    @patch("reptrace.telegram.bot.save_action", return_value={"ok": True})
    def test_owner_only_confirmation_is_idempotent_and_undoable(self, save):
        with tempfile.TemporaryDirectory() as d:
            b, i = self.setup_bot(d)
            b.handle(self.callback(i, sender=99))
            save.assert_not_called()
            b.handle(self.callback(i))
            b.handle(self.callback(i))
            self.assertEqual(save.call_count, 1)
            self.assertEqual(b.state["pendingEdits"][i]["status"], "saved")
            b.handle(self.callback(i, "undo"))
            b.handle(self.callback(i, "undo"))
            self.assertEqual(save.call_count, 2)
            self.assertEqual(save.call_args.args[0]["action"], "undo_workout")
            b.handle(self.callback(i))
            self.assertEqual(save.call_count, 2)

    @patch("reptrace.telegram.bot.save_action")
    def test_cancel_expiry_and_conflict_prevent_writes(self, save):
        with tempfile.TemporaryDirectory() as d:
            b, i = self.setup_bot(d)
            b.handle(self.callback(i, "cancel"))
            b.handle(self.callback(i))
            save.assert_not_called()
            b.state["pendingEdits"][i]["status"] = "pending"
            b.state["pendingEdits"][i]["expires"] = "2000-01-01T00:00:00+00:00"
            b.handle(self.callback(i))
            save.assert_not_called()
            b.state["pendingEdits"][i]["expires"] = "2099-01-01T00:00:00+00:00"
            save.side_effect = ValueError("Stale preview")
            b.handle(self.callback(i))
            self.assertEqual(b.state["pendingEdits"][i]["status"], "pending")

    def test_chat_delivers_pending_preview_without_saving(self):
        with tempfile.TemporaryDirectory() as d:
            b, i = self.setup_bot(d)
            b.coach = Mock(configured=True)

            def answer(message, tools, history, on_text=None):
                tools.state["pendingEdits"][i]["turn"] = "turn"
                return {"text": "Please review and press Save.", "artifacts": []}

            b.coach.answer.side_effect = answer
            with patch("reptrace.telegram.bot.save_action") as save:
                b.handle_chat("delete last session", "turn")
                save.assert_not_called()
            calls = b.api.call.call_args_list
            self.assertTrue(
                any("PROPOSED CHANGE" in call.args[1].get("text", "") for call in calls)
            )
            self.assertEqual(b.state["pendingEdits"][i]["status"], "pending")

    def test_large_preview_escapes_html_and_attaches_full_details(self):
        with tempfile.TemporaryDirectory() as d:
            b, i = self.setup_bot(d)
            b.state["pendingEdits"][i]["preview"] = (
                "<script>bad()</script>" + "A" * 7000
            )
            b.send_edit_preview(i)
            calls = b.api.call.call_args_list
            self.assertEqual(calls[0].args[0], "sendDocument")
            self.assertNotIn(b"<script>", calls[0].kwargs["document"])
            self.assertIn("reply_markup", calls[-1].args[1])


if __name__ == "__main__":
    unittest.main()
