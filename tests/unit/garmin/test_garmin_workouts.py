from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

from reptrace.garmin.workouts import (
    make_update,
    GarminWorkouts,
    manual_update,
    saved_workout_matches,
    editable_steps,
    executed_steps,
    unroll_group,
    full_workout_edit,
    merge_adjacent_repeats,
    full_edit_summary,
)
from reptrace.storage.state import Conflict


def fixture(count=2):
    active = {
        "stepId": 10,
        "stepOrder": 2,
        "type": "ExecutableStepDTO",
        "stepType": {"stepTypeKey": "interval"},
        "category": "BENCH_PRESS",
        "exerciseName": "BARBELL_BENCH_PRESS",
        "endCondition": {"conditionTypeKey": "reps"},
        "endConditionValue": 8,
        "weightValue": 80,
        "weightUnit": {"unitKey": "kilogram"},
        "description": "Keep this cue",
    }
    rest = {
        "stepId": 11,
        "stepOrder": 3,
        "stepType": {"stepTypeKey": "rest"},
        "endCondition": {"conditionTypeKey": "time"},
        "endConditionValue": 90,
    }
    return {
        "workoutId": 123,
        "workoutName": "Upper 1",
        "sportType": {"sportTypeKey": "strength_training"},
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "workoutSteps": [
                    {
                        "stepId": 9,
                        "type": "RepeatGroupDTO",
                        "numberOfIterations": count,
                        "endConditionValue": float(count),
                        "workoutSteps": [active, rest],
                        "skipLastRestStep": True,
                    }
                ],
            }
        ],
    }


def plan(targets=None):
    return {
        "type": "upper1",
        "stale": False,
        "exercises": [
            {
                "name": "Barbell Bench Press",
                "status": "weight_progress",
                "proposed": targets or [{"weight": 85, "reps": 10}] * 2,
            }
        ],
    }


