import sys
import unittest
from copy import deepcopy
from datetime import date
from pathlib import Path

from reptrace.coaching.assistant import TrainingTools


def meal(time, protein=50, calories=1000):
    return dict(
        id=time,
        time=time,
        name="Meal",
        protein_g=protein,
        calories=calories,
        carbs_g=100,
        fat_g=30,
    )


class NutritionToolsTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "timezone": "Europe/Kyiv",
            "foodLog": [
                meal("2026-10-20T09:00:00Z"),
                meal("2026-10-22T22:30:00Z", 60, 1200),
                meal("2026-10-23T09:00:00Z", 55, 1345),
                meal("2026-10-24T09:00:00Z", 99, 2242),
            ],
            "recovery": [
                {
                    "date": "2026-10-21",
                    "bodyWeightKg": 80,
                    "bodyWeightSource": "garmin",
                },
                {"date": "2026-10-24", "activeCalories": 500, "restingCalories": 2000},
                {"date": "2026-10-25", "bodyWeightKg": 200},
            ],
        }
        self.tools = TrainingTools(self.data, {}, today=date(2026, 10, 24))

    def read(self, **args):
        return self.tools.call(
            "get_nutrition_history", dict(from_date=None, to_date=None, limit=2) | args
        )

    def test_local_days_complete_totals_weight_and_burn(self):
        before = deepcopy(self.data)
        result = self.read()
        self.assertEqual(result["matchingDays"], 3)
        self.assertTrue(result["truncated"])
        today, yesterday = result["days"]
        self.assertEqual(yesterday["date"], "2026-10-23")
        self.assertEqual(yesterday["totals"]["protein_g"], 115)
        self.assertEqual(yesterday["totals"]["calories"], 2545)
        self.assertEqual(today["bodyWeight"]["date"], "2026-10-21")
        self.assertEqual(today["proteinGramsPerKg"], 1.238)
        self.assertEqual(today["intakeMinusBurnKcal"], -258)
        self.assertIsNone(yesterday["intakeMinusBurnKcal"])
        self.assertTrue(today["isToday"])
        self.assertEqual(result["averagesPerLoggedDay"]["protein_g"], 107)
        self.assertEqual(result["latestBodyWeight"]["kg"], 80)
        self.assertEqual(self.data, before)

    def test_date_bounds_missing_values_and_empty_log(self):
        result = self.read(from_date="2026-10-23", to_date="2026-10-23")
        self.assertEqual(len(result["days"]), 1)
        self.assertFalse(result["truncated"])
        self.data["foodLog"][1]["protein_g"] = None
        result = self.read()
        self.assertIsNone(result["days"][1]["totals"]["protein_g"])
        self.assertIsNone(result["averagesPerLoggedDay"]["protein_g"])
        self.data["foodLog"] = []
        self.assertEqual(self.read()["days"], [])
        self.assertTrue(self.read()["foodLogAvailable"])
        del self.data["foodLog"]
        self.assertFalse(self.read()["foodLogAvailable"])

    def test_truncated_entries_do_not_truncate_totals_and_weight_is_not_backfilled(
        self,
    ):
        self.data["foodLog"] = [meal("2026-10-20T09:00:00Z")] * 25
        day = self.read()["days"][0]
        self.assertTrue(day["entriesTruncated"])
        self.assertEqual(len(day["entries"]), 20)
        self.assertEqual(day["totals"]["protein_g"], 1250)
        self.assertIsNone(day["bodyWeight"])
        self.assertIsNone(day["proteinGramsPerKg"])

    def test_invalid_bounds_and_limit(self):
        for args in (
            {"from_date": "bad"},
            {"from_date": "2026-10-24", "to_date": "2026-10-23"},
            {"limit": 0},
            {"limit": True},
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.read(**args)


if __name__ == "__main__":
    unittest.main()
