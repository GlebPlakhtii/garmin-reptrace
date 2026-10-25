import sys
import unittest
from pathlib import Path

from reptrace.training.strength import build_strength_points


class StrengthTests(unittest.TestCase):
    def setUp(self):
        self.activity = {
            "activityId": 123,
            "activityName": "Upper",
            "startTimeGMT": "2026-10-20 13:00:00",
        }

    def active(self, **changes):
        item = {
            "setType": "ACTIVE",
            "repetitionCount": 5,
            "weight": 80000,
            "duration": 25,
            "startTime": "2026-10-20T13:01:00.0",
            "exercises": [
                {
                    "category": "BENCH_PRESS",
                    "name": "BARBELL_BENCH_PRESS",
                    "probability": 100,
                }
            ],
        }
        item.update(changes)
        return item

    def points(self, *items):
        return build_strength_points(
            self.activity, {"exerciseSets": list(items)}, "Watch", "GarminStats"
        )

    def test_converts_grams_and_computes_volume_and_estimate(self):
        point, summary = self.points(self.active())
        self.assertEqual(point["fields"]["weightKg"], 80)
        self.assertEqual(point["fields"]["volumeKg"], 400)
        self.assertAlmostEqual(point["fields"]["estimated1RMKg"], 93.3333333)
        self.assertEqual(point["time"], "2026-10-20T13:01:00+00:00")
        self.assertEqual(summary["fields"]["totalReps"], 5)
        self.assertEqual(summary["time"], "2026-10-20T13:00:00+00:00")

    def test_rest_and_cardio_do_not_count_as_sets(self):
        points = self.points(
            self.active(),
            {"setType": "REST", "duration": 120},
            self.active(repetitionCount=None),
        )
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0]["fields"]["restAfterSeconds"], 120)
        self.assertEqual(points[1]["fields"]["sets"], 1)

    def test_missing_load_stays_missing_but_zero_load_is_preserved(self):
        a, b, summary = self.points(self.active(weight=None), self.active(weight=0))
        self.assertNotIn("weightKg", a["fields"])
        self.assertEqual(b["fields"]["weightKg"], 0)
        self.assertEqual(summary["fields"]["setsWithWeight"], 1)
        self.assertNotIn("estimated1RMKg", summary["fields"])

    def test_no_1rm_for_high_reps_or_bodyweight_or_invalid_load(self):
        for item in [
            self.active(repetitionCount=15),
            self.active(weight=float("nan")),
            self.active(exercises=[{"category": "PULL_UP", "name": "PULL_UP"}]),
        ]:
            self.assertNotIn("estimated1RMKg", self.points(item)[0]["fields"])

    def test_best_exercise_candidate_and_unique_set_identity(self):
        items = [
            self.active(
                exercises=[
                    {"name": "WRONG", "probability": 1},
                    {
                        "name": "BARBELL_BENCH_PRESS",
                        "category": "BENCH_PRESS",
                        "probability": 99,
                    },
                ]
            ),
            self.active(),
        ]
        points = self.points(*items)
        self.assertEqual(points[0]["tags"]["Exercise"], "Barbell Bench Press")
        self.assertNotEqual(
            points[0]["tags"]["SetIndex"], points[1]["tags"]["SetIndex"]
        )
        self.assertEqual(points[2]["fields"]["sets"], 2)
        self.assertEqual([p["fields"]["setNumber"] for p in points[:2]], [1, 2])
        self.assertEqual(points, self.points(*items))

    def test_summary_uses_max_load_and_sums_work(self):
        a, b, summary = self.points(
            self.active(), self.active(weight=70000, repetitionCount=7)
        )
        self.assertEqual(summary["fields"]["bestWeightKg"], 80)
        self.assertEqual(summary["fields"]["totalReps"], 12)
        self.assertEqual(summary["fields"]["volumeKg"], 890)

    def test_bench_names_share_one_exercise_summary(self):
        short = self.active(
            exercises=[{"category": "BENCH_PRESS", "name": "BENCH_PRESS"}]
        )
        points = self.points(short, self.active())
        self.assertEqual(
            [p["tags"]["Exercise"] for p in points], ["Barbell Bench Press"] * 3
        )
        self.assertEqual(points[-1]["fields"]["sets"], 2)
        self.assertEqual(points[0]["fields"]["originalExercise"], "Bench Press")

    def test_confirmed_garmin_proxy_names_use_saved_mappings(self):
        aliases = {
            "FLY": "Cable Chest Fly",
            "CABLE_CROSSOVER": "Cable Chest Fly",
            "WEIGHTED_SEATED_CALF_RAISE": "Leg Press Calf Raise",
            "WEIGHTED_LEG_CURL": "Lying Leg Curl",
            "WEIGHTED_LEG_EXTENSIONS": "Machine Leg Extension",
            "TRICEPS_EXTENSION": "Cable Triceps Extension",
            "SEATED_REAR_LATERAL_RAISE": "Seated Rear Lateral Raise",
        }
        for code, expected in aliases.items():
            points = self.points(
                self.active(exercises=[{"category": "TEST", "name": code}])
            )
            self.assertEqual(points[0]["tags"]["Exercise"], expected)
            self.assertEqual(points[0]["fields"]["exerciseCode"], code)
            self.assertEqual(points[0]["fields"]["weightKg"], 80)

    def test_future_flye_records_use_machine_chest_fly_name(self):
        points = self.points(
            self.active(exercises=[{"category": "FLYE", "name": "FLYE"}])
        )
        self.assertTrue(
            all(p["tags"]["Exercise"] == "Machine Chest Fly" for p in points)
        )
        self.assertEqual(points[0]["fields"]["exerciseCode"], "FLYE")
        self.assertEqual(points[0]["fields"]["originalExercise"], "Flye")

    def test_empty_sets_and_missing_exercise(self):
        self.assertEqual(self.points(), [])
        self.assertEqual(
            self.points(self.active(exercises=[]))[0]["tags"]["Exercise"], "Unknown"
        )

    def test_user_tag_and_explicit_timezone(self):
        self.activity["User_ID"] = "test-user"
        point = self.points(self.active(startTime="2026-10-20T16:01:00+03:00"))[0]
        self.assertEqual(point["time"], "2026-10-20T13:01:00+00:00")
        self.assertEqual(point["tags"]["User_ID"], "test-user")


