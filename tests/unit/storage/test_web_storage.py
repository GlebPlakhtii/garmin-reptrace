from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from zoneinfo import ZoneInfo

from reptrace.storage.state import (
    WebState,
    Conflict,
    plan_workout,
    revision,
    snapshot_rows,
    numeric,
)

ZONE = ZoneInfo("Europe/Kyiv")
CATALOG = {"Barbell Bench Press": ("BENCH_PRESS", "BARBELL_BENCH_PRESS")}


def request(**kwargs):
    return dict(requestId=str(uuid.uuid4()), **kwargs)


def fixture():
    tags = {"ActivityID": "123", "Device": "Watch", "Database_Name": "Test"}
    return [
        {
            "measurement": "ActivitySummary",
            "time": "2026-10-01T09:00:00Z",
            "tags": dict(tags, ActivitySelector="start"),
            "fields": {
                "activityType": "strength_training",
                "activityName": "Upper",
                "Activity_ID": 123,
                "averageHR": 122,
                "elapsedDuration": 3600.0,
            },
        },
        {
            "measurement": "StrengthSet",
            "time": "2026-10-01T09:00:01Z",
            "tags": dict(
                tags,
                Exercise="Barbell Bench Press",
                ExerciseCategory="BENCH_PRESS",
                SetIndex="1",
            ),
            "fields": {
                "weightKg": 80.0,
                "reps": 5,
                "volumeKg": 400.0,
                "estimated1RMKg": 93.3,
                "source": "Garmin",
                "exerciseCode": "BARBELL_BENCH_PRESS",
                "durationSeconds": 30.0,
            },
        },
    ]


