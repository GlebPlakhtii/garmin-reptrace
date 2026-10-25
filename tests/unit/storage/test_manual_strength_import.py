import csv
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

from reptrace.storage.manual_import import (
    read_records,
    reviewed_records,
    build_session,
    already_imported,
)
from reptrace.training.strength import has_manual_strength_details


class ManualImportTests(unittest.TestCase):
    def test_import_registry_preserves_tombstones_and_reviewed_sessions(self):
        self.assertFalse(already_imported([], "abc", "1"))
        self.assertTrue(
            already_imported(
                [{"sourceHash": "abc", "source": "Manual Web"}], "abc", "1"
            )
        )
        for marker in [
            {"deleted": True, "importedSets": 0},
            {"source": "Manual Web"},
            {"sourceHash": "different"},
        ]:
            with self.assertRaisesRegex(ValueError, "reconcile"):
                already_imported([marker], "abc", "1")

    def record(self, **updates):
        r = {
            "sourceRow": 1,
            "raw": {"Exersize": "Bench Press"},
            "session": "1",
            "date": date(2025, 5, 1),
            "exercise": "Bench Press",
            "sets": 2,
            "weights": ["70", "75"],
            "reps": ["10", "5"],
            "skipReason": "",
        }
        r.update(updates)
        return r

    def build(self, records, workout=None):
        return build_session(
            records,
            workout,
            {"Barbell Bench Press": ("BENCH_PRESS", "BARBELL_BENCH_PRESS")},
            "GarminStats",
            "abc",
            "Europe/Kyiv",
        )

    def test_machine_fly_aliases_use_saved_canonical_name(self):
        for name in ["Machine Fly", "Flye"]:
            points = build_session(
                [self.record(exercise=name)],
                None,
                {"Machine Chest Fly": ("FLYE", "FLYE")},
                "GarminStats",
                "abc",
                "Europe/Kyiv",
            )
            sets = [p for p in points if p["measurement"] == "StrengthSet"]
            self.assertEqual(len(sets), 2)
            self.assertTrue(
                all(p["tags"]["Exercise"] == "Machine Chest Fly" for p in sets)
            )
            self.assertEqual(sets[0]["fields"]["originalExercise"], name)

    def test_rear_delt_fly_keeps_its_source_name(self):
        points = build_session(
            [self.record(exercise="Rear Delt Fly")],
            None,
            {},
            "GarminStats",
            "abc",
            "Europe/Kyiv",
        )
        sets = [p for p in points if p["measurement"] == "StrengthSet"]
        self.assertEqual([p["tags"]["Exercise"] for p in sets], ["Rear Delt Fly"] * 2)

    def test_reads_tsv_and_does_not_import_previous_columns(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t.csv"
            with path.open("w", newline="") as f:
                w = csv.writer(f, delimiter="\t")
                w.writerow(
                    [
                        "Session ID",
                        "Date",
                        "Exersize",
                        "Sets",
                        "Weights",
                        "Reps",
                        "Prev\nReps",
                    ]
                )
                w.writerow(
                    ["1", "01/05/2025", "Bench Press", "2 ", "70 75", "10 5", "99 99"]
                )
            records = read_records(path)
        self.assertEqual(records[0]["reps"], ["10", "5"])
        self.assertEqual(records[0]["date"], date(2025, 5, 1))
        self.assertEqual(records[0]["sets"], 2)

    def test_user_confirmed_corrections_are_narrow(self):
        r = self.record(
            session="901",
            date=date(2024, 1, 2),
            exercise="Seated Cable Row",
            weights=["50"] * 3,
        )
        profile = {
            "rules": [
                {
                    "match": {
                        "session": "901",
                        "date": "2024-01-02",
                        "exercise": "Seated Cable Row",
                        "sets": 2,
                        "weights": ["50"] * 3,
                    },
                    "replace": {"weights": ["50"] * 2},
                    "correction": "Reviewed synthetic fixture",
                }
            ]
        }
        self.assertEqual(
            list(reviewed_records([r], profile))[0]["weights"], ["50", "50"]
        )
        with self.assertRaises(ValueError):
            list(reviewed_records([r]))
        with self.assertRaises(ValueError):
            list(reviewed_records([self.record(weights=["70"] * 3)]))

    def test_repeat_tail_is_skipped_but_audited(self):
        r = self.record(session="902", date=date(2024, 1, 3), exercise="Lying Leg Curl")
        profile = {
            "rules": [
                {
                    "match": {
                        "session": "902",
                        "date": "2024-01-03",
                        "exercise": "Lying Leg Curl",
                    },
                    "duplicateOnly": True,
                    "skipReason": "Reviewed synthetic duplicate",
                }
            ]
        }
        records = list(reviewed_records([r, dict(r, sourceRow=2)], profile))
        self.assertFalse(records[0]["skipReason"])
        self.assertTrue(records[1]["skipReason"])
        points = self.build(records)
        self.assertEqual(
            len([p for p in points if p["measurement"] == "StrengthSet"]), 2
        )
        self.assertEqual(
            len([p for p in points if p["measurement"] == "StrengthManualSource"]), 2
        )

    def test_missing_reps_are_not_zero_and_do_not_generate_volume(self):
        points = self.build([self.record(reps=[])])
        sets = [p for p in points if p["measurement"] == "StrengthSet"]
        self.assertNotIn("reps", sets[0]["fields"])
        self.assertNotIn("volumeKg", sets[0]["fields"])
        summary = next(p for p in points if p["measurement"] == "StrengthExercise")
        self.assertEqual(summary["fields"]["sets"], 2)
        self.assertEqual(summary["fields"]["setsWithReps"], 0)
        self.assertNotIn("totalReps", summary["fields"])

    def test_colon_notation_preserved_without_numeric_guess(self):
        points = self.build([self.record(weights=["55:40", "45"], reps=["5:6", "11"])])
        first = next(p for p in points if p["measurement"] == "StrengthSet")
        self.assertEqual(first["fields"]["rawWeight"], "55:40")
        self.assertNotIn("reps", first["fields"])
        self.assertNotIn("weightKg", first["fields"])

    def test_new_manual_workout_has_no_fake_duration_or_garmin_link(self):
        points = self.build([self.record()])
        summary = next(p for p in points if p["measurement"] == "ActivitySummary")
        self.assertLess(summary["fields"]["Activity_ID"], 0)
        self.assertNotIn("elapsedDuration", summary["fields"])
        self.assertNotIn("activityUrl", summary["fields"])
        self.assertEqual(summary["time"], "2025-05-01T09:00:00+00:00")
        self.assertEqual(points, self.build([self.record()]))

    def test_same_day_merge_uses_existing_identity_and_no_extra_workout(self):
        workout = {
            "Activity_ID": 123,
            "time": "2025-05-01T13:00:00Z",
            "activityName": "Strength",
            "Device": "Watch",
        }
        points = self.build([self.record()], workout)
        self.assertFalse(any(p["measurement"] == "ActivitySummary" for p in points))
        self.assertTrue(all(p["tags"]["ActivityID"] == "123" for p in points))
        self.assertEqual(points[-1]["fields"]["mergedWithGarmin"], True)

    def test_unknown_exercise_and_weighted_pullup_preserved(self):
        points = self.build(
            [self.record(exercise="Incline Bicep Curl", weights=["8", "0"])]
        )
        first = points[0]
        self.assertEqual(first["tags"]["Exercise"], "Incline Bicep Curl")
        self.assertEqual(points[1]["fields"]["weightKg"], 0)
        points = build_session(
            [self.record(exercise="Pull-up", weights=["16", "16"])],
            None,
            {"Pull Up": ("PULL_UP", "PULL_UP")},
            "GarminStats",
            "abc",
            "Europe/Kyiv",
        )
        self.assertEqual(points[0]["fields"]["weightKg"], 16)
        self.assertNotIn("estimated1RMKg", points[0]["fields"])

    def test_import_registry_prevents_collector_overwrite(self):
        client = Mock()
        client.query.return_value.get_points.return_value = iter([{"importedSets": 3}])
        self.assertTrue(has_manual_strength_details(client, "1", 123))
        client.query.return_value.get_points.return_value = iter([])
        self.assertFalse(has_manual_strength_details(client, "1", 456))
        client.query.return_value.to_pylist.return_value = [{"importedSets": 3}]
        self.assertTrue(has_manual_strength_details(client, "3", 123))


if __name__ == "__main__":
    unittest.main()
