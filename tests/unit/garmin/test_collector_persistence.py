"""Execute only collector definitions: never import its login/startup side effects."""

import ast
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import types
import unittest
from unittest.mock import Mock

PATH = Path(__file__).resolve().parents[3] / "src/reptrace/garmin/collector.py"


class CollectorPersistenceTests(unittest.TestCase):
    def definitions(self, names, **extra):
        tree = ast.parse(PATH.read_text())
        ns = {"logging": logging, **extra}
        exec(
            compile(
                ast.Module(
                    body=[
                        n
                        for n in tree.body
                        if isinstance(n, (ast.FunctionDef, ast.ClassDef))
                        and n.name in names
                    ],
                    type_ignores=[],
                ),
                str(PATH),
                "exec",
            ),
            ns,
        )
        return ns

    def test_false_and_exception_writes_never_report_success(self):
        class InfluxError(Exception):
            pass

        client = Mock()
        ns = self.definitions(
            {"DatabaseWriteError", "write_points_to_influxdb"},
            INFLUXDB_VERSION="1",
            TAG_MEASUREMENTS_WITH_USER_EMAIL=False,
            influxdbclient=client,
            InfluxDBClientError=InfluxError,
            InfluxDBError=InfluxError,
        )
        for failure in (False, InfluxError("private endpoint detail")):
            client.write_points.side_effect = (
                failure if isinstance(failure, Exception) else None
            )
            client.write_points.return_value = False
            with self.assertRaises(ns["DatabaseWriteError"]):
                ns["write_points_to_influxdb"]([{"measurement": "Example"}])
        client.write_points.side_effect = None
        client.write_points.return_value = True
        ns["write_points_to_influxdb"]([{"measurement": "Example"}])

    def test_restart_retries_old_skipped_dates_despite_newer_metric_samples(self):
        ns = self.definitions({"resume_partial_collection"}, datetime=datetime)
        latest = datetime(2026, 10, 25, 9, tzinfo=timezone.utc)
        resume = ns["resume_partial_collection"]
        self.assertEqual(
            resume(
                latest,
                {"result": "partial", "startDate": "2026-10-20"},
                timedelta(hours=2),
            ),
            datetime(2026, 10, 19, 22, tzinfo=timezone.utc),
        )
        for marker in (
            {"result": "updated", "startDate": "2026-10-20"},
            {"result": "partial", "startDate": "invalid"},
            {},
        ):
            self.assertEqual(resume(latest, marker, timedelta(hours=2)), latest)

    def test_missing_sleep_payload_does_not_crash_collection_or_invent_readings(self):
        client = Mock()
        ns = self.definitions({"get_sleep_data"}, garmin_obj=client)
        for payload in (
            None,
            {},
            {"dailySleepDTO": None},
            {"dailySleepDTO": {}},
            {"dailySleepDTO": {"sleepEndTimestampGMT": None}},
        ):
            client.get_sleep_data.return_value = payload
            self.assertEqual(ns["get_sleep_data"]("2026-10-01"), [])

    def test_partial_date_collection_keeps_retry_signal(self):
        class ConnectionFailure(Exception):
            pass

        class RateLimit(Exception):
            pass

        class AuthenticationFailure(Exception):
            pass

        marker = Mock()
        daily = Mock(side_effect=[None, ConnectionFailure("offline")])
        ns = self.definitions(
            {"DatabaseWriteError", "fetch_write_bulk"},
            time=Mock(),
            iter_days=lambda *_: ["2026-10-01", "2026-10-02"],
            get_last_sync=lambda: [],
            write_points_to_influxdb=Mock(),
            daily_fetch_write=daily,
            write_collector_marker=marker,
            RATE_LIMIT_CALLS_SECONDS=0,
            FETCH_FAILED_WAIT_SECONDS=0,
            GarminConnectTooManyRequestsError=RateLimit,
            GarminConnectConnectionError=ConnectionFailure,
            GarminConnectAuthenticationError=AuthenticationFailure,
            GarthHTTPError=ConnectionFailure,
            requests=types.SimpleNamespace(
                exceptions=types.SimpleNamespace(
                    HTTPError=ConnectionFailure,
                    ConnectionError=ConnectionFailure,
                    Timeout=ConnectionFailure,
                )
            ),
        )
        self.assertFalse(ns["fetch_write_bulk"]("2026-10-01", "2026-10-02"))
        marker.assert_called_once_with("partial", "2026-10-01", "2026-10-02")
        daily.side_effect = None
        self.assertTrue(ns["fetch_write_bulk"]("2026-10-01", "2026-10-02"))
        marker.assert_called_with("updated", "2026-10-01", "2026-10-02")


if __name__ == "__main__":
    unittest.main()
