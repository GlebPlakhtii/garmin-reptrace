from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

from reptrace.garmin.workouts import (
    GarminWorkouts,
    append_exercise,
    garmin_exercise_catalog,
    executed_steps,
    playback_signature,
    saved_workout_matches,
)
from reptrace.storage.state import Conflict
from reptrace.coaching.assistant import TrainingTools
from reptrace.telegram.bot import Bot
from tests.unit.garmin.test_garmin_workouts import fixture


class AdditionTests(unittest.TestCase):
    def test_catalogue_explains_captains_chair_without_inventing_an_exact_code(self):
        result = garmin_exercise_catalog("capitan chair legs raise")
        self.assertIn(
            {
                "category": "LEG_RAISE",
                "exerciseCode": "",
                "name": "Leg Raise",
                "generic": True,
            },
            result["exercises"],
        )
        self.assertIn("no dedicated code", result["note"])
        self.assertTrue(all(r["category"] == "LEG_RAISE" for r in result["exercises"]))

    def test_verifier_accepts_only_neutral_metadata_and_rejects_meaningful_changes(
        self,
    ):
        before = fixture()
        after = deepcopy(before)
        step = after["workoutSegments"][0]["workoutSteps"][0]["workoutSteps"][0]
        step.update(
            secondaryTargetType=None,
            targetValueOne=None,
            equipmentType={
                "equipmentTypeId": 0,
                "equipmentTypeKey": None,
                "displayOrder": 0,
            },
        )
        self.assertTrue(saved_workout_matches(before, after))
        step["endConditionValue"] = 15
        self.assertFalse(saved_workout_matches(before, after))
        step["endConditionValue"] = 8
        step["equipmentType"]["equipmentTypeId"] = 2
        self.assertFalse(saved_workout_matches(before, after))

    def setup_service(self, path):
        remote = [fixture()]
        client = Mock()
        client.get.side_effect = lambda _: deepcopy(remote[0])
        client.update.side_effect = lambda _, value: remote.__setitem__(
            0, deepcopy(value)
        )
        return GarminWorkouts(path, lambda: client), remote, client

    def body(self, details, **overrides):
        args = dict(
            category="LEG_RAISE",
            code="",
            sets_count=2,
            reps=15,
            weight=0,
            rest_seconds=None,
            notes="Captain's chair leg raise",
        )
        args.update(overrides)
        return append_exercise(details, **args)

    def test_addition_preserves_original_playback_and_only_applies_after_confirmation(
        self,
    ):
        with tempfile.TemporaryDirectory() as d:
            service, remote, client = self.setup_service(Path(d) / "garmin.sqlite")
            before = deepcopy(remote[0])
            details = service.call({"operation": "details", "workoutId": 123}, [])
            body = self.body(details)
            preview = service.call(body, [])
            client.update.assert_not_called()
            service.call({"operation": "apply", "previewId": preview["previewId"]}, [])
            old = [s for _, s, _ in executed_steps(before)]
            new = [s for _, s, _ in executed_steps(remote[0])]
            self.assertEqual(
                [playback_signature(s) for s in old],
                [playback_signature(s) for s in new[: len(old)]],
            )
            additions = [s for s in new if s.get("category") == "LEG_RAISE"]
            self.assertEqual(len(additions), 2)
            self.assertTrue(
                all(
                    s["endConditionValue"] == 15 and s["weightValue"] == 0
                    for s in additions
                )
            )
            self.assertEqual(new[-1]["endConditionValue"], 90)
            service.call({"operation": "apply", "previewId": preview["previewId"]}, [])
            client.update.assert_called_once()
            with self.assertRaisesRegex(ValueError, "already"):
                self.body(service.call({"operation": "details", "workoutId": 123}, []))

    def test_concurrent_edits_and_invalid_targets_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            service, remote, client = self.setup_service(Path(d) / "garmin.sqlite")
            details = service.call({"operation": "details", "workoutId": 123}, [])
            remote[0]["workoutName"] = "Changed elsewhere"
            with self.assertRaises(Conflict):
                service.call(self.body(details), [])
            for override in (
                {"sets_count": True},
                {"reps": 0},
                {"weight": float("nan")},
                {"rest_seconds": 0},
                {"code": "INVENTED"},
                {"notes": ""},
            ):
                with self.assertRaises(ValueError):
                    self.body(details, **override)
            client.update.assert_not_called()

    def test_bot_uses_reviewable_full_edit_preview_and_drafts_without_saving(self):
        with tempfile.TemporaryDirectory() as d:
            service, remote, client = self.setup_service(Path(d) / "garmin.sqlite")
            state = {}
            tools = TrainingTools(
                {},
                state,
                garmin=lambda body: service.call(body, []),
                request_id="append",
            )
            result = tools.call(
                "propose_garmin_exercise_addition",
                {
                    "workout_id": 123,
                    "category": "LEG_RAISE",
                    "exercise_code": "",
                    "sets": 2,
                    "reps": 15,
                    "external_weight_kg": 0,
                    "rest_seconds": None,
                    "notes": "Captain's chair leg raise",
                },
            )
            self.assertFalse(result["saved"])
            client.update.assert_not_called()
            draft = state["pendingEdits"][result["draftId"]]
            self.assertTrue(draft["garminPreview"]["fullEdit"])
            api = Mock()
            bot = Bot(
                api,
                lambda: [],
                Path(d) / "bot.json",
                "42",
                garmin=lambda body: service.call(body, []),
            )
            bot.state.update(state)
            bot.send_edit_preview(result["draftId"])
            self.assertEqual(api.call.call_args.args[0], "sendMessage")
            self.assertIn("Captain's chair", api.call.call_args.args[1]["text"])
            self.assertIn("reply_markup", api.call.call_args.args[1])
            client.update.assert_not_called()
            bot.handle_edit("edit:save:" + result["draftId"])
            self.assertIn(
                "reviewed structure and targets", api.call.call_args.args[1]["text"]
            )
            client.update.assert_called_once()