class StorageTests(unittest.TestCase):
    def test_submitting_existing_date_preserves_garmin_set_timing(self):
        before = fixture()
        body = request(
            date="2026-10-01",
            revision=revision(snapshot_rows(before)),
            sets=[
                {
                    "id": "123:1",
                    "exercise": "Barbell Bench Press",
                    "weight": 85,
                    "reps": 5,
                }
            ],
        )
        _, points, _ = plan_workout(
            body, before, CATALOG, "Test", ZONE, body["requestId"]
        )
        row = snapshot_rows(points)[0]
        self.assertEqual(row["time"], before[1]["time"])
        self.assertNotIn("timeAccuracy", row)
        self.assertEqual(
            next(p for p in points if p["measurement"] == "ActivitySummary"), before[0]
        )

    def test_moving_overnight_workout_preserves_day_offsets_and_set_times(self):
        before = fixture()
        before[0]["time"] = "2026-10-01T20:50:00Z"
        before[1]["time"] = "2026-10-01T21:05:00Z"
        end = dict(
            before[0],
            time="2026-10-01T21:30:00Z",
            fields=dict(before[0]["fields"], activityType="strength_training_end"),
        )
        before.append(end)
        body = request(
            date="2026-10-03",
            revision=revision(snapshot_rows(before)),
            sets=[
                {
                    "id": "123:1",
                    "exercise": "Barbell Bench Press",
                    "weight": 80,
                    "reps": 5,
                }
            ],
        )
        _, points, _ = plan_workout(
            body, before, CATALOG, "Test", ZONE, body["requestId"]
        )
        self.assertEqual(snapshot_rows(points)[0]["time"], "2026-10-03T21:05:00+00:00")
        summaries = [p for p in points if p["measurement"] == "ActivitySummary"]
        self.assertEqual(summaries[1]["time"], "2026-10-03T21:30:00+00:00")

    def test_new_workout_alias_and_missing_metrics(self):
        body = request(
            date="2026-10-01",
            name="Upper",
            sets=[{"exercise": "Bench Press", "weight": 80, "reps": None}],
        )
        identity, points, name = plan_workout(
            body, [], CATALOG, "Test", ZONE, body["requestId"]
        )
        row = snapshot_rows(points)[0]
        self.assertEqual(row["Exercise"], "Barbell Bench Press")
        self.assertNotIn("volumeKg", row)
        self.assertNotIn("estimated1RMKg", row)
        self.assertEqual(row["source"], "Manual Web")
        self.assertTrue(identity.startswith("web-"))

    def test_edit_preserves_metadata_and_clears_stale_derived_values(self):
        before = fixture()
        body = request(
            revision=revision(snapshot_rows(before)),
            sets=[
                {
                    "id": "123:1",
                    "exercise": "Barbell Bench Press",
                    "weight": 85,
                    "reps": None,
                }
            ],
        )
        _, points, _ = plan_workout(
            body, before, CATALOG, "Test", ZONE, body["requestId"]
        )
        self.assertEqual(points[-2], before[0])
        row = snapshot_rows(points)[0]
        self.assertEqual(row["durationSeconds"], 30)
        self.assertEqual(row["weightKg"], 85)
        self.assertNotIn("volumeKg", row)
        self.assertNotIn("estimated1RMKg", row)
        self.assertTrue(
            any(p["measurement"] == "StrengthManualSession" for p in points)
        )

    def test_stale_and_repeated_set_edits_are_rejected(self):
        before = fixture()
        body = request(revision="stale", sets=[])
        with self.assertRaises(Conflict):
            plan_workout(body, before, CATALOG, "Test", ZONE, body["requestId"])
        body.update(
            revision=revision(snapshot_rows(before)),
            sets=[
                {
                    "id": "123:1",
                    "exercise": "Barbell Bench Press",
                    "weight": 80,
                    "reps": 5,
                }
            ]
            * 2,
        )
        with self.assertRaisesRegex(ValueError, "repeated"):
            plan_workout(body, before, CATALOG, "Test", ZONE, body["requestId"])

    def test_numeric_input_rejects_nonfinite_boolean_and_fractional_reps(self):
        for value in [True, float("nan"), float("inf"), -1, 500.5]:
            with self.assertRaises(ValueError):
                numeric(value, "reps", True, 500)
        self.assertEqual(numeric(0, "weight"), 0)
        self.assertIsNone(numeric("", "weight"))

    def test_goals_settings_are_durable_idempotent_and_archivable(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.sqlite"
            state = WebState(path)
            goal = request(
                action="goal_save",
                goal={
                    "exercise": "Bench Press",
                    "reps": "5",
                    "weight": "100",
                    "deadline": "2027-01-01",
                },
            )
            state.apply(goal, None, "Test", ZONE)
            state.apply(goal, None, "Test", ZONE)
            self.assertEqual(len(state.read()["goals"]), 1)
            with self.assertRaises(Conflict):
                state.apply(dict(goal, goal={"exercise": "Curl"}), None, "Test", ZONE)
            state.apply(
                request(action="goal_archive", id=goal["requestId"]), None, "Test", ZONE
            )
            self.assertEqual(state.read()["goals"], [])
            self.assertEqual(len(state.read()["archivedGoals"]), 1)
            state.apply(
                request(action="muscle_save", mappings={"Curl": "Biceps"}),
                None,
                "Test",
                ZONE,
            )
            restored = WebState(path).read()
            self.assertEqual(restored["muscleOverrides"], {"Curl": "Biceps"})
            self.assertEqual(
                restored["archivedGoals"][0]["exercise"], "Barbell Bench Press"
            )
            with self.assertRaises(ValueError):
                state.apply(
                    request(action="muscle_save", mappings={"Curl": "Invalid"}),
                    None,
                    "Test",
                    ZONE,
                )


class AtomicProgressionTests(unittest.TestCase):
    def test_setting_one_rule_preserves_other_exercises(self):
        with tempfile.TemporaryDirectory() as directory:
            state = WebState(Path(directory) / "state.sqlite")
            state.apply(
                request(
                    action="progression_save",
                    mappings={"Curl": {"repMin": 8, "repMax": 12, "weightStep": 1}},
                ),
                None,
                "Test",
                ZONE,
            )
            state.apply(
                request(
                    action="progression_set",
                    exercise="Barbell Bench Press",
                    rule={"repMin": 6, "repMax": 10, "weightStep": 2.5},
                ),
                None,
                "Test",
                ZONE,
            )
            rules = state.read()["progressionRules"]
            self.assertEqual(rules["Curl"]["weightStep"], 1)
            self.assertEqual(rules["Barbell Bench Press"]["repMax"], 10)


if __name__ == "__main__":
    unittest.main()


class ConcurrentStorageTests(unittest.TestCase):
    def test_distinct_workers_cannot_both_overwrite_the_same_settings_revision(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite"
            a, b = WebState(path), WebState(path)
            rev = a.read()["metadataRevision"]
            start = Barrier(2)

            def save(state, name):
                start.wait(timeout=5)
                try:
                    state.apply(
                        request(
                            action="muscle_save",
                            metadataRevision=rev,
                            mappings={name: "Back"},
                        ),
                        None,
                        "Test",
                        ZONE,
                    )
                    return "saved"
                except Conflict:
                    return "conflict"

            with ThreadPoolExecutor(2) as pool:
                futures = [
                    pool.submit(save, a, "Exercise A"),
                    pool.submit(save, b, "Exercise B"),
                ]
                self.assertCountEqual(
                    [f.result(timeout=10) for f in futures], ["saved", "conflict"]
                )
            self.assertEqual(len(WebState(path).read()["muscleOverrides"]), 1)

    def test_mutation_lock_remains_held_across_audit_commits_and_releases_on_failure(
        self,
    ):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite"
            a, b = WebState(path), WebState(path)
            entered = Event()
            acquired = Event()

            def contender():
                entered.set()
                with b.mutation_lock():
                    acquired.set()

            with ThreadPoolExecutor(1) as pool:
                with a.mutation_lock():
                    with a.connect() as c:
                        c.commit()
                    future = pool.submit(contender)
                    self.assertTrue(entered.wait(timeout=5))
                    self.assertFalse(acquired.wait(timeout=0.05))
                future.result(timeout=5)
            self.assertTrue(acquired.is_set())
            try:
                with a.mutation_lock():
                    raise RuntimeError("injected")
            except RuntimeError:
                pass
            with b.mutation_lock():
                pass
