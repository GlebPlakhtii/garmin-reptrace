from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
import json
import sys
import threading
import unittest
from unittest.mock import Mock, patch

from reptrace.web import server as web


class ActionHandlerTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.state = Mock()
        self.state.apply.return_value = {"ok": True}
        self.patch = patch.object(web, "STATE", self.state)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def send(self, body="{}", headers=None, path="/api/actions"):
        client = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        client.request(
            "POST",
            path,
            body=body,
            headers=headers or {"Content-Type": "application/json"},
        )
        response = client.getresponse()
        data = response.read()
        client.close()
        return response.status, json.loads(data)

    def test_untrusted_hosts_cannot_read_training_data_or_exports(self):
        with patch.object(web, "STORE") as store:
            for path in (
                "/api/data",
                "/api/health",
                "/api/sessions.xlsx?full=1",
                "/api/plan.png?type=upper1",
                "/",
            ):
                client = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
                client.request("GET", path, headers={"Host": "untrusted.example"})
                response = client.getresponse()
                response.read()
                client.close()
                self.assertEqual(response.status, 403, path)
            store.get.assert_not_called()
            store.full_export.assert_not_called()

    def test_origin_must_be_http_and_configured_hosts_remain_usable(self):
        port = self.server.server_port
        for origin in (
            "null",
            f"file://localhost:{port}",
            f"https://user@localhost:{port}",
        ):
            self.assertEqual(
                self.send(
                    headers={"Content-Type": "application/json", "Origin": origin}
                )[0],
                403,
            )
        with patch.dict("os.environ", {"WEB_ALLOWED_HOSTS": "form.test:3001"}):
            self.assertEqual(
                self.send(
                    headers={
                        "Content-Type": "application/json",
                        "Host": "form.test:3001",
                        "Origin": "http://form.test:3001",
                    }
                )[0],
                200,
            )

    def test_garmin_endpoint_shares_origin_guard_and_passes_server_plans(self):
        with (
            patch.object(web, "GARMIN_WORKOUTS") as service,
            patch.object(web, "STORE") as store,
        ):
            service.call.return_value = {"workouts": []}
            status, result = self.send(
                '{"operation":"list"}', path="/api/garmin-workouts"
            )
            self.assertEqual((status, result), (200, {"workouts": []}))
            service.call.assert_called_once_with({"operation": "list"}, [])
            store.get.assert_not_called()
            self.assertEqual(
                self.send(
                    path="/api/garmin-workouts",
                    headers={
                        "Content-Type": "application/json",
                        "Origin": "https://elsewhere.example",
                    },
                )[0],
                403,
            )
            self.assertEqual(service.call.call_count, 1)
            store.get.return_value = ({"nextSessions": [{"type": "upper1"}]}, b"", b"")
            self.send(
                '{"operation":"preview","workoutId":123,"planType":"upper1"}',
                path="/api/garmin-workouts",
            )
            store.get.assert_called_once_with(force=True)
            self.assertEqual(service.call.call_args.args[1], [{"type": "upper1"}])
            store.get.reset_mock()
            service.call.return_value = {"plannedSets": []}
            self.assertEqual(
                self.send(
                    '{"operation":"review","workoutName":"Upper 1","sessionTime":"2026-10-20T10:00:00Z"}',
                    path="/api/garmin-workouts",
                )[0],
                200,
            )
            store.get.assert_not_called()

    def test_database_endpoint_is_read_only_and_uses_same_origin_guard(self):
        with patch.object(web, "DatabaseReader") as reader:
            reader.return_value.call.return_value = {"rows": [{"value": 154}]}
            status, result = self.send(
                '{"operation":"query","table":"HRV_Intraday","fields":["hrvValue"],"aggregate":"max"}',
                path="/api/database",
            )
            self.assertEqual((status, result), (200, {"rows": [{"value": 154}]}))
            reader.return_value.call.assert_called_once_with(
                "query", table="HRV_Intraday", fields=["hrvValue"], aggregate="max"
            )
            self.state.apply.assert_not_called()
            self.assertEqual(
                self.send(
                    path="/api/database",
                    headers={
                        "Content-Type": "application/json",
                        "Origin": "https://elsewhere.example",
                    },
                )[0],
                403,
            )
            self.assertEqual(reader.return_value.call.call_count, 1)
            reader.return_value.call.side_effect = ValueError("Unknown column")
            self.assertEqual(
                self.send('{"operation":"query"}', path="/api/database"),
                (400, {"error": "Unknown column"}),
            )
            reader.return_value.call.side_effect = RuntimeError("offline")
            self.assertEqual(
                self.send('{"operation":"query"}', path="/api/database")[0], 503
            )

    def test_food_endpoint_uses_local_origin_guard_and_storage(self):
        self.state.food_action.return_value = {
            "ok": True,
            "entry": {"name": "Banana", "calories": 105},
        }
        status, result = self.send('{"action":"add","id":"example"}', path="/api/food")
        self.assertEqual(
            (status, result),
            (200, {"ok": True, "entry": {"name": "Banana", "calories": 105}}),
        )
        self.state.food_action.assert_called_once_with(
            {"action": "add", "id": "example"}
        )
        self.assertEqual(
            self.send(
                path="/api/food",
                headers={
                    "Content-Type": "application/json",
                    "Origin": "https://elsewhere.example",
                },
            )[0],
            403,
        )
        self.assertEqual(self.state.food_action.call_count, 1)

    def test_cross_origin_and_non_json_never_reach_storage(self):
        self.assertEqual(
            self.send(
                headers={
                    "Content-Type": "application/json",
                    "Origin": "https://elsewhere.example",
                }
            )[0],
            403,
        )
        self.assertEqual(self.send(headers={"Content-Type": "text/plain"})[0], 415)
        self.state.apply.assert_not_called()

    def test_invalid_json_and_nonfinite_never_reach_storage(self):
        for body in ["{", '{"weight":NaN}']:
            self.assertEqual(self.send(body)[0], 400)
        self.state.apply.assert_not_called()

    def test_valid_actions_and_conflicts_have_explicit_status(self):
        self.assertEqual(self.send('{"action":"goal_save"}'), (200, {"ok": True}))
        self.state.apply.side_effect = web.Conflict("Reload this workout")
        self.assertEqual(self.send()[0], 409)


if __name__ == "__main__":
    unittest.main()