class GarminWorkoutTests(unittest.TestCase):
    def test_review_uses_saved_pre_session_template_and_expands_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            original = fixture()
            remote = [deepcopy(original)]
            client = Mock()
            client.get.side_effect = lambda _: deepcopy(remote[0])
            client.update.side_effect = lambda _, value: remote.__setitem__(
                0, deepcopy(value)
            )
            service = GarminWorkouts(Path(directory) / "updates.sqlite", lambda: client)
            preview = service.call({"operation": "preview", "workoutId": 123}, [plan()])
            service.call(
                {"operation": "apply", "previewId": preview["previewId"]}, [plan()]
            )
            result = service.call(
                {
                    "operation": "review",
                    "workoutName": "Upper 1",
                    "sessionTime": (
                        datetime.now(timezone.utc) + timedelta(minutes=1)
                    ).isoformat(),
                },
                [],
            )
            self.assertEqual(result["source"], "app_snapshot")
            self.assertEqual(
                [
                    (r["exercise"], r["weight"], r["reps"])
                    for r in result["plannedSets"]
                ],
                [("Barbell Bench Press", 85, 10)] * 2,
            )
            self.assertEqual(client.get.call_count, 3)

    def test_matching_set_after_repeat_is_merged_automatically(self):
        before = fixture()
        group = before["workoutSegments"][0]["workoutSteps"][0]
        group["skipLastRestStep"] = False
        before["workoutSegments"][0]["workoutSteps"] += deepcopy(group["workoutSteps"])
        played = [
            (s.get("exerciseName"), s.get("endConditionValue"))
            for _, s, _ in executed_steps(before)
        ]
        updated = full_workout_edit(
            before,
            {
                "name": "Upper 1",
                "description": "",
                "segments": before["workoutSegments"],
            },
        )
        items = updated["workoutSegments"][0]["workoutSteps"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["numberOfIterations"], 3)
        self.assertEqual(
            [
                (s.get("exerciseName"), s.get("endConditionValue"))
                for _, s, _ in executed_steps(updated)
            ],
            played,
        )
        self.assertEqual(len(before["workoutSegments"][0]["workoutSteps"]), 3)
        self.assertEqual(
            [change["label"] for change in full_edit_summary(before, updated)],
            ["Repeat structure or step order"],
        )

    def test_full_editor_changes_title_steps_and_repeats_with_readback(self):
        with tempfile.TemporaryDirectory() as directory:
            original = fixture()
            remote = [deepcopy(original)]
            client = Mock()
            client.get.side_effect = lambda _: deepcopy(remote[0])
            client.update.side_effect = lambda _, value: remote.__setitem__(
                0, deepcopy(value)
            )
            service = GarminWorkouts(Path(directory) / "updates.sqlite", lambda: client)
            details = service.call({"operation": "details", "workoutId": 123}, [])
            segments = details["segments"]
            group = segments[0]["workoutSteps"][0]
            group["numberOfIterations"] = 3
            group["endConditionValue"] = 3
            group["workoutSteps"][0]["exerciseName"] = "BARBELL_SQUAT"
            group["workoutSteps"][0]["category"] = "SQUAT"
            group["workoutSteps"][1]["endCondition"] = {"conditionTypeKey": "time"}
            group["workoutSteps"][1]["endConditionValue"] = 120
            preview = service.call(
                {
                    "operation": "edit",
                    "workoutId": 123,
                    "name": "Lower 1",
                    "description": "New plan",
                    "segments": segments,
                },
                [],
            )
            self.assertTrue(preview["fullEdit"])
            self.assertEqual(remote[0], original)
            self.assertTrue(any(c["label"] == "Name" for c in preview["changes"]))
            result = service.call(
                {"operation": "apply", "previewId": preview["previewId"]}, []
            )
            self.assertTrue(result["ok"])
            self.assertEqual(remote[0]["workoutName"], "Lower 1")
            self.assertEqual(
                remote[0]["workoutSegments"][0]["workoutSteps"][0][
                    "numberOfIterations"
                ],
                3,
            )
            client.update.assert_called_once()

    def test_full_editor_preserves_and_displays_pounds(self):
        before = fixture()
        before["workoutSegments"][0]["workoutSteps"][0]["workoutSteps"][0][
            "weightUnit"
        ]["unitKey"] = "pound"
        segments = deepcopy(before["workoutSegments"])
        segments[0]["workoutSteps"][0]["workoutSteps"][0]["weightValue"] = 100
        after = full_workout_edit(before, {"name": "Upper 1", "segments": segments})
        change = full_edit_summary(before, after)[0]
        self.assertIn("80 lb", change["before"])
        self.assertIn("100 lb", change["after"])
        self.assertEqual(
            after["workoutSegments"][0]["workoutSteps"][0]["workoutSteps"][0][
                "weightUnit"
            ]["unitKey"],
            "pound",
        )

    def test_full_editor_rejects_stale_draft_before_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            remote = fixture()
            client = Mock()
            client.get.side_effect = lambda _: deepcopy(remote)
            service = GarminWorkouts(Path(directory) / "updates.sqlite", lambda: client)
            details = service.call({"operation": "details", "workoutId": 123}, [])
            remote["description"] = "Changed elsewhere"
            with self.assertRaisesRegex(Conflict, "changed"):
                service.call(
                    {
                        "operation": "edit",
                        "workoutId": 123,
                        "expectedRevision": details["revision"],
                        "name": details["name"],
                        "segments": details["segments"],
                    },
                    [],
                )
            client.update.assert_not_called()

    def test_full_editor_rejects_invalid_structure(self):
        before = fixture()
        segments = deepcopy(before["workoutSegments"])
        segments[0]["workoutSteps"][0]["numberOfIterations"] = 0
        with self.assertRaisesRegex(ValueError, "Repeat blocks"):
            full_workout_edit(
                before, {"name": "Upper 1", "description": "", "segments": segments}
            )

    def test_full_editor_accepts_category_only_garmin_exercise(self):
        before = fixture()
        before["workoutSegments"][0]["workoutSteps"][0]["workoutSteps"][0].update(
            category="FLYE", exerciseName=""
        )
        after = full_workout_edit(
            before,
            {
                "name": "Upper 1",
                "description": "",
                "segments": before["workoutSegments"],
            },
        )
        self.assertEqual(
            after["workoutSegments"][0]["workoutSteps"][0]["workoutSteps"][0][
                "category"
            ],
            "FLYE",
        )

    def test_changes_only_two_leaves_and_keeps_full_structure(self):
        before = fixture()
        copy = deepcopy(before)
        after, changes, skipped = make_update(before, plan())
        self.assertEqual(before, copy)
        self.assertEqual(len(changes), 2)
        self.assertEqual(skipped, [])
        active = after["workoutSegments"][0]["workoutSteps"][0]["workoutSteps"][0]
        self.assertEqual((active["weightValue"], active["endConditionValue"]), (85, 10))
        active["weightValue"] = 80
        active["endConditionValue"] = 8
        self.assertEqual(after, before)

    def test_uniform_targets_fill_existing_sets_when_counts_differ(self):
        before = fixture(4)
        after, changes, notes = make_update(
            before, plan([{"weight": 85, "reps": 10}] * 3)
        )
        self.assertEqual(
            after["workoutSegments"][0]["workoutSteps"][0]["numberOfIterations"], 4
        )
        self.assertEqual(
            [
                (step["weightValue"], step["endConditionValue"])
                for _, step, _ in executed_steps(after)
                if step.get("stepType", {}).get("stepTypeKey") == "interval"
            ],
            [(85, 10)] * 4,
        )
        self.assertEqual(
            sum(change["sets"] for change in changes if change["field"] == "weight"), 4
        )
        self.assertTrue(
            any(
                note.get("applied") and "set counts differ" in note["reason"]
                for note in notes
            )
        )

    def test_varying_targets_still_skip_when_set_counts_differ(self):
        before = fixture(3)
        after, changes, notes = make_update(
            before, plan([{"weight": 85, "reps": 10}, {"weight": 85, "reps": 11}])
        )
        self.assertEqual(after, before)
        self.assertEqual(changes, [])
        self.assertIn("targets vary by set", notes[0]["reason"])

    def test_differing_reps_expand_repeat_into_exact_individual_sets(self):
        before = fixture()
        after, changes, notes = make_update(
            before, plan([{"weight": 85, "reps": 10}, {"weight": 85, "reps": 11}])
        )
        items = after["workoutSegments"][0]["workoutSteps"]
        self.assertEqual(
            [step["stepType"]["stepTypeKey"] for step in items],
            ["interval", "rest", "interval"],
        )
        self.assertEqual(
            [(items[i]["weightValue"], items[i]["endConditionValue"]) for i in (0, 2)],
            [(85, 10), (85, 11)],
        )
        self.assertEqual(len(changes), 4)
        self.assertTrue(notes[0]["applied"])
        self.assertEqual(before, fixture())

    def test_differing_weights_also_expand_to_avoid_approximation(self):
        after, _, _ = make_update(
            fixture(), plan([{"weight": 85, "reps": 10}, {"weight": 80, "reps": 10}])
        )
        self.assertEqual(
            [
                after["workoutSegments"][0]["workoutSteps"][i]["weightValue"]
                for i in (0, 2)
            ],
            [85, 80],
        )

    def test_three_identical_targets_stay_in_one_repeat_before_a_different_set(self):
        before = fixture(4)
        targets = [{"weight": 85, "reps": 10}] * 3 + [{"weight": 87.5, "reps": 8}]
        after, changes, _ = make_update(before, plan(targets))
        items = after["workoutSegments"][0]["workoutSteps"]
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["numberOfIterations"], 3)
        self.assertEqual(items[0]["endConditionValue"], 3)
        self.assertFalse(items[0]["skipLastRestStep"])
        self.assertEqual(items[1]["weightValue"], 87.5)
        self.assertEqual([row["sets"] for row in editable_steps(after)], [3, 1])
        self.assertEqual(
            [step["stepType"]["stepTypeKey"] for _, step, _ in executed_steps(after)],
            [step["stepType"]["stepTypeKey"] for _, step, _ in executed_steps(before)],
        )
        self.assertEqual(
            [
                step["weightValue"]
                for _, step, _ in executed_steps(after)
                if step["stepType"]["stepTypeKey"] == "interval"
            ],
            [85, 85, 85, 87.5],
        )
        self.assertEqual(
            sum(change["sets"] for change in changes if change["field"] == "weight"), 4
        )

    def test_three_identical_targets_after_a_different_set_skip_final_rest(self):
        before = fixture(4)
        targets = [{"weight": 87.5, "reps": 8}] + [{"weight": 85, "reps": 10}] * 3
        after, _, _ = make_update(before, plan(targets))
        items = after["workoutSegments"][0]["workoutSteps"]
        self.assertEqual(
            [item.get("numberOfIterations") for item in items], [None, None, 3]
        )
        self.assertTrue(items[-1]["skipLastRestStep"])
        self.assertEqual([row["sets"] for row in editable_steps(after)], [1, 3])
        self.assertEqual(len(executed_steps(after)), len(executed_steps(before)))

    def test_already_expanded_steps_are_regrouped_into_repeat_runs(self):
        before = fixture(4)
        before["workoutSegments"][0]["workoutSteps"] = unroll_group(
            before["workoutSegments"][0]["workoutSteps"][0]
        )
        targets = [{"weight": 85, "reps": 10}] * 3 + [{"weight": 87.5, "reps": 8}]
        after, _, notes = make_update(before, plan(targets))
        items = after["workoutSegments"][0]["workoutSteps"]
        self.assertEqual([item.get("numberOfIterations") for item in items], [3, None])
        self.assertEqual(items[0]["endConditionValue"], 3)
        self.assertEqual([row["sets"] for row in editable_steps(after)], [3, 1])
        self.assertTrue(
            any("grouped into Garmin repeat blocks" in note["reason"] for note in notes)
        )
        self.assertEqual(len(executed_steps(after)), len(executed_steps(before)))

    def test_manual_update_can_regroup_unchanged_expanded_steps(self):
        before = fixture(3)
        before["workoutSegments"][0]["workoutSteps"] = unroll_group(
            before["workoutSegments"][0]["workoutSteps"][0]
        )
        after, changes = manual_update(before, before, [])
        self.assertEqual(changes, [])
        self.assertEqual(
            after["workoutSegments"][0]["workoutSteps"][0]["numberOfIterations"], 3
        )
        self.assertTrue(
            after["workoutSegments"][0]["workoutSteps"][0]["skipLastRestStep"]
        )
        self.assertEqual(len(executed_steps(after)), len(executed_steps(before)))

    def test_structure_only_preview_can_be_reviewed_without_target_changes(self):
        before = fixture(3)
        before["workoutSegments"][0]["workoutSteps"] = unroll_group(
            before["workoutSegments"][0]["workoutSteps"][0]
        )
        unchanged = plan([{"weight": 80, "reps": 8}] * 3)
        with tempfile.TemporaryDirectory() as directory:
            client = Mock()
            client.get.return_value = before
            service = GarminWorkouts(Path(directory) / "updates.sqlite", lambda: client)
            preview = service.call(
                {"operation": "preview", "workoutId": 123}, [unchanged]
            )
            self.assertEqual(preview["changes"], [])
            self.assertTrue(preview["structureChanged"])
            revised = service.call(
                {
                    "operation": "revise",
                    "previewId": preview["previewId"],
                    "useSuggestions": False,
                    "manualTargets": [],
                },
                [unchanged],
            )
            self.assertEqual(revised["changes"], [])
            self.assertTrue(revised["structureChanged"])
            self.assertEqual(revised["editable"][0]["sets"], 3)

    def test_skip_last_rest_and_partner_exercise_keep_playback_sequence(self):
        before = fixture()
        group = before["workoutSegments"][0]["workoutSteps"][0]
        group["skipLastRestStep"] = True
        partner = deepcopy(group["workoutSteps"][0])
        partner.update(
            stepId=12, stepOrder=4, category="CURL", exerciseName="CABLE_BICEPS_CURL"
        )
        group["workoutSteps"] = [
            group["workoutSteps"][0],
            group["workoutSteps"][1],
            partner,
            dict(group["workoutSteps"][1], stepId=13, stepOrder=5),
        ]
        p = plan([{"weight": 85, "reps": 10}, {"weight": 85, "reps": 11}])
        p["exercises"].append(
            {
                "name": "Cable Biceps Curl",
                "status": "repeat",
                "proposed": [{"weight": 80, "reps": 8}] * 2,
            }
        )
        after, _, _ = make_update(before, p)
        items = after["workoutSegments"][0]["workoutSteps"]
        self.assertEqual(
            [
                s.get("exerciseName")
                for s in items
                if s.get("stepType", {}).get("stepTypeKey") == "interval"
            ],
            ["BARBELL_BENCH_PRESS", "CABLE_BICEPS_CURL"] * 2,
        )
        self.assertEqual(
            len(
                [s for s in items if s.get("stepType", {}).get("stepTypeKey") == "rest"]
            ),
            3,
        )
        self.assertEqual(
            [
                s["endConditionValue"]
                for s in items
                if s.get("exerciseName") == "CABLE_BICEPS_CURL"
            ],
            [8, 8],
        )

    def test_verification_allows_regenerated_ids_but_checks_every_step_field(self):
        expected = fixture()
        actual = deepcopy(expected)
        group = actual["workoutSegments"][0]["workoutSteps"][0]
        group["stepId"] = 999
        for step in group["workoutSteps"]:
            step["stepId"] += 1000
        self.assertTrue(saved_workout_matches(expected, actual))
        for field, value in [
            ("exerciseName", "OTHER"),
            ("weightValue", 99),
            ("endConditionValue", 99),
            ("stepOrder", 99),
            ("description", "changed"),
        ]:
            changed = deepcopy(actual)
            changed["workoutSegments"][0]["workoutSteps"][0]["workoutSteps"][0][
                field
            ] = value
            self.assertFalse(saved_workout_matches(expected, changed), field)
        for field, value in [("numberOfIterations", 5), ("skipLastRestStep", False)]:
            changed = deepcopy(actual)
            changed["workoutSegments"][0]["workoutSteps"][0][field] = value
            self.assertFalse(saved_workout_matches(expected, changed), field)
        changed = deepcopy(actual)
        changed["workoutSegments"][0]["workoutSteps"][0]["workoutSteps"][1][
            "endConditionValue"
        ] = 120
        self.assertFalse(saved_workout_matches(expected, changed))

    def test_verification_allows_garmin_renumbered_child_ids_after_expansion(self):
        expected, _, _ = make_update(
            fixture(), plan([{"weight": 85, "reps": 10}, {"weight": 85, "reps": 11}])
        )
        actual = deepcopy(expected)
        for number, step in enumerate(
            actual["workoutSegments"][0]["workoutSteps"], start=100
        ):
            step["stepId"] = number
            step["childStepId"] = 1
        self.assertTrue(saved_workout_matches(expected, actual))
        actual["workoutSegments"][0]["workoutSteps"][2]["endConditionValue"] = 12
        self.assertFalse(saved_workout_matches(expected, actual))

    def test_interrupted_success_reconciles_without_another_put(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Mock()
            remote = [fixture()]
            client.get.side_effect = lambda _: deepcopy(remote[0])

            def accepted_then_timeout(_, value):
                remote[0] = deepcopy(value)
                remote[0]["workoutSegments"][0]["workoutSteps"][0]["stepId"] = 999
                raise TimeoutError()

            client.update.side_effect = accepted_then_timeout
            service = GarminWorkouts(Path(directory) / "updates.sqlite", lambda: client)
            preview = service.call({"operation": "preview", "workoutId": 123}, [plan()])
            command = {"operation": "apply", "previewId": preview["previewId"]}
            with self.assertRaises(TimeoutError):
                service.call(command, [plan()])
            result = service.call(command, [plan()])
            self.assertTrue(result["reconciled"])
            client.update.assert_called_once()
            self.assertTrue(service.call(command, [plan()])["alreadyApplied"])

    def test_manual_targets_preserve_every_other_field(self):
        before = fixture()
        after, changes = manual_update(
            before, before, [{"index": 0, "weight": 82.5, "reps": 9}]
        )
        active = after["workoutSegments"][0]["workoutSteps"][0]["workoutSteps"][0]
        self.assertEqual(
            (active["weightValue"], active["endConditionValue"]), (82.5, 9)
        )
        active.update(weightValue=80, endConditionValue=8)
        self.assertEqual(after, before)
        for value in (
            [{"index": 0, "exerciseName": "OTHER"}],
            [{"index": 0, "weight": True}],
            [{"index": 0, "reps": 3.5}],
            [{"index": 999, "weight": 10}],
        ):
            with self.assertRaises(ValueError):
                manual_update(before, before, value)

    def test_revised_preview_supersedes_original_and_saves_manual_values(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Mock()
            remote = [fixture()]
            client.get.side_effect = lambda _: deepcopy(remote[0])
            client.update.side_effect = lambda _, value: remote.__setitem__(
                0, deepcopy(value)
            )
            service = GarminWorkouts(Path(directory) / "updates.sqlite", lambda: client)
            first = service.call({"operation": "preview", "workoutId": 123}, [plan()])
            revised = service.call(
                {
                    "operation": "revise",
                    "previewId": first["previewId"],
                    "useSuggestions": False,
                    "manualTargets": [{"index": 0, "weight": 75, "reps": 7}],
                },
                [plan()],
            )
            with self.assertRaises(Conflict):
                service.call(
                    {"operation": "apply", "previewId": first["previewId"]}, [plan()]
                )
            self.assertEqual(revised["changes"][0]["after"], 75)
            service.call(
                {"operation": "apply", "previewId": revised["previewId"]}, [plan()]
            )
            client.update.assert_called_once()
            self.assertEqual(
                remote[0]["workoutSegments"][0]["workoutSteps"][0]["workoutSteps"][0][
                    "weightValue"
                ],
                75,
            )

    def test_mismatch_review_and_missing_exercises_are_unchanged(self):
        for p in [
            plan(
                [
                    {"weight": 85, "reps": 10},
                    {"weight": 85, "reps": 11},
                    {"weight": 85, "reps": 12},
                ]
            ),
            dict(plan(), stale=True),
            dict(plan(), exercises=[{"name": "Other", "proposed": []}]),
        ]:
            after, changes, skipped = make_update(fixture(), p)
            self.assertEqual(after, fixture())
            self.assertEqual(changes, [])
            self.assertTrue(skipped)

    def test_non_kg_leaves_weight_alone_and_timed_steps_untouched(self):
        before = fixture()
        active = before["workoutSegments"][0]["workoutSteps"][0]["workoutSteps"][0]
        active["weightUnit"]["unitKey"] = "pound"
        _, changes, skipped = make_update(before, plan())
        self.assertEqual(changes, [])
        self.assertTrue(skipped)
        active["endCondition"]["conditionTypeKey"] = "time"
        after, changes, _ = make_update(before, plan())
        self.assertEqual(after, before)

    def test_individual_sets_receive_individual_targets(self):
        before = fixture()
        base = before["workoutSegments"][0]["workoutSteps"][0]["workoutSteps"][0]
        before["workoutSegments"][0]["workoutSteps"] = [
            deepcopy(base),
            dict(base, stepId=12, stepOrder=4),
        ]
        after, _, _ = make_update(
            before, plan([{"weight": 85, "reps": 10}, {"weight": 80, "reps": 11}])
        )
        self.assertEqual(
            [
                (s["weightValue"], s["endConditionValue"])
                for s in after["workoutSegments"][0]["workoutSteps"]
            ],
            [(85, 10), (80, 11)],
        )

    def test_preview_apply_is_durable_idempotent_and_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Mock()
            remote = [fixture()]
            client.get.side_effect = lambda _: deepcopy(remote[0])
            client.update.side_effect = lambda _, value: remote.__setitem__(
                0, deepcopy(value)
            )
            service = GarminWorkouts(Path(directory) / "updates.sqlite", lambda: client)
            preview = service.call(
                {"operation": "preview", "workoutId": 123, "planType": "upper1"},
                [plan()],
            )
            client.update.assert_not_called()
            command = {"operation": "apply", "previewId": preview["previewId"]}
            self.assertTrue(service.call(command, [plan()])["ok"])
            again = GarminWorkouts(service.path, lambda: client).call(command, [plan()])
            self.assertTrue(again["alreadyApplied"])
            client.update.assert_called_once()

    def test_remote_edit_or_changed_plan_prevents_write(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Mock()
            client.get.return_value = fixture()
            service = GarminWorkouts(Path(directory) / "updates.sqlite", lambda: client)
            preview = service.call(
                {"operation": "preview", "workoutId": 123, "planType": "upper1"},
                [plan()],
            )
            command = {"operation": "apply", "previewId": preview["previewId"]}
            with self.assertRaises(Conflict):
                service.call(command, [dict(plan(), stale=True)])
            client.get.return_value = dict(fixture(), workoutName="Changed elsewhere")
            with self.assertRaises(Conflict):
                service.call(command, [plan()])
            client.update.assert_not_called()

    def test_ambiguous_network_failure_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Mock()
            client.get.return_value = fixture()
            client.update.side_effect = TimeoutError()
            service = GarminWorkouts(Path(directory) / "updates.sqlite", lambda: client)
            preview = service.call(
                {"operation": "preview", "workoutId": 123, "planType": "upper1"},
                [plan()],
            )
            command = {"operation": "apply", "previewId": preview["previewId"]}
            with self.assertRaises(TimeoutError):
                service.call(command, [plan()])
            with self.assertRaises(Conflict):
                service.call(command, [plan()])
            client.update.assert_called_once()
