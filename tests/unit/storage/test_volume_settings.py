from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from zoneinfo import ZoneInfo

from reptrace.storage.state import WebState, Conflict


class VolumeSettingsTests(unittest.TestCase):
    def test_persistence_revision_and_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            state = WebState(Path(folder) / "state.sqlite")
            settings = {
                "bodyWeightKg": 80,
                "exercises": {
                    "Pull Up": {"multiplier": 1.2, "bodyweight": 1, "assistance": False}
                },
            }

            def save(value, rev=None):
                return state.apply(
                    {
                        "action": "volume_save",
                        "requestId": str(uuid.uuid4()),
                        "metadataRevision": rev or state.read()["metadataRevision"],
                        "settings": value,
                    },
                    None,
                    "Test",
                    ZoneInfo("UTC"),
                )

            revision = state.read()["metadataRevision"]
            save(settings)
            self.assertEqual(
                WebState(Path(folder) / "state.sqlite").read()["volumeSettings"],
                settings,
            )
            with self.assertRaises(Conflict):
                save(settings, revision)
            for key, value in [
                ("multiplier", 0),
                ("multiplier", float("inf")),
                ("bodyweight", 1.1),
                ("bodyweight", None),
                ("assistance", "false"),
                ("reviewed", "yes"),
            ]:
                bad = {
                    "bodyWeightKg": 80,
                    "exercises": {
                        "Pull Up": dict(
                            settings["exercises"]["Pull Up"], **{key: value}
                        )
                    },
                }
                with self.assertRaises(ValueError):
                    save(bad)
            self.assertEqual(state.read()["volumeSettings"], settings)

    def test_custom_profile_review_is_explicit_and_persisted(self):
        with tempfile.TemporaryDirectory() as folder:
            state = WebState(Path(folder) / "state.sqlite")
            settings = {
                "bodyWeightKg": None,
                "exercises": {
                    "Custom machine": {
                        "multiplier": 0.5,
                        "bodyweight": 0,
                        "assistance": False,
                        "reviewed": True,
                    }
                },
            }
            state.apply(
                {
                    "action": "volume_save",
                    "requestId": str(uuid.uuid4()),
                    "metadataRevision": state.read()["metadataRevision"],
                    "settings": settings,
                },
                None,
                "Test",
                ZoneInfo("UTC"),
            )
            self.assertEqual(
                WebState(Path(folder) / "state.sqlite").read()["volumeSettings"],
                settings,
            )

    def test_load_conventions_are_validated_and_persisted(self):
        with tempfile.TemporaryDirectory() as folder:
            state = WebState(Path(folder) / "state.sqlite")

            def save(copies):
                settings = {
                    "bodyWeightKg": None,
                    "exercises": {
                        "Lateral Raise": {
                            "multiplier": 1.375,
                            "bodyweight": 0,
                            "assistance": False,
                            "loadCopies": copies,
                        }
                    },
                }
                state.apply(
                    {
                        "action": "volume_save",
                        "requestId": str(uuid.uuid4()),
                        "metadataRevision": state.read()["metadataRevision"],
                        "settings": settings,
                    },
                    None,
                    "Test",
                    ZoneInfo("UTC"),
                )

            save(2)
            self.assertEqual(
                state.read()["volumeSettings"]["exercises"]["Lateral Raise"][
                    "loadCopies"
                ],
                2,
            )
            for copies in [None, 0, 3, 1.5, True]:
                with self.assertRaises(ValueError):
                    save(copies)
            save(1)
            self.assertEqual(
                state.read()["volumeSettings"]["exercises"]["Lateral Raise"][
                    "loadCopies"
                ],
                1,
            )


if __name__ == "__main__":
    unittest.main()
