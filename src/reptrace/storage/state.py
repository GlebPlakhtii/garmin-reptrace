"""Persistent goals/settings and reversible, validated InfluxDB workout edits."""

from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import threading
import uuid

from reptrace.training.equipment import validate_equipment
from reptrace.training.strength import BODYWEIGHT_CATEGORIES, EXERCISE_NAME_ALIASES

MEASUREMENTS = (
    "StrengthSet",
    "StrengthExercise",
    "ActivitySummary",
    "StrengthManualSession",
)
TAGS = (
    "Device",
    "Database_Name",
    "ActivityID",
    "ActivitySelector",
    "Exercise",
    "ExerciseCategory",
    "SetIndex",
    "User_ID",
)
GROUPS = {
    "Chest",
    "Back",
    "Shoulders",
    "Biceps",
    "Triceps",
    "Quads",
    "Hamstrings",
    "Glutes",
    "Calves",
    "Core",
    "Adductors",
    "Unassigned",
}


class Conflict(ValueError):
    pass


def quote(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def revision(rows):
    clean = [{k: v for k, v in r.items() if v is not None} for r in rows]
    return hashlib.sha256(
        json.dumps(
            sorted(clean, key=lambda r: str(r.get("SetIndex", ""))),
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def snapshot_revision(points):
    return hashlib.sha256(
        json.dumps(
            sorted(points, key=lambda p: json.dumps(p, sort_keys=True)), sort_keys=True
        ).encode()
    ).hexdigest()


def snapshots_equal(first, second):
    """Compare Influx readback without confusing UTC or numeric serialization."""

    def clean(points):
        result = []
        for point in points:
            stamp = point["time"]
            fraction = re.search(r"\.(\d+)", stamp)
            nanos = fraction.group(1)[6:].rstrip("0") if fraction else ""
            value = dict(
                point,
                time=datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                .astimezone(timezone.utc)
                .isoformat(),
                submicrosecond=nanos,
            )
            result.append(value)
        return sorted(
            result,
            key=lambda p: (
                p["measurement"],
                p["time"],
                json.dumps(p["tags"], sort_keys=True),
            ),
        )

    return clean(first) == clean(second)


def text(value, field, limit=180):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ValueError(f"{field} must contain 1–{limit} characters")
    return value.strip()


def numeric(value, field, integer=False, maximum=2000):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number")
    try:
        value = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{field} must be a number")
    if (
        not math.isfinite(value)
        or not 0 <= value <= maximum
        or (integer and value != int(value))
    ):
        raise ValueError(
            f"{field} must be between 0 and {maximum}"
            + (" and an integer" if integer else "")
        )
    return int(value) if integer else value


def rows_to_points(measurement, rows):
    return [
        {
            "measurement": measurement,
            "time": r["time"],
            "tags": {k: r[k] for k in TAGS if r.get(k) is not None},
            "fields": {
                k: v
                for k, v in r.items()
                if k not in TAGS + ("time",) and v is not None
            },
        }
        for r in rows
    ]


def snapshot(query, identity):
    return [
        p
        for m in MEASUREMENTS
        for p in rows_to_points(
            m, query(f'SELECT * FROM "{m}" WHERE "ActivityID" = ' + quote(identity))
        )
    ]


def snapshot_rows(points):
    return [
        dict(p["fields"], **p["tags"], time=p["time"])
        for p in points
        if p["measurement"] == "StrengthSet"
    ]


def replace_workout(client, identity, points):
    for m in MEASUREMENTS:
        client.query(f'DELETE FROM "{m}" WHERE "ActivityID" = ' + quote(identity))
    if points:
        ordered = sorted(
            points, key=lambda p: p["measurement"] != "StrengthManualSession"
        )
        if not client.write_points(ordered):
            raise RuntimeError("Database did not accept workout changes")


def plan_workout(body, before, catalog, database, zone, request_id):
    existing = [
        p
        for p in before
        if p["measurement"] == "ActivitySummary"
        and p["fields"].get("activityType") == "strength_training"
    ]
    original = existing[0] if existing else None
    if before and not original:
        raise ValueError("Workout summary is unavailable")
    date_changed = False
    day_shift = timedelta(0)
    if original:
        stamp = original["time"]
        tags = dict(original["tags"])
        name = original["fields"]["activityName"]
        day = (
            datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(zone).date()
        )
        if body.get("revision") != revision(snapshot_rows(before)):
            raise Conflict("This workout changed. Reload it before saving.")
        if body.get("name") is not None:
            name = text(body["name"], "Workout name")
        original_day = day
        if body.get("date") is not None:
            try:
                day = date.fromisoformat(body["date"])
            except (ValueError, TypeError):
                raise ValueError("Enter a valid workout date")
            if day > datetime.now(zone).date():
                raise ValueError("Recorded workouts cannot be in the future")
            date_changed = day != original_day
            day_shift = day - original_day
            original_time = datetime.fromisoformat(
                stamp.replace("Z", "+00:00")
            ).astimezone(zone)
            stamp = (
                datetime.combine(day, original_time.timetz().replace(tzinfo=None), zone)
                .astimezone(timezone.utc)
                .isoformat()
            )
    else:
        try:
            day = date.fromisoformat(body.get("date", ""))
        except (TypeError, ValueError):
            raise ValueError("Enter a valid workout date")
        if day > datetime.now(zone).date():
            raise ValueError("Recorded workouts cannot be in the future")
        name = text(body.get("name"), "Workout name")
        stamp = (
            datetime.combine(day, time(12), zone).astimezone(timezone.utc).isoformat()
        )
        tags = {
            "ActivityID": "web-" + request_id,
            "Device": "Manual log",
            "Database_Name": database,
            "ActivitySelector": "web-" + request_id,
        }
    identity = tags["ActivityID"]
    common = {k: v for k, v in tags.items() if k != "ActivitySelector"}
    rows = body.get("sets")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 250:
        raise ValueError("A workout must have 1–250 sets")
    previous = {
        str(p["tags"]["ActivityID"]) + ":" + str(p["tags"]["SetIndex"]): p
        for p in before
        if p["measurement"] == "StrengthSet"
    }
    used = set()
    numbers = defaultdict(int)
    points = []
    numeric_id = (
        original["fields"].get("Activity_ID")
        if original
        else -int(uuid.UUID(request_id).hex[:12], 16)
    )
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError("Invalid set")
        key = row.get("id")
        old = previous.get(key) if key else None
        if key and (not old or key in used):
            raise ValueError("Invalid or repeated set identity")
        if key:
            used.add(key)
        exercise = text(row.get("exercise"), "Exercise name", 120)
        exercise = EXERCISE_NAME_ALIASES.get(exercise, exercise)
        match = next((n for n in catalog if n.casefold() == exercise.casefold()), None)
        if match:
            exercise = match
        category, code = catalog.get(exercise, ("MANUAL", exercise))
        weight = numeric(row.get("weight"), "Load (kg)")
        reps = numeric(row.get("reps"), "Repetitions", True, 500)
        if weight is None and reps is None and not old:
            raise ValueError("Each new set needs a load or rep count")
        note = row.get("note", "")
        if not isinstance(note, str) or len(note) > 1000:
            raise ValueError("Set notes must be at most 1,000 characters")
        fields = dict(old["fields"]) if old else {}
        changed = (
            not old
            or old["tags"]["Exercise"] != exercise
            or fields.get("weightKg") != weight
            or fields.get("reps") != reps
            or (fields.get("dataNote") or "") != note
        )
        for field in ("weightKg", "reps", "volumeKg", "estimated1RMKg", "dataNote"):
            fields.pop(field, None)
        if weight is not None:
            fields["weightKg"] = weight
        if reps is not None:
            fields["reps"] = reps
        if weight is not None and reps is not None:
            fields["volumeKg"] = float(weight * reps)
            if (
                weight > 0
                and 1 <= reps <= 10
                and category not in BODYWEIGHT_CATEGORIES
                and category != "MANUAL"
            ):
                fields["estimated1RMKg"] = float(
                    weight if reps == 1 else weight * (1 + reps / 30)
                )
        if note:
            fields["dataNote"] = note
        if changed:
            fields["source"] = "Manual Web"
            if old:
                fields.setdefault("originalExercise", old["tags"]["Exercise"])
        if not old:
            fields.update(sourceDate=day.isoformat(), timeAccuracy="date-only")
        elif date_changed:
            fields["sourceDate"] = day.isoformat()
        numbers[exercise] += 1
        fields.update(
            setCount=1,
            setNumber=numbers[exercise],
            setOrder=index + 1,
            workoutName=name,
            exerciseCode=code,
        )
        if numeric_id and numeric_id > 0:
            fields.update(
                activityId=int(numeric_id),
                activityUrl=f"https://connect.garmin.com/modern/activity/{numeric_id}",
            )
        point_tags = dict(
            common,
            Exercise=exercise,
            ExerciseCategory=category,
            SetIndex=old["tags"]["SetIndex"] if old else f"web-{request_id}-{index}",
        )
        set_stamp = old["time"] if old else stamp
        if old and date_changed:
            local = datetime.fromisoformat(
                old["time"].replace("Z", "+00:00")
            ).astimezone(zone)
            set_stamp = (local + day_shift).astimezone(timezone.utc).isoformat()
        points.append(
            {
                "measurement": "StrengthSet",
                "time": set_stamp,
                "tags": point_tags,
                "fields": fields,
            }
        )
    groups = defaultdict(list)
    for p in points:
        groups[(p["tags"]["Exercise"], p["tags"]["ExerciseCategory"])].append(
            p["fields"]
        )
    for (exercise, category), sets in groups.items():
        fields = {
            "sets": len(sets),
            "setsWithWeight": sum("weightKg" in s for s in sets),
            "setsWithReps": sum("reps" in s for s in sets),
            "workoutName": name,
            "workoutLabel": f"{day} · {name} | {identity}",
            "source": "Manual Web",
        }
        if numeric_id and numeric_id > 0:
            fields.update(
                activityId=int(numeric_id),
                activityUrl=f"https://connect.garmin.com/modern/activity/{numeric_id}",
            )
        for field, out, agg in [
            ("weightKg", "bestWeightKg", max),
            ("reps", "totalReps", sum),
            ("reps", "bestReps", max),
            ("volumeKg", "volumeKg", sum),
            ("estimated1RMKg", "estimated1RMKg", max),
            ("durationSeconds", "activeSeconds", sum),
            ("restAfterSeconds", "restSeconds", sum),
        ]:
            values = [s[field] for s in sets if s.get(field) is not None]
            if values:
                fields[out] = (
                    int(agg(values)) if field == "reps" else float(agg(values))
                )
        points.append(
            {
                "measurement": "StrengthExercise",
                "time": stamp,
                "tags": dict(common, Exercise=exercise, ExerciseCategory=category),
                "fields": fields,
            }
        )
    if original:
        for summary in before:
            if summary["measurement"] != "ActivitySummary":
                continue
            updated = dict(summary, fields=dict(summary["fields"], activityName=name))
            if date_changed:
                local = datetime.fromisoformat(
                    summary["time"].replace("Z", "+00:00")
                ).astimezone(zone)
                updated["time"] = (
                    (local + day_shift).astimezone(timezone.utc).isoformat()
                )
            if (
                "durationMinutes" in body
                and summary["fields"].get("activityType") == "strength_training"
            ):
                minutes = numeric(
                    body["durationMinutes"], "Duration (minutes)", False, 1440
                )
                updated["fields"].pop("elapsedDuration", None)
                if minutes is not None:
                    updated["fields"]["elapsedDuration"] = minutes * 60
            points.append(updated)
    else:
        fields = {
            "Activity_ID": numeric_id,
            "activityName": name,
            "activityType": "strength_training",
            "source": "Manual Web",
            "timeAccuracy": "date-only",
        }
        minutes = numeric(
            body.get("durationMinutes"), "Duration (minutes)", False, 1440
        )
        if minutes is not None:
            fields["elapsedDuration"] = minutes * 60
        points.append(
            {
                "measurement": "ActivitySummary",
                "time": stamp,
                "tags": tags,
                "fields": fields,
            }
        )
    old_marker = next(
        (p for p in before if p["measurement"] == "StrengthManualSession"), None
    )
    marker_fields = (
        dict(old_marker["fields"])
        if old_marker
        else {"sourceHash": "web-" + request_id, "sourceSession": identity}
    )
    marker_fields.update(importedSets=len(rows), source="Manual Web")
    points.append(
        {
            "measurement": "StrengthManualSession",
            "time": old_marker["time"] if old_marker else stamp,
            "tags": dict(old_marker["tags"]) if old_marker else common,
            "fields": marker_fields,
        }
    )
    return identity, points, name


class WebState:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()

    @contextmanager
    def mutation_lock(self):
        # All WebState workers share this SQLite-backed lock. Keep it on a
        # separate connection/file so committing the durable edit journal does
        # not release the lock during the subsequent Influx replacement.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = sqlite3.connect(str(self.path) + ".write-lock", timeout=30)
        try:
            lock.execute(
                "CREATE TABLE IF NOT EXISTS writer_lock (id INTEGER PRIMARY KEY)"
            )
            lock.execute("BEGIN IMMEDIATE")
            yield
        finally:
            lock.rollback()
            lock.close()

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        c.executescript(
            "CREATE TABLE IF NOT EXISTS goals(id TEXT PRIMARY KEY,data TEXT NOT NULL,archived INTEGER DEFAULT 0); CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY,kind TEXT,request TEXT,before_data TEXT,after_data TEXT,response TEXT,status TEXT,created TEXT); CREATE TABLE IF NOT EXISTS food_log(id TEXT PRIMARY KEY,data TEXT NOT NULL,created TEXT NOT NULL);"
        )
        try:
            with c:
                yield c
        finally:
            c.close()

    def read(self):
        with self.lock, self.connect() as c:
            goals = [
                dict(json.loads(r["data"]), id=r["id"])
                for r in c.execute(
                    "SELECT * FROM goals WHERE archived=0 ORDER BY rowid DESC"
                )
            ]
            archived = [
                dict(json.loads(r["data"]), id=r["id"])
                for r in c.execute(
                    "SELECT * FROM goals WHERE archived=1 ORDER BY rowid DESC"
                )
            ]
            settings = {
                r["key"]: json.loads(r["value"])
                for r in c.execute("SELECT * FROM settings")
            }
            edits = []
            for r in c.execute(
                "SELECT * FROM audit WHERE kind IN ('workout_save','workout_delete') AND status IN ('done','undone') ORDER BY rowid DESC LIMIT 10"
            ):
                result = json.loads(r["response"])
                edits.append(
                    {
                        "id": r["id"],
                        "created": r["created"],
                        "sessionId": result["sessionId"],
                        "name": result["name"],
                        "undone": r["status"] == "undone",
                    }
                )
            metadata = {
                "goals": [
                    dict(r) for r in c.execute("SELECT * FROM goals ORDER BY id")
                ],
                "settings": [
                    dict(r) for r in c.execute("SELECT * FROM settings ORDER BY key")
                ],
            }
            return {
                "metadataRevision": hashlib.sha256(
                    json.dumps(metadata, sort_keys=True).encode()
                ).hexdigest(),
                "goals": goals,
                "archivedGoals": archived,
                "muscleOverrides": settings.get("muscles", {}),
                "volumeSettings": settings.get(
                    "volume", {"bodyWeightKg": None, "exercises": {}}
                ),
                "equipment": settings.get(
                    "equipment", {"profiles": {}, "assignments": {}}
                ),
                "progressionRules": settings.get("progression", {}),
                "edits": edits,
                "recoveryOverrides": settings.get("recovery", {}),
            }

    def export_records(self):
        with self.lock, self.connect() as c:
            return {
                "AppGoals": [
                    dict(r) for r in c.execute("SELECT * FROM goals ORDER BY id")
                ],
                "AppSettings": [
                    dict(r) for r in c.execute("SELECT * FROM settings ORDER BY key")
                ],
                "AppAudit": [
                    dict(r) for r in c.execute("SELECT * FROM audit ORDER BY created")
                ],
                "FoodLog": [
                    json.loads(r["data"])
                    for r in c.execute("SELECT * FROM food_log ORDER BY created")
                ],
            }

    def food_entries(self):
        with self.lock, self.connect() as c:
            return [
                json.loads(r["data"])
                for r in c.execute("SELECT data FROM food_log ORDER BY created DESC")
            ]

    def food_action(self, body):
        if not isinstance(body, dict):
            raise ValueError("Expected an object")
        try:
            identity = str(uuid.UUID(body.get("id", "")))
        except (ValueError, TypeError, AttributeError):
            raise ValueError("A valid food entry identity is required")
        action = body.get("action")
        with self.lock, self.mutation_lock(), self.connect() as c:
            if action == "delete":
                c.execute("DELETE FROM food_log WHERE id=?", (identity,))
                return {"ok": True, "id": identity}
            if action != "add":
                raise ValueError("Invalid food action")
            existing = c.execute(
                "SELECT data FROM food_log WHERE id=?", (identity,)
            ).fetchone()
            if existing:
                return {"ok": True, "entry": json.loads(existing["data"])}
            name = text(body.get("name"), "Food name", 120)
            description = body.get("description", "")
            note = body.get("note", "")
            if (
                not isinstance(description, str)
                or len(description) > 2000
                or not isinstance(note, str)
                or len(note) > 300
            ):
                raise ValueError("Food description or note is too long")
            try:
                stamp = datetime.fromisoformat(
                    body.get("time", "").replace("Z", "+00:00")
                )
            except (TypeError, ValueError, AttributeError):
                raise ValueError("Invalid food time")
            if stamp.tzinfo is None:
                raise ValueError("Food time must include a timezone")
            stamp = stamp.astimezone(timezone.utc)
            if stamp > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise ValueError("Food time cannot be in the future")
            values = {}
            for key, maximum in [
                ("calories", 5000),
                ("protein_g", 1000),
                ("carbs_g", 1000),
                ("fat_g", 1000),
            ]:
                value = numeric(body.get(key), key, maximum=maximum)
                if value is None:
                    raise ValueError(f"{key} is required")
                values[key] = value
            items = body.get("items", [])
            if not isinstance(items, list) or len(items) > 20:
                raise ValueError("Invalid food items")
            checked = []
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("Invalid food item")
                checked.append(
                    {
                        "name": text(item.get("name"), "Food item", 100),
                        "portion": text(item.get("portion"), "Food portion", 100),
                    }
                )
            entry = {
                "id": identity,
                "time": stamp.isoformat(),
                "name": name,
                "description": description,
                "items": checked,
                **values,
                "note": note,
                "source": "telegram-estimate",
            }
            c.execute(
                "INSERT INTO food_log VALUES(?,?,?)",
                (identity, json.dumps(entry, ensure_ascii=False), stamp.isoformat()),
            )
            return {"ok": True, "entry": entry}

    def apply(self, body, factory, database, zone):
        if not isinstance(body, dict):
            raise ValueError("Expected an object")
        try:
            request_id = str(uuid.UUID(body.get("requestId", "")))
        except (ValueError, TypeError, AttributeError):
            raise ValueError("A valid request identity is required")
        kind = body.get("action")
        request = json.dumps(body, sort_keys=True, allow_nan=False)
        with self.lock, self.mutation_lock(), self.connect() as c:
            old = c.execute("SELECT * FROM audit WHERE id=?", (request_id,)).fetchone()
            if old:
                if old["request"] != request:
                    raise Conflict(
                        "This request identity was used for different changes"
                    )
                if old["status"] == "done":
                    return json.loads(old["response"])
                if old["status"] == "pending" and kind in (
                    "workout_save",
                    "workout_delete",
                    "undo_workout",
                ):
                    response = json.loads(old["response"])
                    client, query = factory()
                    try:
                        actual = snapshot(query, response["sessionId"])
                    finally:
                        client.close()
                    if snapshots_equal(actual, json.loads(old["after_data"])):
                        c.execute(
                            "UPDATE audit SET status='done',after_data=? WHERE id=?",
                            (json.dumps(actual), request_id),
                        )
                        if kind == "undo_workout":
                            c.execute(
                                "UPDATE audit SET status='undone' WHERE id=?",
                                (body["id"],),
                            )
                        return response
                    if snapshots_equal(actual, json.loads(old["before_data"])):
                        # No replacement survived (or rollback restored it). The exact
                        # same request can safely run again under the writer lock.
                        c.execute("DELETE FROM audit WHERE id=?", (request_id,))
                    else:
                        raise Conflict(
                            "Interrupted save has different database contents. Originals are archived; reload and review before editing."
                        )
                else:
                    raise Conflict("This request was undone. Reload before retrying.")
            if (
                kind in ("muscle_save", "progression_save")
                and "metadataRevision" in body
                and body["metadataRevision"] != self.read()["metadataRevision"]
            ):
                raise Conflict(
                    "Settings changed. Refresh before saving these settings."
                )
            before = []
            after = []
            response = {"ok": True}
            if kind == "goal_save":
                goal = body.get("goal", {})
                if not isinstance(goal, dict):
                    raise ValueError("Invalid goal")
                name = text(goal.get("exercise"), "Exercise", 120)
                name = EXERCISE_NAME_ALIASES.get(name, name)
                reps = numeric(goal.get("reps"), "Target reps", True, 500)
                if reps is None or reps < 1:
                    raise ValueError("Target reps must be at least 1")
                mode = goal.get("mode", "load_reps")
                if mode not in ("load_reps", "reps"):
                    raise ValueError("Invalid goal mode")
                weight = (
                    numeric(goal.get("weight"), "Target load")
                    if mode == "load_reps"
                    else None
                )
                if mode == "load_reps" and weight is None:
                    raise ValueError("Enter a target load")
                deadline = goal.get("deadline") or ""
                if deadline:
                    try:
                        date.fromisoformat(deadline)
                    except ValueError:
                        raise ValueError("Invalid deadline")
                identity = str(uuid.UUID(goal["id"])) if goal.get("id") else request_id
                data = {
                    "exercise": name,
                    "reps": reps,
                    "weight": weight,
                    "mode": mode,
                    "deadline": deadline,
                }
                c.execute(
                    "INSERT INTO goals(id,data,archived) VALUES(?,?,0) ON CONFLICT(id) DO UPDATE SET data=excluded.data,archived=0",
                    (identity, json.dumps(data)),
                )
            elif kind == "goal_archive":
                if not c.execute(
                    "UPDATE goals SET archived=1 WHERE id=?", (body.get("id"),)
                ).rowcount:
                    raise ValueError("Goal not found")
            elif kind == "equipment_save":
                if body.get("metadataRevision") != self.read()["metadataRevision"]:
                    raise Conflict("Settings changed. Refresh before saving equipment.")
                equipment = validate_equipment(body.get("equipment"))
                c.execute(
                    "INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ("equipment", json.dumps(equipment)),
                )
            elif kind == "volume_save":
                if body.get("metadataRevision") != self.read()["metadataRevision"]:
                    raise Conflict(
                        "Settings changed. Refresh before saving volume factors."
                    )
                settings = body.get("settings")
                if not isinstance(settings, dict):
                    raise ValueError("Invalid volume settings")
                weight = numeric(
                    settings.get("bodyWeightKg"), "Fallback body weight", False, 500
                )
                if weight is not None and weight <= 0:
                    raise ValueError("Body weight must be greater than zero")
                mappings = settings.get("exercises")
                if not isinstance(mappings, dict) or len(mappings) > 1000:
                    raise ValueError("Invalid exercise volume factors")
                checked = {}
                for name, rule in mappings.items():
                    name = text(name, "Exercise", 120)
                    if not isinstance(rule, dict):
                        raise ValueError("Invalid exercise volume factor")
                    multiplier = numeric(
                        rule.get("multiplier"), "Volume multiplier", False, 10
                    )
                    fraction = numeric(
                        rule.get("bodyweight"), "Bodyweight fraction", False, 1
                    )
                    if multiplier is None or multiplier <= 0 or fraction is None:
                        raise ValueError(
                            "Enter a positive multiplier and a bodyweight fraction from 0 to 1"
                        )
                    assistance = rule.get("assistance", False)
                    if not isinstance(assistance, bool):
                        raise ValueError("Invalid assistance flag")
                    checked[name] = {
                        "multiplier": multiplier,
                        "bodyweight": fraction,
                        "assistance": assistance,
                    }
                    if "reviewed" in rule:
                        if not isinstance(rule["reviewed"], bool):
                            raise ValueError("Invalid volume review flag")
                        checked[name]["reviewed"] = rule["reviewed"]
                    if "loadCopies" in rule:
                        copies = numeric(rule["loadCopies"], "Load copies", True, 2)
                        if copies not in (1, 2):
                            raise ValueError("Load copies must be 1 or 2")
                        checked[name]["loadCopies"] = copies
                c.execute(
                    "INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (
                        "volume",
                        json.dumps({"bodyWeightKg": weight, "exercises": checked}),
                    ),
                )
            elif kind == "muscle_save":
                mappings = body.get("mappings")
                if not isinstance(mappings, dict) or len(mappings) > 1000:
                    raise ValueError("Invalid muscle mappings")
                for name in mappings:
                    text(name, "Exercise", 120)
                if any(group not in GROUPS for group in mappings.values()):
                    raise ValueError("Invalid muscle group")
                c.execute(
                    "INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ("muscles", json.dumps(mappings)),
                )
            elif kind in ("progression_save", "progression_set"):
                mappings = (
                    {body.get("exercise"): body.get("rule")}
                    if kind == "progression_set"
                    else body.get("mappings")
                )
                if not isinstance(mappings, dict) or len(mappings) > 1000:
                    raise ValueError("Invalid progression rules")
                checked = {}
                for name, rule in mappings.items():
                    name = text(name, "Exercise", 120)
                    if not isinstance(rule, dict):
                        raise ValueError("Invalid progression rule")
                    low = numeric(rule.get("repMin"), "Minimum reps", True, 30)
                    high = numeric(rule.get("repMax"), "Maximum reps", True, 30)
                    step = numeric(
                        rule.get("weightStep"), "Weight increment", False, 50
                    )
                    if low is None or high is None or not 1 <= low < high:
                        raise ValueError(
                            "Rep range must have a minimum below its maximum (1–30)"
                        )
                    if step is not None and step < 0.25:
                        raise ValueError("Weight increment must be at least 0.25 kg")
                    checked[name] = {"repMin": low, "repMax": high, "weightStep": step}
                if kind == "progression_set":
                    existing = c.execute(
                        "SELECT value FROM settings WHERE key='progression'"
                    ).fetchone()
                    merged = json.loads(existing["value"]) if existing else {}
                    merged.update(checked)
                    checked = merged
                c.execute(
                    "INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ("progression", json.dumps(checked)),
                )
            elif kind == "metadata_change":
                # Snapshot all app metadata for reversible, revision-checked small edits.
                before_meta = {
                    "goals": [
                        dict(r) for r in c.execute("SELECT * FROM goals ORDER BY id")
                    ],
                    "settings": [
                        dict(r)
                        for r in c.execute("SELECT * FROM settings ORDER BY key")
                    ],
                }
                token = hashlib.sha256(
                    json.dumps(before_meta, sort_keys=True).encode()
                ).hexdigest()
                if body.get("metadataRevision") != token:
                    raise Conflict("Settings changed. Request a fresh preview.")
                entity = body.get("entity")
                operation = body.get("operation")
                key = body.get("key")
                value = body.get("value")
                if operation not in ("save", "delete"):
                    raise ValueError("Invalid operation")
                if entity == "goal":
                    if operation == "delete":
                        if not c.execute(
                            "DELETE FROM goals WHERE id=?", (key,)
                        ).rowcount:
                            raise ValueError("Goal not found")
                    else:
                        # Reuse goal validation without creating a second audit transaction.
                        if not isinstance(value, dict):
                            raise ValueError("Invalid goal")
                        name = text(value.get("exercise"), "Exercise", 120)
                        name = EXERCISE_NAME_ALIASES.get(name, name)
                        reps = numeric(value.get("reps"), "Target reps", True, 500)
                        mode = value.get("mode", "load_reps")
                        if (
                            reps is None
                            or reps < 1
                            or mode not in ("load_reps", "reps")
                        ):
                            raise ValueError("Invalid goal reps or mode")
                        weight = (
                            numeric(value.get("weight"), "Target load")
                            if mode == "load_reps"
                            else None
                        )
                        if mode == "load_reps" and weight is None:
                            raise ValueError("Enter a target load")
                        deadline = value.get("deadline") or ""
                        if deadline:
                            date.fromisoformat(deadline)
                        identity = str(uuid.UUID(key)) if key else request_id
                        data = dict(
                            exercise=name,
                            reps=reps,
                            mode=mode,
                            weight=weight,
                            deadline=deadline,
                        )
                        c.execute(
                            "INSERT INTO goals VALUES(?,?,0) ON CONFLICT(id) DO UPDATE SET data=excluded.data,archived=0",
                            (identity, json.dumps(data)),
                        )
                elif entity in ("muscle", "progression", "recovery"):
                    setting = {
                        "muscle": "muscles",
                        "progression": "progression",
                        "recovery": "recovery",
                    }[entity]
                    old_setting = c.execute(
                        "SELECT value FROM settings WHERE key=?", (setting,)
                    ).fetchone()
                    mapping = json.loads(old_setting["value"]) if old_setting else {}
                    key = text(key, "Record key", 120)
                    if entity == "recovery":
                        date.fromisoformat(key)
                    if operation == "delete":
                        if key not in mapping:
                            raise ValueError("Saved override not found")
                        del mapping[key]
                    else:
                        if entity == "muscle":
                            if value not in GROUPS:
                                raise ValueError("Invalid muscle group")
                        elif entity == "progression":
                            if not isinstance(value, dict):
                                raise ValueError("Invalid progression rule")
                            low = numeric(value.get("repMin"), "Minimum reps", True, 30)
                            high = numeric(
                                value.get("repMax"), "Maximum reps", True, 30
                            )
                            step = numeric(
                                value.get("weightStep"), "Weight step", False, 50
                            )
                            if (
                                low is None
                                or high is None
                                or not 1 <= low < high
                                or (step is not None and step < 0.25)
                            ):
                                raise ValueError("Invalid progression range or step")
                            value = dict(repMin=low, repMax=high, weightStep=step)
                        else:
                            limits = {
                                "bodyWeightKg": 500,
                                "sleepHours": 24,
                                "hrv": 500,
                                "restingHR": 250,
                                "sleepScore": 100,
                                "bodyBattery": 100,
                                "deepSeconds": 86400,
                                "lightSeconds": 86400,
                                "remSeconds": 86400,
                                "awakeSeconds": 86400,
                            }
                            if (
                                not isinstance(value, dict)
                                or not value
                                or any(k not in limits for k in value)
                            ):
                                raise ValueError("Invalid recovery fields")
                            value = {
                                k: numeric(v, k, maximum=limits[k])
                                for k, v in value.items()
                            }
                            if (
                                value.get("bodyWeightKg") is not None
                                and value["bodyWeightKg"] <= 0
                            ):
                                raise ValueError(
                                    "Body weight must be greater than zero"
                                )
                            value = dict(mapping.get(key, {}), **value)
                        mapping[key] = value
                    c.execute(
                        "INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (setting, json.dumps(mapping)),
                    )
                else:
                    raise ValueError("Invalid record type")
                after_meta = {
                    "goals": [
                        dict(r) for r in c.execute("SELECT * FROM goals ORDER BY id")
                    ],
                    "settings": [
                        dict(r)
                        for r in c.execute("SELECT * FROM settings ORDER BY key")
                    ],
                }
                c.execute(
                    "INSERT INTO audit VALUES(?,?,?,?,?,?,?,?)",
                    (
                        request_id,
                        kind,
                        request,
                        json.dumps(before_meta),
                        json.dumps(after_meta),
                        json.dumps(response),
                        "done",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                return response
            elif kind == "undo_metadata":
                prior = c.execute(
                    "SELECT * FROM audit WHERE id=? AND kind='metadata_change' AND status='done'",
                    (body.get("id"),),
                ).fetchone()
                if not prior:
                    raise ValueError("This change is not available to undo")
                current = {
                    "goals": [
                        dict(r) for r in c.execute("SELECT * FROM goals ORDER BY id")
                    ],
                    "settings": [
                        dict(r)
                        for r in c.execute("SELECT * FROM settings ORDER BY key")
                    ],
                }
                if current != json.loads(prior["after_data"]):
                    raise Conflict("Newer settings changes exist. Undo those first.")
                previous = json.loads(prior["before_data"])
                c.execute("DELETE FROM goals")
                c.execute("DELETE FROM settings")
                c.executemany(
                    "INSERT INTO goals VALUES(:id,:data,:archived)", previous["goals"]
                )
                c.executemany(
                    "INSERT INTO settings VALUES(:key,:value)", previous["settings"]
                )
                c.execute("UPDATE audit SET status='undone' WHERE id=?", (body["id"],))
            elif kind in ("workout_save", "workout_delete", "undo_workout"):
                client, query = factory()
                try:
                    if kind == "undo_workout":
                        prior = c.execute(
                            "SELECT * FROM audit WHERE id=? AND kind IN ('workout_save','workout_delete') AND status='done'",
                            (body.get("id"),),
                        ).fetchone()
                        if not prior:
                            raise ValueError("This edit is not available to undo")
                        previous = json.loads(prior["response"])
                        identity = previous["sessionId"]
                        before = snapshot(query, identity)
                        after = json.loads(prior["before_data"])
                        if snapshot_revision(before) != snapshot_revision(
                            json.loads(prior["after_data"])
                        ):
                            raise Conflict(
                                "Newer changes exist. Undo the newer edit first."
                            )
                        name = previous["name"]
                    else:
                        identity = body.get("sessionId") or "web-" + request_id
                        before = snapshot(query, identity)
                        if body.get("sessionId") and not before:
                            raise ValueError("Workout not found")
                        expected = body.get("expectedMetadata")
                        if expected is not None:
                            summary = next(
                                (
                                    p
                                    for p in before
                                    if p["measurement"] == "ActivitySummary"
                                    and p["fields"].get("activityType")
                                    == "strength_training"
                                ),
                                None,
                            )
                            actual_metadata = (
                                {
                                    "name": summary["fields"].get("activityName"),
                                    "date": datetime.fromisoformat(
                                        summary["time"].replace("Z", "+00:00")
                                    )
                                    .astimezone(zone)
                                    .date()
                                    .isoformat(),
                                    "duration": summary["fields"].get(
                                        "elapsedDuration"
                                    ),
                                }
                                if summary
                                else None
                            )
                            if actual_metadata != expected:
                                raise Conflict(
                                    "Workout details changed. Request a fresh preview."
                                )
                        raw = query(
                            'SELECT "Exercise",  "ExerciseCategory", LAST("exerciseCode") FROM "StrengthSet" GROUP BY "Exercise", "ExerciseCategory"'
                        )
                        catalog = {
                            r["Exercise"]: (r["ExerciseCategory"], r["last"])
                            for r in raw
                        }
                        if kind == "workout_delete":
                            original = next(
                                (
                                    p
                                    for p in before
                                    if p["measurement"] == "ActivitySummary"
                                    and p["fields"].get("activityType")
                                    == "strength_training"
                                ),
                                None,
                            )
                            if not original:
                                raise ValueError("Strength workout not found")
                            if body.get("revision") != revision(snapshot_rows(before)):
                                raise Conflict(
                                    "This workout changed. Request a fresh preview."
                                )
                            name = original["fields"]["activityName"]
                            # Keep a tombstone so Garmin sync cannot resurrect a deleted session.
                            after = [
                                {
                                    "measurement": "StrengthManualSession",
                                    "time": original["time"],
                                    "tags": {
                                        k: v
                                        for k, v in original["tags"].items()
                                        if k != "ActivitySelector"
                                    },
                                    "fields": {
                                        "importedSets": 0,
                                        "source": "Manual Web",
                                        "deleted": True,
                                    },
                                }
                            ]
                        else:
                            identity, after, name = plan_workout(
                                body, before, catalog, database, zone, request_id
                            )
                    response.update(sessionId=identity, name=name)
                    # A durable journal and Influx archives precede every replacement.
                    c.execute(
                        "INSERT INTO audit VALUES(?,?,?,?,?,?,?,?)",
                        (
                            request_id,
                            kind,
                            request,
                            json.dumps(before),
                            json.dumps(after),
                            json.dumps(response),
                            "pending",
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                    c.commit()
                    archives = [
                        dict(
                            p,
                            measurement=p["measurement"] + "WebArchive",
                            tags=dict(p["tags"], EditID=request_id),
                        )
                        for p in before
                    ]
                    if archives and not client.write_points(archives):
                        raise RuntimeError("Could not archive originals")
                    try:
                        replace_workout(client, identity, after)
                        actual = snapshot(query, identity)
                        if not snapshots_equal(actual, after):
                            raise RuntimeError(
                                "Saved workout did not match the requested changes"
                            )
                    except Exception:
                        replace_workout(client, identity, before)
                        raise
                    c.execute(
                        "UPDATE audit SET status='done',after_data=? WHERE id=?",
                        (json.dumps(actual), request_id),
                    )
                    if kind == "undo_workout":
                        c.execute(
                            "UPDATE audit SET status='undone' WHERE id=?", (body["id"],)
                        )
                    c.commit()
                    return response
                finally:
                    client.close()
            else:
                raise ValueError("Unknown action")
            c.execute(
                "INSERT INTO audit VALUES(?,?,?,?,?,?,?,?)",
                (
                    request_id,
                    kind,
                    request,
                    "[]",
                    "[]",
                    json.dumps(response),
                    "done",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            return response
