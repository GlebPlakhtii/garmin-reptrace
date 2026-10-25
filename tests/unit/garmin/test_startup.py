"""CLI imports must never authenticate, mutate storage, or parse caller arguments."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from reptrace.garmin import collector


class StartupTests(unittest.TestCase):
    def test_imports_do_not_start_external_work(self):
        script = """
import logging
from unittest.mock import patch
before = logging.root.handlers[:]
with patch('dotenv.load_dotenv', side_effect=AssertionError('read environment file')), \\
     patch('garminconnect.Garmin', side_effect=AssertionError('authenticated')), \\
     patch('influxdb.InfluxDBClient', side_effect=AssertionError('database client')), \\
     patch('influxdb_client_3.InfluxDBClient3', side_effect=AssertionError('database client')), \\
     patch('argparse.ArgumentParser.parse_args', side_effect=AssertionError('parsed arguments')):
    import reptrace.garmin.collector
    import reptrace.exports.influx
assert logging.root.handlers == before
"""
        with tempfile.TemporaryDirectory() as directory:
            env = dict(
                os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[3] / "src")
            )
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_explicit_bulk_command_initializes_before_authentication(self):
        events = Mock()
        for success, code in ((True, 0), (False, 1)):
            with (
                self.subTest(success=success),
                patch.object(collector, "initialize", events.initialize),
                patch.object(collector, "garmin_login", events.login),
                patch.object(collector, "fetch_write_bulk", events.bulk),
                patch.object(collector, "MANUAL_START_DATE", "2024-01-01", create=True),
                patch.object(collector, "MANUAL_END_DATE", "2024-01-02", create=True),
            ):
                events.reset_mock()
                events.bulk.return_value = success
                with self.assertRaises(SystemExit) as stopped:
                    collector.main()
                self.assertEqual(stopped.exception.code, code)
                self.assertEqual(
                    [call[0] for call in events.mock_calls],
                    ["initialize", "login", "bulk"],
                )
                events.bulk.assert_called_once_with("2024-01-01", "2024-01-02")

    def test_initialization_without_override_file_configures_both_database_versions(
        self,
    ):
        import contextlib
        import io
        import logging

        for version in ("1", "3"):
            with (
                self.subTest(version=version),
                patch.dict(os.environ, {"INFLUXDB_VERSION": version}, clear=True),
                patch.object(collector.dotenv, "load_dotenv", return_value=False),
                patch.object(collector, "InfluxDBClient") as influx1,
                patch.object(collector, "InfluxDBClient3") as influx3,
                patch.object(logging.root, "handlers", []),
                patch.object(logging, "basicConfig"),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                collector.initialize()
                self.assertEqual(collector.INFLUXDB_VERSION, version)
                self.assertIsNone(collector.garmin_obj)
                if version == "1":
                    influx1.assert_called_once()
                    influx1.return_value.switch_database.assert_called_once_with(
                        "GarminStats"
                    )
                    influx1.return_value.write_points.assert_called_once()
                    influx3.assert_not_called()
                else:
                    influx3.assert_called_once()
                    influx3.return_value.write.assert_called_once()
                    influx1.assert_not_called()
