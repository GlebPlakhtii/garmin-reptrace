from copy import deepcopy
from datetime import date
import unittest

from reptrace.training.adaptation import adapt_session
from tests.unit.reports.test_training_reports import records, row


class AdaptationTests(unittest.TestCase):
    def setUp(self):
        self.data = records()
        self.data["workouts"][-1].update(name="Hotel full body", duration=2100)
        self.data["sets"] = [
            row("c", "2026-10-20", 40, 8, exercise=name, order=i, duration=30, rest=90)
            for name in ("Squat", "Row", "Curl")
            for i in range(3)
        ]
        self.options = {
            "session_id": "c",
            "time_minutes": 15,
            "priority_exercises": ["Squat"],
        }
        self.today = date(2026, 10, 22)

    def test_explicit_arbitrary_session_preserves_priorities_and_reports_week(self):
        before = deepcopy(self.data)
        p = adapt_session(self.data, self.options, self.today)
        self.assertEqual(self.data, before)
        self.assertEqual([len(e["proposed"]) for e in p["exercises"]], [3, 1, 1])
        self.assertEqual(p["adaptation"]["estimatedMinutes"], 15)
        self.assertEqual(p["adaptation"]["originalEstimatedMinutes"], 23)
        self.assertFalse(p["adaptation"]["budgetExceeded"])
        self.assertEqual(
            p["adaptation"]["setImpact"][2],
            {
                "exercise": "Curl",
                "recordedThisWeek": 3,
                "originalPlannedSets": 3,
                "adaptedPlannedSets": 1,
            },
        )

    def test_impossible_budget_is_explicit_and_never_cuts_protected_sets(self):
        p = adapt_session(self.data, dict(self.options, time_minutes=10), self.today)
        self.assertEqual([e["name"] for e in p["exercises"]], ["Squat"])
        self.assertEqual(len(p["exercises"][0]["proposed"]), 3)
        self.assertEqual(p["adaptation"]["estimatedMinutes"], 11)
        self.assertTrue(p["adaptation"]["budgetExceeded"])

    def test_elapsed_duration_does_not_double_count_preparation(self):
        for r in self.data["sets"]:
            r.pop("duration")
            r.pop("rest")
        p = adapt_session(self.data, dict(self.options, time_minutes=35), self.today)
        self.assertEqual(p["adaptation"]["estimatedMinutes"], 35)
        self.assertEqual(
            p["adaptation"]["timing"]["Squat"]["source"], "recorded session duration"
        )
        self.data["workouts"][-1]["duration"] = None
        p = adapt_session(self.data, dict(self.options, time_minutes=35), self.today)
        self.assertEqual(p["adaptation"]["estimatedMinutes"], 32)
        self.assertEqual(
            p["adaptation"]["timing"]["Squat"]["source"], "assumed 3 minutes per set"
        )

    def test_unknown_measurements_and_explicit_zero_rest_are_preserved(self):
        self.data["sets"][0].update(weight=None, reps=None)
        for r in self.data["sets"]:
            r["rest"] = 0
        p = adapt_session(self.data, self.options, self.today)
        self.assertIsNone(p["exercises"][0]["proposed"][0]["weight"])
        self.assertIsNone(p["exercises"][0]["proposed"][0]["reps"])
        self.assertEqual(p["adaptation"]["estimatedMinutes"], 9.5)

    def test_constraints_validate_and_no_future_history_is_used(self):
        for update in (
            {"time_minutes": True},
            {"time_minutes": 9},
            {"priority_exercises": ["Invented"]},
            {"unavailable_exercises": ["Squat"]},
            {"session_id": "missing"},
        ):
            with self.subTest(update=update), self.assertRaises(ValueError):
                adapt_session(self.data, dict(self.options, **update), self.today)
        with self.assertRaises(ValueError):
            adapt_session(self.data, self.options, date(2026, 10, 19))

    def test_generic_session_is_explicit_baseline_without_unrelated_progression(self):
        self.data["workouts"][-1]["name"] = "Strength"
        p = adapt_session(self.data, self.options, self.today)
        self.assertEqual(p["evidenceCount"], 1)
        self.assertEqual(p["baselineId"], "c")

    def test_replacement_never_uses_future_or_equivalent_loads(self):
        options = dict(
            self.options,
            substitutions=[{"from_exercise": "Row", "to_exercise": "Cable Row"}],
        )
        self.data["sets"].append(
            row("future", "2026-11-01", 100, 10, exercise="Cable Row")
        )
        with self.assertRaises(ValueError):
            adapt_session(self.data, options, self.today)
        self.data["sets"].append(row("a", "2026-10-11", 20, 9, exercise="Cable Row"))
        p = adapt_session(self.data, dict(options, time_minutes=35), self.today)
        replacement = p["exercises"][1]
        self.assertEqual(replacement["proposed"], [{"weight": 20, "reps": 9}])
        self.assertEqual(replacement["history"], [])
