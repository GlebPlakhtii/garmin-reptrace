"""The Python and browser consumers must use the same packaged definitions."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest

from reptrace.training.catalog import (
    BODYWEIGHT_CATEGORIES,
    CATALOG,
    DEFAULT_MUSCLES,
    DEFAULT_VOLUME_PROFILES,
    EXERCISE_NAME_ALIASES,
    EXERCISES,
    MUSCLE_GROUPS,
    MUSCLE_INVOLVEMENT,
)
from reptrace.training.muscles import DEFAULT_MUSCLES as EXPORT_MUSCLES
from reptrace.training.strength import EXERCISE_NAME_ALIASES as IMPORT_ALIASES
from reptrace.storage.state import GROUPS as ALLOWED_MUSCLES


class CatalogTests(unittest.TestCase):
    def test_catalog_references_known_groups_and_complete_profiles(self):
        self.assertEqual(CATALOG["schemaVersion"], 1)
        self.assertEqual(len(MUSCLE_GROUPS), len(set(MUSCLE_GROUPS)))
        groups = set(MUSCLE_GROUPS)
        for name, entry in EXERCISES.items():
            with self.subTest(exercise=name):
                if "muscle" in entry:
                    self.assertIn(entry["muscle"], groups)
                    self.assertIn("volume", entry)
                if "roles" in entry:
                    roles = entry["roles"]
                    self.assertTrue(roles["primary"])
                    self.assertLessEqual(set(roles["primary"] + roles["secondary"]), groups)
                    self.assertFalse(set(roles["primary"]) & set(roles["secondary"]))
                if "volume" in entry:
                    self.assertIn(entry["volume"]["confidence"], {"estimate", "calibrate", "unidentified"})
                    self.assertIsInstance(entry["volume"]["assistance"], bool)
        for alias, canonical in EXERCISE_NAME_ALIASES.items():
            with self.subTest(alias=alias):
                self.assertIn(canonical, EXERCISES)
                self.assertNotEqual(alias, canonical)
                self.assertNotIn(canonical, EXERCISE_NAME_ALIASES)

    def test_compatibility_imports_share_definitions_without_renaming_history(self):
        self.assertIs(EXPORT_MUSCLES, DEFAULT_MUSCLES)
        self.assertIs(IMPORT_ALIASES, EXERCISE_NAME_ALIASES)
        self.assertEqual(ALLOWED_MUSCLES, set(MUSCLE_GROUPS))
        self.assertEqual(EXERCISE_NAME_ALIASES["Weighted Leg Curl"], "Lying Leg Curl")
        self.assertEqual(DEFAULT_MUSCLES["Weighted Leg Curl"], "Hamstrings")
        self.assertEqual(DEFAULT_MUSCLES["Lying Leg Curl"], "Hamstrings")
        self.assertEqual(MUSCLE_INVOLVEMENT["Barbell Squat"]["primary"], ["Quads", "Glutes"])
        self.assertEqual(DEFAULT_VOLUME_PROFILES["Romanian Deadlift"]["confidence"], "unidentified")

    @unittest.skipUnless(shutil.which("node"), "Native ESM agreement requires Node.js")
    def test_browser_and_python_agree_on_every_catalog_definition(self):
        root = Path(__file__).resolve().parents[3]
        result = subprocess.run(
            [
                "node", "--input-type=module", "-e",
                """
                import * as model from './src/reptrace/web/static/model.mjs';
                import catalog from './src/reptrace/training/exercise_catalog.json' with {type:'json'};
                console.log(JSON.stringify({
                  groups:model.MUSCLE_GROUPS,
                  aliases:model.EXERCISE_NAME_ALIASES,
                  bodyweight:model.BODYWEIGHT_CATEGORIES,
                  muscles:model.DEFAULT_MUSCLES,
                  volumes:model.DEFAULT_VOLUME_PROFILES,
                  roles:Object.fromEntries(Object.keys(catalog.exercises).map(name=>[name,model.exerciseMuscles(name)]))
                }));
                """,
            ],
            cwd=root, text=True, capture_output=True, check=True, timeout=15,
        )
        actual = json.loads(result.stdout)
        self.assertEqual(actual["groups"], MUSCLE_GROUPS)
        self.assertEqual(actual["aliases"], EXERCISE_NAME_ALIASES)
        self.assertEqual(set(actual["bodyweight"]), BODYWEIGHT_CATEGORIES)
        self.assertEqual(actual["muscles"], DEFAULT_MUSCLES)
        self.assertEqual(actual["volumes"], DEFAULT_VOLUME_PROFILES)
        self.assertEqual(actual["roles"], {
            name: entry.get("roles", {"primary": [entry.get("muscle", "Unassigned")], "secondary": []})
            for name, entry in EXERCISES.items()
        })
