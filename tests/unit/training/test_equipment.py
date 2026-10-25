import copy
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from zoneinfo import ZoneInfo

from reptrace.training.equipment import validate_equipment
from reptrace.storage.state import WebState, Conflict
from reptrace.training.planning import build_next_sessions

NAME = "Barbell Bench Press"


def equipment(loads=(80, 85, 90)):
    return {
        "profiles": {"rack": {"name": "Gym rack", "loads": list(loads)}},
        "assignments": {NAME: "rack"},
    }


def training(loads=(80, 85, 90)):
    return {
        "equipment": equipment(loads),
        "workouts": [
            {"id": "a", "name": "Upper 1", "date": "2026-10-13"},
            {"id": "b", "name": "Upper 1", "date": "2026-10-20"},
        ],
        "sets": [
            {"sessionId": identity, "exercise": NAME, "weight": 80, "reps": 12}
            for identity in ("a", "b")
        ],
    }


def exercise(data):
    return build_next_sessions(data, "2026-10-21")[0]["exercises"][0]


class EquipmentTests(unittest.TestCase):
    def test_normalizes_inventory_and_rejects_invalid_assignments_and_loads(self):
        self.assertEqual(
            validate_equipment(equipment((85, 80, 85)))["profiles"]["rack"]["loads"],
            [80, 85],
        )
        for loads in ([], [True], [float("nan")], [-1], [2001], ["80"]):
            with self.subTest(loads=loads), self.assertRaises(ValueError):
                validate_equipment(equipment(loads))
        bad = equipment()
        bad["assignments"][NAME] = "missing"
        with self.assertRaises(ValueError):
            validate_equipment(bad)

    def test_profile_overrides_fixed_increment_without_mutating_history(self):
        data = training()
        data["progressionRules"] = {NAME: {"repMin": 6, "repMax": 12, "weightStep": 1}}
        original = copy.deepcopy(data)
        result = exercise(data)
        self.assertEqual(result["status"], "weight_progress")
        self.assertEqual(result["proposed"], [{"weight": 85, "reps": 6}])
        self.assertEqual(result["rule"]["equipmentName"], "Gym rack")
        self.assertEqual(data, original)

    def test_maximum_unavailable_and_large_jump_require_review(self):
        for loads in ((80,), (80, 100), (75, 85)):
            with self.subTest(loads=loads):
                result = exercise(training(loads))
                self.assertEqual(result["status"], "review")
                self.assertEqual(result["proposed"][0]["weight"], 80)

    def test_unassigned_exercise_keeps_existing_progression(self):
        data = training()
        data["equipment"]["assignments"] = {}
        self.assertEqual(exercise(data)["proposed"][0]["weight"], 82.5)

    def test_saved_profiles_persist_conflict_and_clear_assignments(self):
        with tempfile.TemporaryDirectory() as directory:
            state = WebState(Path(directory) / "state.sqlite")

            def save(value, revision=None):
                body = {
                    "action": "equipment_save",
                    "requestId": str(uuid.uuid4()),
                    "equipment": value,
                    "metadataRevision": revision or state.read()["metadataRevision"],
                }
                return state.apply(body, None, "Test", ZoneInfo("Europe/Kyiv"))

            initial = state.read()["metadataRevision"]
            save(equipment())
            self.assertEqual(WebState(state.path).read()["equipment"], equipment())
            with self.assertRaises(Conflict):
                save(equipment((80, 82)), initial)
            bad = equipment()
            bad["profiles"] = {}
            with self.assertRaises(ValueError):
                save(bad)
            self.assertEqual(state.read()["equipment"], equipment())
            save({"profiles": {}, "assignments": {}})
            self.assertEqual(state.read()["equipment"]["assignments"], {})
