from pathlib import Path
import copy
from io import BytesIO
import sys
import unittest

from reptrace.training.planning import build_next_sessions, workout_type
from reptrace.exports.plans import render_plan
from PIL import Image


def workout(identity, day, name="Upper 1"):
    return dict(id=identity, date=day, time=day + "T09:00:00Z", name=name)


def row(identity, weight=80, reps=5, name="Barbell Bench Press", order=1, **extra):
    return dict(
        sessionId=identity,
        exercise=name,
        weight=weight,
        reps=reps,
        order=order,
        category="BENCH_PRESS",
        **extra,
    )


def data():
    return {
        "workouts": [workout("a", "2026-10-13"), workout("b", "2026-10-20")],
        "sets": [
            row("a"),
            row("a", reps=6, order=2),
            row("b", reps=6),
            row("b", reps=6, order=2),
        ],
    }


def plan(d, day="2026-10-21"):
    return build_next_sessions(d, day)[0]


class NextSessionTests(unittest.TestCase):
    def test_last_performed_tracks_exercises_omitted_from_recent_sessions(self):
        records = data()
        records['workouts'] += [workout('c', '2026-10-22'), workout('d', '2026-10-24')]
        records['sets'] += [row('c', name='Squat'), row('d', name='Squat')]
        result = plan(records, '2026-10-25')
        self.assertEqual(result['lastPerformed']['Barbell Bench Press'], {
            'date': '2026-10-20', 'time': '2026-10-20T09:00:00Z',
        })
        self.assertEqual(result['lastPerformed']['Squat']['time'], '2026-10-24T09:00:00Z')
        self.assertEqual(result['baselineTime'], '2026-10-24T09:00:00Z')

    def test_all_four_types_and_named_aliases_without_guessing_generic_workouts(self):
        self.assertEqual(workout_type("Leg Day 2"), "lower2")
        self.assertEqual(workout_type("lower 1"), "lower1")
        self.assertEqual(workout_type("UPPER_2"), "upper2")
        self.assertIsNone(workout_type("Strength"))
        self.assertEqual(len(build_next_sessions({"sets": [], "workouts": []})), 4)

    def test_stable_pattern_adds_only_one_rep_and_preserves_actual_data(self):
        d = data()
        before = copy.deepcopy(d)
        e = plan(d)["exercises"][0]
        self.assertEqual(e["status"], "progress")
        self.assertEqual([r["reps"] for r in e["proposed"]], [6, 7])
        self.assertEqual(d, before)
        self.assertEqual([r["weight"] for r in e["proposed"]], [80, 80])

    def test_load_changes_and_declining_load_groups_pause_progression(self):
        d = data()
        d["sets"][0]["weight"] = 75
        self.assertEqual(plan(d)["exercises"][0]["status"], "repeat")
        d = data()
        d["sets"][0].update(weight=90, reps=10)
        d["sets"][2].update(weight=90, reps=9)
        d["sets"][3]["reps"] = 20
        self.assertEqual(plan(d)["exercises"][0]["status"], "repeat")

    def test_top_and_backoff_sets_are_not_flattened(self):
        d = data()
        for s in d["sets"]:
            if s["order"] == 2:
                s["weight"] = 70
        e = plan(d)["exercises"][0]
        self.assertEqual([r["weight"] for r in e["proposed"]], [80, 70])
        self.assertEqual(len(e["proposed"]), 2)

    def test_stale_data_and_long_gaps_pause_progression(self):
        self.assertEqual(plan(data(), "2026-12-01")["exercises"][0]["status"], "review")
        d = data()
        d["workouts"][0]["date"] = "2026-08-01"
        self.assertEqual(plan(d)["exercises"][0]["status"], "repeat")

    def test_missing_values_and_pullup_loads_are_not_invented_or_converted(self):
        d = data()
        d["sets"][3]["reps"] = None
        e = plan(d)["exercises"][0]
        self.assertIsNone(e["proposed"][1]["reps"])
        self.assertEqual(e["status"], "review")
        d = data()
        for s in d["sets"]:
            s.update(exercise="Pull Up", weight=70, category="PULL_UP")
        e = plan(d)["exercises"][0]
        self.assertEqual(e["status"], "review")
        self.assertEqual(e["proposed"][0]["weight"], 70)

    def test_confirmed_bodyweight_pullups_progress_reps_without_adding_weight(self):
        from reptrace.exports.plans import load_label

        d = data()
        for s in d["sets"]:
            s.update(exercise="Pull Up", weight=0, category="PULL_UP")
        e = plan(d)["exercises"][0]
        self.assertEqual(e["status"], "progress")
        self.assertEqual([r["weight"] for r in e["proposed"]], [0, 0])
        self.assertEqual(load_label("Pull Up", 0), "BW")
        self.assertEqual(load_label("Pull Up", 16), "16 kg")
        for s in d["sets"]:
            s["exercise"] = "Barbell Bench Press"
        self.assertEqual(plan(d)["exercises"][0]["status"], "review")

    def test_known_machine_name_is_not_treated_as_bodyweight_by_garmin_category(self):
        d = data()
        for s in d["sets"]:
            s.update(exercise="Weighted Leg Extensions", category="CRUNCH")
        self.assertEqual(plan(d)["exercises"][0]["status"], "progress")

    def test_generic_future_and_unknown_exercises_are_excluded(self):
        d = data()
        d["workouts"] += [
            workout("future", "2026-10-30"),
            workout("generic", "2026-10-21", "Strength"),
        ]
        d["sets"] += [
            row("future", weight=100),
            row("generic", weight=200),
            row("b", name=" Unknown "),
        ]
        p = plan(d)
        self.assertEqual(p["baselineId"], "b")
        self.assertEqual(len(p["exercises"]), 1)
        self.assertEqual(p["evidenceCount"], 2)

    def test_skipped_exercise_is_retained_without_fabricating_completed_sets(self):
        d = data()
        d["sets"].append(row("a", name="Curl"))
        before = copy.deepcopy(d)
        p = plan(d)
        self.assertEqual(len(p["exercises"]), 2)
        self.assertEqual(p["baselineId"], "b")
        self.assertEqual(p["retainedStructureDate"], "2026-10-13")
        self.assertEqual(p["omittedExercises"], [])
        curl = p["exercises"][1]
        self.assertEqual(curl["previous"], [])
        self.assertEqual(curl["proposed"], [{"weight": 80, "reps": 5}])
        self.assertEqual(curl["status"], "repeat")
        self.assertIn("one-time omission", curl["reason"])
        self.assertEqual(curl["history"][0]["sets"], [])
        self.assertEqual(d, before)

    def test_four_skipped_sets_restore_exercises_in_previous_order(self):
        d = data()
        d["sets"] += [
            row("a", name=name, order=i, reps=12)
            for name, i in [("Row", 0), ("Row", 1), ("Curl", 4), ("Curl", 5)]
        ]
        p = plan(d)
        self.assertEqual(
            [e["name"] for e in p["exercises"]], ["Row", "Barbell Bench Press", "Curl"]
        )
        self.assertEqual(sum(len(e["proposed"]) for e in p["exercises"]), 6)
        self.assertEqual(sum(len(e["previous"]) for e in p["exercises"]), 2)
        self.assertEqual(
            [e["status"] for e in p["exercises"]], ["repeat", "progress", "repeat"]
        )
        self.assertEqual([s["weight"] for s in p["exercises"][0]["proposed"]], [80, 80])
        image = Image.open(BytesIO(render_plan(p)))
        self.assertEqual(image.width, 1200)

    def test_partial_exercise_repeats_full_prior_targets_without_progression(self):
        d = data()
        d["sets"] = [
            row("a", weight=80, reps=12),
            row("a", weight=70, reps=12, order=2),
            row("b", weight=85, reps=12),
        ]
        e = plan(d)["exercises"][0]
        self.assertEqual(e["previous"], [{"weight": 85, "reps": 12}])
        self.assertEqual(
            e["proposed"], [{"weight": 80, "reps": 12}, {"weight": 70, "reps": 12}]
        )
        self.assertEqual(e["status"], "repeat")

    def test_repeated_reduction_establishes_new_structure(self):
        d = data()
        d["sets"].append(row("a", name="Curl"))
        d["workouts"].append(workout("c", "2026-10-21"))
        d["sets"] += [row("c"), row("c", order=2)]
        p = plan(d)
        self.assertEqual(len(p["exercises"]), 1)
        self.assertNotIn("retainedStructureDate", p)
        self.assertEqual(
            p["omittedExercises"], [{"name": "Curl", "lastDate": "2026-10-13"}]
        )

    def test_substitutions_additions_long_gaps_and_explicit_templates_are_respected(
        self,
    ):
        for case in ("substitution", "addition", "long_gap", "explicit"):
            with self.subTest(case=case):
                d = data()
                d["sets"].append(row("a", name="Curl"))
                if case == "substitution":
                    d["sets"].append(row("b", name="Cable Curl"))
                elif case == "addition":
                    d["sets"].append(row("b", order=3))
                elif case == "long_gap":
                    d["workouts"][0]["date"] = "2026-08-01"
                p = build_next_sessions(
                    d, "2026-10-21", baseline_id="b" if case == "explicit" else None
                )[0]
                self.assertNotIn("Curl", [e["name"] for e in p["exercises"]])
                self.assertNotIn("retainedStructureDate", p)

    def test_restored_exercises_still_require_data_and_equipment_review(self):
        for name, overrides in [
            ("Curl", {"reps": None}),
            ("Assisted Pull Up", {}),
            ("Curl", {"weight": 0}),
        ]:
            with self.subTest(name=name, overrides=overrides):
                d = data()
                d["sets"].append(row("a", name=name, **overrides))
                self.assertEqual(plan(d)["exercises"][-1]["status"], "review")
        d = data()
        d["sets"].append(row("a", name="Curl"))
        self.assertEqual(plan(d, "2026-12-01")["exercises"][-1]["status"], "review")
        d["equipment"] = {
            "assignments": {"Curl": "rack"},
            "profiles": {"rack": {"name": "Rack", "loads": [10, 20]}},
        }
        self.assertEqual(plan(d)["exercises"][-1]["status"], "review")

    def test_image_keeps_all_exercises_on_one_readable_png(self):
        d = data()
        d["sets"] += [
            row("b", name="Exercise " + str(i), order=i + 3) for i in range(7)
        ]
        p = plan(d)
        self.assertEqual(p["imagePages"], 1)
        for page in [0]:
            raw = render_plan(p, page)
            image = Image.open(BytesIO(raw))
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.width, 1200)
            self.assertLess(image.width + image.height, 10000)
        with self.assertRaises(ValueError):
            render_plan(p, 1)


if __name__ == "__main__":
    unittest.main()
