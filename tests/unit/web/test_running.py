"""Synthetic activity summaries; no external account or persistent writes."""

import json
import unittest
from unittest.mock import Mock

from reptrace.web.server import build_payload, DataStore
from reptrace.web.demo import DemoClient, sample_records


class RunningTests(unittest.TestCase):
    def test_running_types_units_and_local_dates_are_separate_from_strength(self):
        rows = [
            {
                "ActivityID": "123",
                "time": "2026-11-01T23:30:00Z",
                "activityType": kind,
                "distance": 5000,
                "movingDuration": 1500,
                "elapsedDuration": 1800,
                "averageHR": 142,
                "sourceHash": "private",
                "activityUrl": "javascript:bad",
            }
            for kind in (
                "running",
                "trail_running",
                "treadmill_running",
                "cycling",
                "No Activity",
                "strength_training",
            )
        ]
        payload = build_payload([], [], [], raw_runs=rows)
        self.assertEqual(len(payload["runs"]), 3)
        run = payload["runs"][0]
        self.assertEqual(run["distanceKm"], 5)
        self.assertEqual(run["movingSeconds"], 1500)
        self.assertEqual(run["elapsedSeconds"], 1800)
        self.assertEqual(run["url"], "https://connect.garmin.com/modern/activity/123")
        from reptrace.web.server import local_date

        self.assertEqual(run["date"], local_date(rows[0]["time"]))
        self.assertEqual(payload["workouts"], [])
        self.assertEqual(payload["sets"], [])
        self.assertNotIn("private", json.dumps(payload))
        self.assertNotIn("javascript", json.dumps(payload))

    def test_missing_negative_and_nonfinite_measurements_are_not_zero(self):
        row = {
            "ActivityID": "demo",
            "time": "2026-11-01T10:00:00Z",
            "activityType": "running",
            "distance": -10,
            "movingDuration": float("nan"),
            "averageHR": True,
            "calories": 0,
        }
        run = build_payload([], [], [], raw_runs=[row])["runs"][0]
        for key in ("distanceKm", "movingSeconds", "elapsedSeconds", "averageHR"):
            self.assertIsNone(run[key])
        self.assertEqual(run["calories"], 0)
        self.assertEqual(run["url"], "")
        json.dumps(run, allow_nan=False)

    def test_datastore_loads_running_history_without_changing_strength_counts(self):
        client = DemoClient(sample_records())
        query = Mock(wraps=client.query)
        payload = DataStore(lambda: (client, query)).get()[0]
        self.assertEqual(len(payload["runs"]), 24)
        self.assertEqual(len(payload["workouts"]), 48)
        self.assertEqual(len(payload["sets"]), 720)
        self.assertTrue(
            any("_running$" in call.args[0] for call in query.call_args_list)
        )
        self.assertTrue(payload["sync"]["sources"]["Running activities"])


class RunningHTTPTests(unittest.TestCase):
    def test_import_route_validates_membership_and_origin_before_external_reads(self):
        from http.client import HTTPConnection
        from http.server import ThreadingHTTPServer
        from threading import Thread
        from unittest.mock import patch
        from reptrace.web import server as web

        run = {"id": "123", "type": "running", "name": "Run", "date": "2026-11-01"}
        fake = Mock()
        fake.get.return_value = {"summary": run, "samples": [], "laps": [], "zones": []}
        with (
            patch.object(web.STORE, "get", return_value=({"runs": [run]}, b"", b"")),
            patch.object(web, "RUNNING_STORE", fake),
        ):
            server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                for body, origin, status in [
                    ({"id": "999"}, None, 400),
                    ({"id": "123"}, "https://untrusted.example", 403),
                    ({"id": "123", "refresh": "yes"}, None, 400),
                    ({"id": "123"}, None, 200),
                ]:
                    headers = {"Content-Type": "application/json"}
                    if origin:
                        headers["Origin"] = origin
                    connection.request(
                        "POST", "/api/running", body=json.dumps(body), headers=headers
                    )
                    response = connection.getresponse()
                    response.read()
                    self.assertEqual(response.status, status)
                fake.get.assert_called_once_with(run, refresh=False)
                run["detailsSyncedAt"] = "2026-11-01T12:00:00Z"
                for stamp, changed in [
                    (run["detailsSyncedAt"], False),
                    (None, False),
                    ("2026-11-02T12:00:00Z", True),
                ]:
                    with patch.object(web.STORE, "run_summaries_changed", False):
                        fake.get.return_value["syncedAt"] = stamp
                        connection.request("POST", "/api/running", body='{"id":"123"}',
                                           headers={"Content-Type": "application/json"})
                        response = connection.getresponse()
                        response.read()
                        self.assertEqual(response.status, 200)
                        self.assertEqual(web.STORE.run_summaries_changed, changed)
            finally:
                connection.close()
                server.shutdown()
                server.server_close()
                thread.join()
