"""Synthetic fixture and publication boundary checks."""

from datetime import datetime, timezone
import unittest

from reptrace.web.demo import DemoClient, sample_records
from reptrace.storage.manual_import import reviewed_records


class DemoTests(unittest.TestCase):
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
