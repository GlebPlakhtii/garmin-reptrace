"""Backfill must leave interactive writers free while a Garmin request is in flight."""

from concurrent.futures import ThreadPoolExecutor
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from reptrace.garmin import backfill
from reptrace.storage.coordination import strength_lock


class BackfillTests(unittest.TestCase):
    def test_intervening_review_wins_over_fetched_points(self):
        client = Mock()
        activity = {
            "Activity_ID": 10,
            "activityName": "Synthetic",
            "time": "2026-11-01T10:00:00Z",
        }
        reviewed = False

        def query(statement):
            if "ActivitySummary" in statement:
                rows = [activity]
            else:
                self.assertIn("StrengthManualSession", statement)
                rows = [{"importedSets": 1}] if reviewed else []
            result = Mock()
            result.get_points.return_value = iter(rows)
            return result

        def review_workout():
            nonlocal reviewed
            with strength_lock(timeout=0):
                reviewed = True

        def fetch(_):
            with ThreadPoolExecutor(1) as writer:
                writer.submit(review_workout).result(timeout=3)
            return {"exerciseSets": [{"setType": "ACTIVE", "repetitionCount": 5}]}

        client.query.side_effect = query
        garmin = Mock()
        garmin.get_activity_exercise_sets.side_effect = fetch
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(
                os.environ,
                {
                    "INFLUXDB_VERSION": "1",
                    "STRENGTH_MUTATION_LOCK_PATH": folder + "/write.lock",
                    "GARMIN_OPERATION_STATE_PATH": folder + "/operations.sqlite",
                },
            ),
            patch.object(backfill, "InfluxDBClient", return_value=client),
            patch.object(backfill, "Garmin", return_value=garmin),
            patch("sys.argv", ["backfill", "--delay", "0"]),
        ):
            backfill.main()
        garmin.get_activity_exercise_sets.assert_called_once_with(10)
        client.write_points.assert_not_called()
        client.close.assert_called_once()
