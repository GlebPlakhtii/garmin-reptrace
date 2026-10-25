from pathlib import Path
from io import BytesIO
import json
import sys
import tempfile
import unittest
import uuid
from zoneinfo import ZoneInfo

from reptrace.training.planning import build_next_sessions
from reptrace.storage.state import WebState
from reptrace.exports.plans import render_plan
from PIL import Image


def fixture(current=(13, 13), previous=(13, 13), weights=(80, 80)):
    workouts = [
        {"id": "old", "date": "2026-10-13", "name": "Upper 1"},
        {"id": "new", "date": "2026-10-20", "name": "Upper 1"},
    ]
    sets = [
        {
            "sessionId": identity,
            "exercise": "Barbell Bench Press",
            "weight": weight,
            "reps": rep,
            "order": i + 1,
        }
        for identity, reps in [("old", previous), ("new", current)]
        for i, (weight, rep) in enumerate(zip(weights, reps))
    ]
    return {"sets": sets, "workouts": workouts}


def proposal(data):
    return build_next_sessions(data, "2026-10-21")[0]


class WeightProgressionTests(unittest.TestCase):
    def test_two_successes_increase_weight_and_reset_reps(self):
        data = fixture()
        before = json.dumps(data, sort_keys=True)
        exercise = proposal(data)["exercises"][0]
        self.assertEqual(exercise["status"], "weight_progress")
        self.assertEqual(exercise["proposed"], [{"weight": 82.5, "reps": 8}] * 2)
        self.assertEqual(json.dumps(data, sort_keys=True), before)

    def test_one_high_rep_set_does_not_raise_all_loads(self):
        exercise = proposal(fixture(current=(13, 10), previous=(13, 9)))["exercises"][0]
        self.assertEqual(exercise["status"], "progress")
        self.assertEqual(exercise["proposed"][1]["reps"], 11)
        self.assertEqual([s["weight"] for s in exercise["proposed"]], [80, 80])

    def test_ceiling_requires_two_successful_sessions(self):
        exercise = proposal(fixture(current=(12, 12), previous=(11, 12)))["exercises"][
            0
        ]
        self.assertEqual(exercise["status"], "repeat")
        self.assertEqual([s["reps"] for s in exercise["proposed"]], [12, 12])

    def test_backoff_groups_can_progress_without_heavy_top_sets(self):
        exercise = proposal(
            fixture(current=(5, 13), previous=(5, 12), weights=(80, 70))
        )["exercises"][0]
        self.assertEqual(
            exercise["proposed"],
            [{"weight": 80, "reps": 5}, {"weight": 72.5, "reps": 8}],
        )

    def test_custom_range_and_increment_are_used(self):
        data = fixture(current=(10, 10), previous=(10, 10))
        data["progressionRules"] = {
            "Barbell Bench Press": {"repMin": 6, "repMax": 10, "weightStep": 1}
        }
        self.assertEqual(
            proposal(data)["exercises"][0]["proposed"], [{"weight": 81, "reps": 6}] * 2
        )

    def test_large_jumps_and_ambiguous_pullup_loads_are_not_progressed(self):
        data = fixture()
        data["progressionRules"] = {
            "Barbell Bench Press": {"repMin": 8, "repMax": 12, "weightStep": 25}
        }
        self.assertEqual(proposal(data)["exercises"][0]["status"], "review")
        for row in data["sets"]:
            row["exercise"] = "Pull Up"
        self.assertEqual(proposal(data)["exercises"][0]["status"], "review")
        for row in data["sets"]:
            row["weight"] = 0
        exercise = proposal(data)["exercises"][0]
        self.assertEqual(exercise["status"], "repeat")
        self.assertTrue(all(s["weight"] == 0 for s in exercise["proposed"]))

    def test_assistance_never_uses_added_weight_progression(self):
        for name, custom in [
            ("Assisted Pull Up", False),
            ("Assisted Dip", False),
            ("My machine", True),
        ]:
            data = fixture(weights=(40, 40))
            for row in data["sets"]:
                row["exercise"] = name
            if custom:
                data["volumeSettings"] = {"exercises": {name: {"assistance": True}}}
            exercise = proposal(data)["exercises"][0]
            self.assertEqual(exercise["status"], "review")
            self.assertEqual(exercise["proposed"], exercise["previous"])
            self.assertIn("assistance", exercise["reason"])

    def test_image_renders_weight_status_and_reduced_reps(self):
        image = Image.open(BytesIO(render_plan(proposal(fixture()))))
        self.assertEqual(image.format, "PNG")
        self.assertLess(image.width + image.height, 10000)

    def test_rules_are_persistent_and_invalid_ranges_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            state = WebState(Path(directory) / "state.sqlite")
            rule = {"repMin": 6, "repMax": 12, "weightStep": 1.25}

            def save(value):
                return state.apply(
                    {
                        "requestId": str(uuid.uuid4()),
                        "action": "progression_save",
                        "mappings": {"Curl": value},
                    },
                    None,
                    "Test",
                    ZoneInfo("Europe/Kyiv"),
                )

            save(rule)
            self.assertEqual(
                WebState(state.path).read()["progressionRules"], {"Curl": rule}
            )
            for invalid in [
                dict(rule, repMin=13),
                dict(rule, repMax=12.5),
                dict(rule, weightStep=0),
                dict(rule, weightStep=float("inf")),
            ]:
                with self.assertRaises(ValueError):
                    save(invalid)