class CollectorIntegrationTests(unittest.TestCase):
    def collector(
        self, activity_type="strength_training", enabled=True, error=None, manual=False
    ):
        import ast
        import logging
        from datetime import datetime, timedelta
        from unittest.mock import Mock
        import types
        import zoneinfo

        path = Path(__file__).resolve().parents[3] / "src/reptrace/garmin/collector.py"
        tree = ast.parse(path.read_text())
        fn = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "get_activity_summary"
        )
        garmin = Mock()
        garmin.get_activities_by_date.return_value = [
            {
                "activityId": 123,
                "activityType": {"typeKey": activity_type},
                "activityName": "Upper",
                "startTimeGMT": "2026-10-20 13:00:00",
                "elapsedDuration": 60,
            }
        ]
        garmin.get_activity_exercise_sets.return_value = {
            "exerciseSets": [StrengthTests().active()]
        }
        if error:
            garmin.get_activity_exercise_sets.side_effect = error

        class ConnectionError(Exception):
            pass

        ns = {
            "garmin_obj": garmin,
            "ALWAYS_PROCESS_FIT_FILES": False,
            "FETCH_STRENGTH_SETS": enabled,
            "GARMIN_DEVICENAME": "Watch",
            "INFLUXDB_DATABASE": "GarminStats",
            "datetime": datetime,
            "timedelta": timedelta,
            "pytz": types.SimpleNamespace(UTC=zoneinfo.ZoneInfo("UTC")),
            "logging": logging,
            "build_strength_points": build_strength_points,
            "has_manual_strength_details": lambda *args: manual,
            "influxdbclient": None,
            "INFLUXDB_VERSION": "1",
            "GarminConnectConnectionError": ConnectionError,
        }
        if error == "connection":
            garmin.get_activity_exercise_sets.side_effect = ConnectionError("offline")
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), "exec"), ns)
        return ns["get_activity_summary"], garmin

    def test_collects_strength_without_gps(self):
        fn, garmin = self.collector()
        points, gps = fn("2026-10-20")
        self.assertEqual(
            [p["measurement"] for p in points],
            ["ActivitySummary", "ActivitySummary", "StrengthSet", "StrengthExercise"],
        )
        self.assertEqual(gps, {})
        garmin.get_activity_exercise_sets.assert_called_once_with(123)

    def test_other_sports_and_disabled_collection_skip_extra_request(self):
        for kwargs in [{"activity_type": "walking"}, {"enabled": False}]:
            fn, garmin = self.collector(**kwargs)
            points, gps = fn("2026-10-20")
            self.assertEqual(len(points), 2)
            garmin.get_activity_exercise_sets.assert_not_called()

    def test_missing_exercise_endpoint_preserves_summary(self):
        fn, garmin = self.collector(error="connection")
        with self.assertLogs(level="WARNING"):
            points, gps = fn("2026-10-20")
        self.assertEqual(len(points), 2)

    def test_rate_limit_is_not_silently_ignored(self):
        fn, garmin = self.collector(error=RuntimeError("rate limit"))
        with self.assertRaisesRegex(RuntimeError, "rate limit"):
            fn("2026-10-20")

    def test_reviewed_workouts_and_tombstones_preserve_summaries_and_sets(self):
        for enabled in (True, False):
            fn, garmin = self.collector(manual=True, enabled=enabled)
            points, gps = fn("2026-10-20")
            self.assertEqual(points, [])
            self.assertEqual(gps, {})
            garmin.get_activity_exercise_sets.assert_not_called()


if __name__ == "__main__":
    unittest.main()
