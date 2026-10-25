"""Run inside the Compose network; only writes to its own temporary database."""

import copy
import os
import tempfile
import uuid
from zoneinfo import ZoneInfo
from influxdb import InfluxDBClient
from reptrace.storage.state import WebState, Conflict, snapshot, snapshot_rows, revision
from reptrace.web.server import build_payload

name = "FormIntegration_" + uuid.uuid4().hex
options = dict(
    host=os.getenv("INFLUXDB_HOST", "influxdb"),
    port=int(os.getenv("INFLUXDB_PORT", "8086")),
    username=os.getenv("INFLUXDB_USERNAME"),
    password=os.getenv("INFLUXDB_PASSWORD"),
    database=name,
)
admin = InfluxDBClient(**options)
zone = ZoneInfo("Europe/Kyiv")


def factory():
    client = InfluxDBClient(**options)
    return client, lambda q: list(client.query(q).get_points())


def action(**values):
    return dict(requestId=str(uuid.uuid4()), **values)


try:
    admin.create_database(name)
    tags = {"ActivityID": "123", "Device": "Watch", "Database_Name": name}
    points = [
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
            "measurement": "ActivitySummary",
            "time": "2026-10-01T10:00:00Z",
            "tags": dict(tags, ActivitySelector="END"),
            "fields": {
                "Activity_ID": 123,
                "activityName": "Upper",
                "activityType": "strength_training_end",
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
                "setCount": 1,
                "setNumber": 1,
                "setOrder": 1,
                "durationSeconds": 30.0,
            },
        },
    ]
    assert admin.write_points(points)
    query = lambda q: list(admin.query(q).get_points())
    with tempfile.TemporaryDirectory() as directory:
        state = WebState(directory + "/state.sqlite")
        original = snapshot(query, "123")
        rev = revision(snapshot_rows(original))
        payload = build_payload(
            snapshot_rows(original),
            [
                dict(p["fields"], **p["tags"], time=p["time"])
                for p in original
                if p["measurement"] == "ActivitySummary"
            ],
            [],
        )
        assert payload["workouts"][0]["revision"] == rev
        change = action(
            action="workout_save",
            sessionId="123",
            revision=rev,
            sets=[
                {
                    "id": "123:1",
                    "exercise": "Bench Press",
                    "weight": 85,
                    "reps": 5,
                    "note": "Correction",
                }
            ],
        )
        result = state.apply(change, factory, name, zone)
        assert state.apply(change, factory, name, zone) == result
        # Simulate process exit after Influx success but before journal completion.
        with state.connect() as c:
            c.execute(
                "UPDATE audit SET status='pending' WHERE id=?", (change["requestId"],)
            )
        assert state.apply(change, factory, name, zone) == result
        with state.connect() as c:
            assert (
                c.execute(
                    "SELECT status FROM audit WHERE id=?", (change["requestId"],)
                ).fetchone()[0]
                == "done"
            )
        edited = snapshot(query, "123")
        rows = snapshot_rows(edited)
        assert rows[0]["weightKg"] == 85 and rows[0]["volumeKg"] == 425
        assert rows[0]["source"] == "Manual Web"
        assert len([p for p in edited if p["measurement"] == "ActivitySummary"]) == 2
        assert len(query('SELECT * FROM "StrengthSetWebArchive"')) == 1
        assert len(query('SELECT * FROM "StrengthManualSession"')) == 1
        stale = dict(change, requestId=str(uuid.uuid4()))
        try:
            state.apply(stale, factory, name, zone)
        except Conflict:
            pass
        else:
            raise AssertionError("Stale edit accepted")
        second = action(
            action="workout_save",
            sessionId="123",
            revision=revision(rows),
            sets=[
                {
                    "id": "123:1",
                    "exercise": "Barbell Bench Press",
                    "weight": 90,
                    "reps": None,
                }
            ],
        )
        state.apply(second, factory, name, zone)
        assert "volumeKg" not in snapshot_rows(snapshot(query, "123"))[0]
        try:
            state.apply(
                action(action="undo_workout", id=change["requestId"]),
                factory,
                name,
                zone,
            )
        except Conflict:
            pass
        else:
            raise AssertionError("Undo accepted over newer edit")
        state.apply(
            action(action="undo_workout", id=second["requestId"]), factory, name, zone
        )
        state.apply(
            action(action="undo_workout", id=change["requestId"]), factory, name, zone
        )
        assert revision(snapshot_rows(snapshot(query, "123"))) == rev
        assert snapshot(query, "123") == original
        new = action(
            action="workout_save",
            date="2026-10-02",
            name="Manual session",
            durationMinutes=45,
            sets=[
                {"exercise": "Barbell Bench Press", "weight": 90, "reps": 5},
                {"exercise": "New exercise", "weight": None, "reps": 8},
            ],
        )
        saved = state.apply(new, factory, name, zone)
        assert len(snapshot_rows(snapshot(query, saved["sessionId"]))) == 2
        assert state.apply(new, factory, name, zone) == saved
        state.apply(
            action(action="undo_workout", id=new["requestId"]), factory, name, zone
        )
        assert not snapshot(query, saved["sessionId"])
        # Full-session delete keeps a sync tombstone and can restore every original point.
        deletion = action(
            action="workout_delete",
            sessionId="123",
            revision=rev,
            expectedMetadata={"name": "Upper", "date": "2026-10-01", "duration": 3600},
        )
        state.apply(deletion, factory, name, zone)
        deleted = snapshot(query, "123")
        assert len(deleted) == 1 and deleted[0]["fields"]["deleted"] is True
        assert not snapshot_rows(deleted)
        assert state.apply(deletion, factory, name, zone)["ok"]
        state.apply(
            action(action="undo_workout", id=deletion["requestId"]), factory, name, zone
        )
        assert snapshot(query, "123") == original
        # Renaming, re-dating and duration edits preserve unrelated metadata and round-trip.
        metadata_edit = action(
            action="workout_save",
            sessionId="123",
            revision=rev,
            name="Upper 1",
            date="2026-10-02",
            durationMinutes=45,
            sets=[
                {
                    "id": "123:1",
                    "exercise": "Barbell Bench Press",
                    "weight": 80,
                    "reps": 5,
                }
            ],
        )
        state.apply(metadata_edit, factory, name, zone)
        revised = snapshot(query, "123")
        summary = next(
            p
            for p in revised
            if p["measurement"] == "ActivitySummary"
            and p["fields"]["activityType"] == "strength_training"
        )
        assert (
            summary["fields"]["elapsedDuration"] == 2700
            and summary["fields"]["averageHR"] == 122
        )
        assert summary["fields"]["activityName"] == "Upper 1" and summary[
            "time"
        ].startswith("2026-10-02")
        assert snapshot_rows(revised)[0]["sourceDate"] == "2026-10-02"
        stale_meta = action(
            action="workout_delete",
            sessionId="123",
            revision=revision(snapshot_rows(revised)),
            expectedMetadata={"name": "Upper", "date": "2026-10-01", "duration": 3600},
        )
        try:
            state.apply(stale_meta, factory, name, zone)
        except Conflict:
            pass
        else:
            raise AssertionError("Stale metadata accepted")
        state.apply(
            action(action="undo_workout", id=metadata_edit["requestId"]),
            factory,
            name,
            zone,
        )
        assert snapshot(query, "123") == original
        # Restore originals if a write fails after deletions.
        failure = action(
            action="workout_save",
            sessionId="123",
            revision=rev,
            sets=[
                {
                    "id": "123:1",
                    "exercise": "Barbell Bench Press",
                    "weight": 82.5,
                    "reps": 5,
                }
            ],
        )

        def failing_factory():
            client, q = factory()
            write = client.write_points

            def write_once(points, *args, **kwargs):
                if any(
                    p["measurement"] == "StrengthSet"
                    and p["fields"].get("weightKg") == 82.5
                    for p in points
                ):
                    raise RuntimeError("Injected write failure")
                return write(points, *args, **kwargs)

            client.write_points = write_once
            return client, q

        try:
            state.apply(failure, failing_factory, name, zone)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Injected failure did not fire")
        assert snapshot(query, "123") == original
        # Retrying the exact interrupted request after rollback is safe and idempotent.
        retried = state.apply(failure, factory, name, zone)
        assert snapshot_rows(snapshot(query, "123"))[0]["weightKg"] == 82.5
        assert state.apply(failure, factory, name, zone) == retried
        # An ambiguous journal must never overwrite different current contents.
        with state.connect() as c:
            c.execute(
                "UPDATE audit SET status='pending' WHERE id=?", (failure["requestId"],)
            )
        modified = snapshot(query, "123")
        next(p for p in modified if p["measurement"] == "StrengthSet")["fields"][
            "weightKg"
        ] = 83.0
        assert admin.write_points(modified)
        try:
            state.apply(failure, factory, name, zone)
        except Conflict:
            pass
        else:
            raise AssertionError("Ambiguous interrupted write was retried")
        assert snapshot_rows(snapshot(query, "123"))[0]["weightKg"] == 83
    print(
        "PASS: real Influx saves, schema, revisions, idempotency, stale conflicts, archives, chained undo, new-workout undo, whole-session deletion/tombstone/undo, metadata edits, failure recovery, interrupted-success reconciliation, rolled-back retry, ambiguous retry protection"
    )
finally:
    admin.drop_database(name)
    admin.close()
