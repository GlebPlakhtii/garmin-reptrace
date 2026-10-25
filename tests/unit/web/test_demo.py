"""Synthetic fixture and publication boundary checks."""

from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import os
import threading
import unittest
from unittest.mock import patch

from reptrace.web import demo, server as web
from reptrace.web.demo import DemoClient, sample_records
from reptrace.storage.manual_import import reviewed_records


class DemoTests(unittest.TestCase):
    def test_rejected_save_closes_connection_and_reload_still_works(self):
        with (
            patch.dict(os.environ),
            patch("sys.argv", ["garmin-reptrace-demo", "--port", "0", "--empty"]),
            patch.object(demo, "ThreadingHTTPServer") as server_factory,
            patch.object(web, "STORE"),
        ):
            demo.main()
            handler = server_factory.call_args.args[1]
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        try:
            for extra_headers in ({}, {"Origin": "https://elsewhere.example"}):
                client.request(
                    "POST",
                    "/api/actions",
                    body='{"action":"goal_save"}',
                    headers={"Content-Type": "application/json", **extra_headers},
                )
                response = client.getresponse()
                response.read()
                self.assertEqual(response.status, 403)
                self.assertEqual(response.getheader("Connection"), "close")
                self.assertIsNone(client.sock)
                client.request("GET", "/")
                response = client.getresponse()
                page = response.read()
                self.assertEqual(response.status, 200)
                self.assertIn(b"<!doctype html>", page.lower())
        finally:
            client.close()
            server.shutdown()
            server.server_close()
            thread.join()

    def test_synthetic_history_is_deterministic_and_self_contained(self):
        today = datetime(2024, 4, 10, 9, tzinfo=timezone.utc)
        records = sample_records(today)
        self.assertEqual(records, sample_records(today))
        self.assertEqual(len(records["ActivitySummary"]), 48)
        self.assertEqual(len(records["StrengthSet"]), 720)
        self.assertEqual(len(records["SleepSummary"]), 100)
        self.assertTrue(
            all(row["ActivityID"].startswith("demo-") for row in records["StrengthSet"])
        )
        first = records["StrengthSet"][0]
        self.assertEqual(
            (first["weightKg"], first["reps"], first["volumeKg"]), (50, 8, 400)
        )
        client = DemoClient(records)
        self.assertEqual(
            client.query('SELECT * FROM "StrengthSet"'), records["StrengthSet"]
        )
        self.assertEqual(client.query('SELECT * FROM "Unrecognized"'), [])

    def test_review_profile_rejects_broad_or_unexplained_changes(self):
        for rule in (
            {"match": {"exercise": "Example"}, "skipReason": "Too broad"},
            {
                "match": {"session": "1", "date": "2024-01-01", "exercise": "Example"},
                "replace": {"sets": 0},
            },
            {
                "match": {"session": "1", "date": "2024-01-01", "exercise": "Example"},
                "replace": {"weights": ["1"]},
            },
        ):
            with self.assertRaises(ValueError):
                list(reviewed_records([], {"rules": [rule]}))
