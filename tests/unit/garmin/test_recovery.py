"""Recovery reads stay local and retries preserve the original confirmation."""

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid
from zoneinfo import ZoneInfo

from reptrace.garmin.creation import build_session
from reptrace.garmin.integration import GarminIntegration
from reptrace.garmin.operations import OperationJournal
from reptrace.garmin.recovery import read_operations
from reptrace.storage.state import Conflict, WebState
from tests.unit.garmin.test_integration import fixture, session


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        environment = patch.dict(os.environ, {
            "STRENGTH_MUTATION_LOCK_PATH": str(self.root / "strength.lock"),
            "GARMIN_OPERATION_STATE_PATH": str(self.root / "operations.sqlite"),
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.local, self.remote = fixture()
        self.adapter = Mock()
        self.adapter.activity_sets.side_effect = lambda _: deepcopy(self.remote)
        self.adapter_factory = Mock(return_value=self.adapter)
        self.state = WebState(self.root / "state.sqlite")
        self.state.apply = Mock(return_value={"ok": True})
        self.factory = Mock(side_effect=AssertionError("Unexpected Influx access"))
        self.service = GarminIntegration(
            self.root / "operations.sqlite", self.state, self.factory,
            "synthetic", ZoneInfo("UTC"), self.adapter_factory,
        )
        self.service.local = lambda _: deepcopy(self.local)

    def correction(self, **values):
        details = self.service.details("123")
        operation = self.service.preview({
            "requestId": str(uuid.uuid4()), "activityId": "123",
            "localRevision": details["localRevision"],
            "remoteRevision": details["remoteRevision"],
            "changes": [{"setId": "123:2", "load": 22.5, "unit": "kg"}],
        })
        operation.update(values)
        self.service.journal.save(operation)
        self.adapter.reset_mock()
        self.adapter_factory.reset_mock()
        return operation

    def resume(self, identity, **values):
        return self.service.call({
            "operation": "integration_resume", "requestId": identity, **values,
        })

    def test_missing_history_and_invalid_identity_do_not_create_storage(self):
        journal = OperationJournal(self.root / "absent" / "operations.sqlite")
        self.assertEqual(read_operations(journal), {"operations": []})
        for identity in ("not-a-uuid", "", str(uuid.uuid4())):
            with self.assertRaises(ValueError):
                read_operations(journal, identity)
        self.assertFalse(journal.path.parent.exists())

    def test_history_is_read_only_prioritizes_unfinished_and_omits_raw_responses(self):
        pending = self.correction(
            status="local_pending", destination="both", remoteStatus="saved",
            localStatus="pending", localError="raw-private-error",
            remoteReadback={"access_token": "private-token"},
            original={"credentials": "private-original"},
        )
        completed = self.service.journal.stage(
            str(uuid.uuid4()), "creation", {}, {
                "preview": "Synthetic new workout", "selection": [0],
                "device": {"id": "private-device-id", "name": "Synthetic watch"},
                "items": [{
                    "payload": {"workoutName": "Synthetic A", "credentials": "private-payload"},
                    "creation": "saved", "delivery": "requested",
                    "deliveryResponse": {"secret": "private-delivery"},
                }],
            },
        )
        completed["status"] = "done"
        completed["localError"] = "save_failed"
        self.service.journal.save(completed)
        path = self.service.journal.path
        before = path.read_bytes(), path.stat().st_mtime_ns, sorted(self.root.iterdir())
        history = read_operations(self.service.journal)
        self.assertEqual([op["id"] for op in history["operations"]], [pending["id"], completed["id"]])
        self.assertTrue(history["operations"][0]["canResume"])
        self.assertFalse(history["operations"][1]["canResume"])
        self.assertIsNone(history["operations"][1]["localError"])
        self.assertIsNone(history["operations"][0]["localError"])
        self.assertEqual(history["operations"][1]["items"][0]["name"], "Synthetic A")
        self.assertEqual(read_operations(self.service.journal, pending["id"]), history["operations"][0])
        self.assertNotIn("private-", json.dumps(history))
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns, sorted(self.root.iterdir())), before)
        self.adapter_factory.assert_not_called()
        self.factory.assert_not_called()

    def test_preview_cancelled_and_unconfirmed_operations_cannot_resume(self):
        for values in ({"status": "preview"}, {"status": "cancelled"}, {"status": "local_pending"}):
            operation = self.correction(**values)
            before = self.service.journal.get(operation["id"])
            with self.assertRaises(Conflict):
                self.resume(operation["id"])
            self.assertEqual(self.service.journal.get(operation["id"]), before)
            self.adapter_factory.assert_not_called()
            self.state.apply.assert_not_called()
            # Resolve the synthetic row before staging the next test case.
            operation["status"] = "cancelled"
            self.service.journal.save(operation)

    def test_resume_rejects_changed_confirmation_and_invalid_identity(self):
        operation = self.correction(status="local_pending", destination="local")
        for values in ({"destination": "both"}, {"destination": "local"}, {"selection": [0]}):
            with self.assertRaisesRegex(ValueError, "original confirmed"):
                self.resume(operation["id"], **values)
        for identity in ("invalid-uuid", None, 123, True):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                self.resume(identity)
        with self.assertRaises(ValueError):
            self.service.call({"operation": "integration_resume"})
        self.assertEqual(self.service.journal.get(operation["id"]), operation)
        self.adapter_factory.assert_not_called()
        self.state.apply.assert_not_called()

    def test_local_recovery_keeps_destination_and_completed_retry_does_nothing(self):
        operation = self.correction(status="local_pending", destination="local")
        result = self.resume(operation["id"])
        self.assertEqual((result["status"], result["destination"]), ("done", "local"))
        self.state.apply.assert_called_once_with(
            operation["localBody"], self.factory, "synthetic", ZoneInfo("UTC"),
        )
        self.assertEqual(self.resume(operation["id"]), result)
        self.state.apply.assert_called_once()
        self.adapter_factory.assert_not_called()

    def test_uncertain_correction_reconciles_without_repeating_remote_write(self):
        operation = self.correction(
            status="remote_unresolved", destination="both", remoteStatus="uncertain",
        )
        self.assertEqual(self.resume(operation["id"])["status"], "remote_unresolved")
        self.state.apply.assert_not_called()
        self.remote = deepcopy(operation["proposed"])
        result = self.resume(operation["id"])
        self.assertEqual(result["status"], "done")
        self.adapter.update_activity_sets.assert_not_called()
        self.state.apply.assert_called_once()
        self.adapter_factory.reset_mock()
        self.assertEqual(self.resume(operation["id"]), result)
        self.adapter_factory.assert_not_called()

    def test_creation_recovery_uses_only_original_selection_and_does_not_repeat_delivery(self):
        items = []
        for index, name in enumerate(("Unselected", "Selected")):
            payload, _ = build_session(session(name))
            items.append({
                "payload": payload, "workoutId": index + 101,
                "creation": "saved" if index else "not_started",
                "delivery": "uncertain" if index else "not_started",
            })
        operation = self.service.journal.stage(str(uuid.uuid4()), "creation", {}, {
            "selection": [1], "items": items, "device": {"id": 99, "name": "Synthetic watch"},
        })
        operation["status"] = "partial"
        self.service.journal.save(operation)
        self.adapter.device_messages.return_value = []
        self.assertEqual(self.resume(operation["id"])["status"], "partial")
        self.adapter.device_messages.return_value = [{"deviceId": 99, "metaDataId": 102}]
        result = self.resume(operation["id"])
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["items"][0]["creation"], "not_started")
        self.assertFalse(result["items"][0]["selected"])
        self.assertTrue(result["items"][1]["selected"])
        self.adapter.create.assert_not_called()
        self.adapter.deliver.assert_not_called()
        self.adapter_factory.reset_mock()
        self.assertEqual(self.resume(operation["id"]), result)
        self.adapter_factory.assert_not_called()
