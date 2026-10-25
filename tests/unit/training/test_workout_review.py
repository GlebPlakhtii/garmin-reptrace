from pathlib import Path
import sys
import unittest

from reptrace.training.review import compare_plan
from reptrace.reports.facts import session_facts
from reptrace.reports.render import render_report_html, render_report_preview
from tests.unit.reports.test_training_reports import records


class WorkoutReviewTests(unittest.TestCase):
    def test_matches_changed_missing_extra_and_unknown_without_inventing_values(self):
        facts = session_facts(records(), "c")
        facts["exercises"][0]["sets"] = [
            {"weight": 85, "reps": 10},
            {"weight": 80, "reps": 8},
            {"weight": None, "reps": 7},
        ]
        template = {
            "name": "Upper 1",
            "source": "current_template",
            "asOf": "2026-10-20T11:00:00Z",
            "plannedSets": [
                {"exercise": "Barbell Bench Press", "weight": 85, "reps": 10},
                {"exercise": "Barbell Bench Press", "weight": 82.5, "reps": 8},
                {"exercise": "Barbell Bench Press", "weight": 80, "reps": 7},
                {"exercise": "Barbell Bench Press", "weight": 80, "reps": 6},
                {"exercise": "Lateral Raise", "weight": 10, "reps": 12},
            ],
        }
        review = compare_plan(facts, template)
        self.assertEqual(
            review["counts"],
            {"matched": 1, "changed": 1, "missing": 2, "extra": 0, "unknown": 1},
        )
        self.assertIn("current Garmin template", review["note"])
        facts["planReview"] = review
        html = render_report_html(facts).decode()
        self.assertIn("Plan vs completed", html)
        self.assertIn("Current Garmin template · approximate", html)
        self.assertIn("Lateral Raise", html)
        self.assertIn("82.5 kg", html)
        image = render_report_preview(facts)
        self.assertTrue(image.startswith(b"\x89PNG"))

    def test_unavailable_template_is_explicit(self):
        facts = session_facts(records(), "c")
        facts["planReview"] = compare_plan(
            facts, {"reason": "No saved template predates this session."}
        )
        self.assertEqual(facts["planReview"]["status"], "unavailable")
        self.assertIn("No saved template", render_report_html(facts).decode())


if __name__ == "__main__":
    unittest.main()
