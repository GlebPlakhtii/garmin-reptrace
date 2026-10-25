"""Local HTTP coverage for recovery reads and the single catalog asset route."""

from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from importlib.resources import files
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import uuid
from zoneinfo import ZoneInfo

from reptrace.garmin.integration import GarminIntegration
from reptrace.garmin.operations import OperationJournal
from reptrace.web import server as web


class RecoveryHandlerTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "operations.sqlite"
        self.service = Mock()
        self.service.journal = OperationJournal(self.path)
        self.store = Mock()
        self.store.lock = threading.Lock()
        for target, value in (("GARMIN_INTEGRATION", self.service), ("STORE", self.store)):
            replacement = patch.object(web, target, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def get(self, path="/api/garmin-operations", headers=None):
        client = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            client.request("GET", path, headers=headers or {})
            response = client.getresponse()
            return response.status, response.read(), response.getheader("Content-Type")
        finally:
            client.close()

    def post(self, body):
        client = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            client.request("POST", "/api/garmin-workouts", json.dumps(body),
                           {"Content-Type": "application/json"})
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    def test_empty_local_history_does_not_create_journal_or_query_services(self):
        status, body, content_type = self.get()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"operations": []})
        self.assertTrue(content_type.startswith("application/json"))
        self.assertFalse(self.path.exists())
        self.store.get.assert_not_called()
        self.service.call.assert_not_called()
        self.service.adapter.assert_not_called()

    def test_origin_and_host_guard_runs_before_reading_operation_history(self):
        for headers in ({"Origin": "https://elsewhere.example"}, {"Host": "elsewhere.example"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.get(headers=headers)[0], 403)
        self.assertFalse(self.path.exists())
        self.service.call.assert_not_called()
        self.store.get.assert_not_called()

    def test_invalid_duplicate_and_unknown_operation_ids_are_validation_errors(self):
        identity = str(uuid.uuid4())
        for query in ("id=invalid", "id=", f"id={identity}", f"id={identity}&id={identity}"):
            with self.subTest(query=query):
                status, body, _ = self.get("/api/garmin-operations?" + query)
                self.assertEqual(status, 400)
                self.assertIn("error", json.loads(body))
        self.assertFalse(self.path.exists())

    def test_existing_operation_returns_sanitized_local_status(self):
        operation = self.service.journal.stage(str(uuid.uuid4()), "correction", {}, {
            "activityId": "123", "preview": "Synthetic correction",
            "remoteReadback": {"token": "private-token"},
        }, "123")
        operation.update(status="local_pending", destination="both", remoteStatus="saved", localError="raw-private-error")
        self.service.journal.save(operation)
        status, body, _ = self.get("/api/garmin-operations?id=" + operation["id"])
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result["id"], operation["id"])
        self.assertTrue(result["canResume"])
        self.assertIsNone(result["localError"])
        self.assertNotIn(b"private-", body)
        self.service.call.assert_not_called()
        self.service.adapter.assert_not_called()
        self.store.get.assert_not_called()

    def test_unavailable_journal_returns_sanitized_503(self):
        self.path.write_bytes(b"not a database; private-token")
        status, body, _ = self.get()
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body), {"error": "Operation history is temporarily unavailable."})
        self.assertNotIn(b"private-token", body)

    def test_resume_endpoint_validates_identity_and_completed_retry_is_local(self):
        forbidden = Mock(side_effect=AssertionError("Unexpected external access"))
        service = GarminIntegration(self.path, Mock(), forbidden, "synthetic", ZoneInfo("UTC"), forbidden)
        with patch.object(web, "GARMIN_INTEGRATION", service):
            for identity in ("invalid", None, 123, True):
                with self.subTest(identity=identity):
                    status, result = self.post({"operation": "integration_resume", "requestId": identity})
                    self.assertEqual(status, 400)
                    self.assertIn("error", result)
            self.assertEqual(self.post({"operation": "integration_resume"})[0], 400)
            self.assertFalse(self.path.exists())
            operation = service.journal.stage(str(uuid.uuid4()), "correction", {}, {
                "preview": "Synthetic correction", "destination": "local",
            })
            operation["status"] = "done"
            service.journal.save(operation)
            status, result = self.post({"operation": "integration_resume", "requestId": operation["id"]})
            self.assertEqual(status, 200)
            self.assertEqual(result["status"], "done")
            self.assertFalse(result["canResume"])
        forbidden.assert_not_called()
        self.store.get.assert_not_called()

    def test_only_exact_catalog_path_is_served_as_json(self):
        status, body, content_type = self.get("/training/exercise_catalog.json")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "application/json; charset=utf-8")
        self.assertEqual(body, files("reptrace.training").joinpath("exercise_catalog.json").read_bytes())
        self.assertEqual(json.loads(body)["schemaVersion"], 1)
        for path in (
            "/training/strength.py", "/training/__init__.py",
            "/training/../storage/state.py", "/training/%2e%2e/storage/state.py",
            "/training/exercise_catalog.json/../strength.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.get(path)[0], 404)
        self.assertEqual(self.get("/training/exercise_catalog.json", {"Origin": "https://elsewhere.example"})[0], 403)
        self.store.get.assert_not_called()
        self.service.call.assert_not_called()
