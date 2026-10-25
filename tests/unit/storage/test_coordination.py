from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

from reptrace.garmin.operations import OperationJournal
from reptrace.storage.coordination import protected_activity
from reptrace.storage.state import Conflict, WebState, revision, snapshot_rows
from tests.unit.storage.test_web_storage import fixture, request, ZONE


class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "operations.sqlite"
        self.environment = patch.dict(
            os.environ,
            {
                "GARMIN_OPERATION_STATE_PATH": str(self.path),
                "STRENGTH_MUTATION_LOCK_PATH": str(self.root / "strength.lock"),
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.journal = OperationJournal(self.path)
        self.state = WebState(self.root / "state.sqlite")
        self.before = fixture()
        self.body = request(
            action="workout_save",
            sessionId="123",
            revision=revision(snapshot_rows(self.before)),
            sets=[
                {
                    "id": "123:1",
                    "exercise": "Barbell Bench Press",
                    "weight": 85,
                    "reps": 5,
                }
            ],
        )

    def operation(self, **values):
        operation = self.journal.stage(
            str(uuid.uuid4()), "correction", {}, {"localBody": self.body}, "123"
        )
        operation.update(
            status="local_pending", destination="both", remoteStatus="saved", **values
        )
        self.journal.save(operation)
        return operation

    def test_absent_journal_is_not_created_and_default_path_is_checked(self):
        self.assertFalse(protected_activity("123"))
        self.assertFalse(self.path.exists())
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("reptrace.storage.coordination.Path.exists", return_value=True),
            patch("reptrace.garmin.operations.OperationJournal") as journal,
        ):
            journal.return_value.unresolved.return_value = [
                {"status": "remote_uncertain"}
            ]
            self.assertTrue(protected_activity("123"))
            journal.assert_called_once_with(
                Path("/var/lib/form/garmin-operations.sqlite")
            )

    def test_only_exact_reviewed_local_step_can_pass_an_unresolved_operation(self):
        operation = self.operation()
        self.assertTrue(protected_activity("123"))
        self.assertFalse(protected_activity("123", local_body=self.body))
        self.assertTrue(protected_activity("123", local_body=dict(self.body, sets=[])))
        operation.update(status="remote_uncertain", remoteStatus="uncertain")
        self.journal.save(operation)
        self.assertTrue(protected_activity("123", local_body=self.body))
        operation.update(destination="local")
        self.journal.save(operation)
        self.assertFalse(protected_activity("123", local_body=self.body))
        operation.update(status="done")
        self.journal.save(operation)
        self.assertFalse(protected_activity("123"))

    def test_pending_operation_blocks_save_delete_and_undo_before_influx_changes(self):
        self.operation()
        prior_id = str(uuid.uuid4())
        with self.state.connect() as db:
            db.execute(
                "INSERT INTO audit VALUES(?,?,?,?,?,?,?,?)",
                (
                    prior_id,
                    "workout_save",
                    "{}",
                    "[]",
                    "[]",
                    json.dumps({"sessionId": "123", "name": "Upper"}),
                    "done",
                    "2026-10-01",
                ),
            )
        client, query = Mock(), Mock()
        for body in (
            dict(self.body, requestId=str(uuid.uuid4())),
            request(
                action="workout_delete", sessionId="123", revision=self.body["revision"]
            ),
            request(action="undo_workout", id=prior_id),
        ):
            with (
                self.subTest(action=body["action"]),
                self.assertRaisesRegex(Conflict, "pending Garmin"),
            ):
                self.state.apply(body, lambda: (client, query), "Test", ZONE)
            with self.state.connect() as db:
                self.assertIsNone(
                    db.execute(
                        "SELECT id FROM audit WHERE id=?", (body["requestId"],)
                    ).fetchone()
                )
        query.assert_not_called()
        client.write_points.assert_not_called()
        client.query.assert_not_called()

    def test_approved_step_readback_and_interrupted_retry_remain_available(self):
        self.operation()
        current = deepcopy(self.before)
        client = Mock()
        query = Mock(return_value=[])

        def replace(_client, _identity, points):
            current[:] = deepcopy(points)

        with (
            patch(
                "reptrace.storage.state.snapshot",
                side_effect=lambda *_: deepcopy(current),
            ),
            patch(
                "reptrace.storage.state.replace_workout", side_effect=replace
            ) as write,
        ):
            result = self.state.apply(self.body, lambda: (client, query), "Test", ZONE)
            self.assertEqual(snapshot_rows(current)[0]["weightKg"], 85)
            with self.state.connect() as db:
                db.execute(
                    "UPDATE audit SET status='pending' WHERE id=?",
                    (self.body["requestId"],),
                )
            restarted = WebState(self.state.path)
            self.assertEqual(
                restarted.apply(self.body, lambda: (client, query), "Test", ZONE),
                result,
            )
            self.assertEqual(restarted.apply(self.body, None, "Test", ZONE), result)
            write.assert_called_once()
        with self.state.connect() as db:
            audit = db.execute(
                "SELECT * FROM audit WHERE id=?", (self.body["requestId"],)
            ).fetchone()
            self.assertEqual(audit["status"], "done")
            self.assertEqual(json.loads(audit["before_data"]), self.before)


if __name__ == "__main__":
    unittest.main()
