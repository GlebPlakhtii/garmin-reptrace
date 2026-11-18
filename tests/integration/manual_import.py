"""Verify reviewed TSV collision handling and interrupted imports in disposable Influx."""

import csv
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from influxdb import InfluxDBClient
from reptrace.storage import manual_import
from reptrace.training.strength import has_manual_strength_details
from reptrace.web.server import DataStore


class ImportIntegration(unittest.TestCase):
    def test_collision_then_interrupted_replacement_and_retry(self):
        name = "ImportReview_" + uuid.uuid4().hex
        client = InfluxDBClient(
            host=os.environ["INFLUXDB_HOST"],
            port=int(os.environ["INFLUXDB_PORT"]),
            database=name,
            username=os.getenv("INFLUXDB_USERNAME"),
            password=os.getenv("INFLUXDB_PASSWORD"),
        )
        self.addCleanup(client.close)
        client.create_database(name)
        self.addCleanup(client.drop_database, name)
        common = {"ActivityID": "123", "Device": "Synthetic", "Database_Name": name}
        stamp = "2026-05-01T10:00:00Z"
        self.assertTrue(
            client.write_points(
                [
                    dict(
                        measurement="ActivitySummary",
                        time=stamp,
                        tags=common,
                        fields={
                            "Activity_ID": 123,
                            "activityName": "Synthetic",
                            "activityType": "strength_training",
                        },
                    ),
                    dict(
                        measurement="StrengthSet",
                        time=stamp,
                        tags={
                            **common,
                            "Exercise": "Bench",
                            "ExerciseCategory": "BENCH_PRESS",
                            "SetIndex": "0",
                        },
                        fields={
                            "source": "Garmin",
                            "reps": 7,
                            "weightKg": 32.5,
                            "exerciseCode": "BENCH_PRESS",
                        },
                    ),
                ]
            )
        )

        def records(table):
            return list(client.query(f'SELECT * FROM "{table}"').get_points())

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                os.environ,
                {
                    "INFLUXDB_DATABASE": name,
                    "STRENGTH_MUTATION_LOCK_PATH": directory + "/lock",
                    "GARMIN_OPERATION_STATE_PATH": directory + "/operations.sqlite",
                },
            ),
        ):
            path = Path(directory) / "synthetic.tsv"

            def write_tsv(session_ids):
                with path.open("w", newline="") as output:
                    writer = csv.writer(output, delimiter="\t")
                    writer.writerow(
                        ["Session ID", "Date", "Exersize", "Sets", "Weights", "Reps"]
                    )
                    for session in session_ids:
                        writer.writerow(
                            [session, "01/05/2026", "Bench Press", 2, "40 45", "10 6"]
                        )

            def run():
                with patch(
                    "sys.argv",
                    [
                        "garmin-reptrace-import",
                        str(path),
                        "--write",
                        "--timezone",
                        "UTC",
                    ],
                ):
                    manual_import.main()

            write_tsv(["1", "2"])
            with self.assertRaisesRegex(ValueError, "Multiple source sessions"):
                run()
            self.assertEqual(records("StrengthSet")[0]["reps"], 7)
            self.assertEqual(records("StrengthManualSession"), [])

            write_tsv(["1"])
            write = InfluxDBClient.write_points

            def interrupt(db, points, *args, **kwargs):
                if (
                    points[0]["measurement"] == "StrengthManualSession"
                    and not points[0]["fields"]["importPending"]
                ):
                    raise RuntimeError("synthetic interruption")
                return write(db, points, *args, **kwargs)

            with (
                patch.object(InfluxDBClient, "write_points", interrupt),
                self.assertRaisesRegex(RuntimeError, "synthetic interruption"),
            ):
                run()
            self.assertTrue(records("StrengthManualSession")[0]["importPending"])
            self.assertTrue(has_manual_strength_details(client, "1", 123))
            store = DataStore(
                factory=lambda: (
                    InfluxDBClient(
                        host=os.environ["INFLUXDB_HOST"],
                        port=int(os.environ["INFLUXDB_PORT"]),
                        database=name,
                    ),
                    lambda q: list(client.query(q).get_points()),
                )
            )
            partial = store.get()[0]
            self.assertEqual(partial["pendingImports"], 1)
            self.assertEqual(partial["workouts"], [])
            self.assertEqual(partial["sets"], [])
            run()
            complete = store.get(force=True)[0]
            self.assertEqual(complete["pendingImports"], 0)
            self.assertEqual(len(complete["sets"]), 2)
            self.assertFalse(records("StrengthManualSession")[0]["importPending"])
            expected = records("StrengthSet")
            self.assertEqual(sorted(r["volumeKg"] for r in expected), [270, 400])
            run()
            self.assertEqual(records("StrengthSet"), expected)
            self.assertEqual(records("StrengthSetGarminArchive")[0]["weightKg"], 32.5)


if __name__ == "__main__":
    unittest.main()
