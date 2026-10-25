"""Owner-confirmed training edits. Models can draft; only Telegram buttons commit."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
import uuid

from reptrace.storage.state import numeric, text, GROUPS


def set_record(row):
    return {k: row.get(k) for k in ("id", "exercise", "weight", "reps", "note")}


def stage(tools, body, lines):
    identity = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL, tools.request_id + json.dumps(body, sort_keys=True)
        )
    )
    body = dict(body, requestId=identity)
    pending = tools.state.setdefault("pendingEdits", {})
    if identity not in pending:
        if len(pending) >= 30:
            for key in list(pending)[:-20]:
                if pending[key].get("status") != "saving":
                    pending.pop(key)
        pending[identity] = {
            "body": body,
            "preview": "\n".join(lines),
            "status": "pending",
            "turn": tools.request_id,
            "expires": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        }
        tools.save()
    draft = pending[identity]
    status = draft["status"]
    return {
        "saved": status == "saved",
        "status": status,
        "draftId": identity,
        "preview": draft["preview"],
        "next": (
            "Owner must press Save in the Telegram preview. Nothing has changed yet."
            if status == "pending"
            else "This request already has status "
            + status
            + ". Read its current result before proposing further changes."
        ),
    }


def draft_workout(tools, a):
    identity = a.get("session_id")
    operation = a["operation"]
    workout = (
        next((w for w in tools.data["workouts"] if w["id"] == identity), None)
        if identity
        else None
    )
    if identity and not workout:
        raise ValueError("Workout not found; read workout history first")
    if operation not in ("save", "delete"):
        raise ValueError("Invalid operation")
    if operation == "delete":
        if not workout:
            raise ValueError("Deleting requires an existing workout reference")
        return stage(
            tools,
            {
                "action": "workout_delete",
                "sessionId": identity,
                "revision": workout["revision"],
                "expectedMetadata": {
                    k: workout.get(k) for k in ("name", "date", "duration")
                },
            },
            [
                f"DELETE SESSION: {workout['date']} · {workout['name']}",
                f"Remove all {sum(r['sessionId'] == identity for r in tools.data['sets'])} sets. Undo available after saving.",
            ],
        )
    # Preserve every row, including Unknown, unless explicitly targeted by its ID.
    rows = (
        [
            set_record(r)
            for r in sorted(tools.data["sets"], key=lambda r: r.get("order") or 0)
            if r["sessionId"] == identity
        ]
        if workout
        else []
    )
    body = {"action": "workout_save", "sets": rows}
    lines = []
    if workout:
        body.update(
            sessionId=identity,
            revision=workout["revision"],
            expectedMetadata={k: workout.get(k) for k in ("name", "date", "duration")},
        )
        lines.append(f"EDIT SESSION: {workout['date']} · {workout['name']}")
    else:
        if not a.get("date") or not a.get("name"):
            raise ValueError("A new workout needs an explicit date and name")
        lines.append("ADD SESSION")
    for key in ("date", "name", "duration_minutes"):
        value = a.get(key)
        if value is None:
            continue
        target = "durationMinutes" if key == "duration_minutes" else key
        if key == "date":
            if date.fromisoformat(value) > tools.today:
                raise ValueError("Recorded workouts cannot be in the future")
        elif key == "name":
            value = text(value, "Workout name")
        else:
            value = numeric(value, "Duration", maximum=1440)
        body[target] = value
        lines.append(
            f"{key}: {workout.get('duration', 0) / 60 if workout and key == 'duration_minutes' and workout.get('duration') is not None else workout.get(key) if workout else 'new'} → {value}"
        )
    touched = set()
    for change in a.get("set_changes", []):
        op = change["operation"]
        key = change.get("set_id")
        old = next((r for r in rows if r.get("id") == key), None) if key else None
        if op not in ("add", "update", "delete"):
            raise ValueError("Invalid set operation")
        if op != "add" and (not old or key in touched):
            raise ValueError(
                "Set not found or targeted twice; get editable workout first"
            )
        if op == "add" and key:
            raise ValueError("New sets cannot have an existing ID")
        if key:
            touched.add(key)
        if op == "delete":
            rows.remove(old)
            lines.append(
                f"DELETE {old['exercise']} [{key}]: {old['weight']} kg × {old['reps']}"
            )
            continue
        new = dict(old) if old else {}
        exercise = change.get("exercise")
        if exercise is not None:
            new["exercise"] = text(exercise, "Exercise", 120)
        if not new.get("exercise"):
            raise ValueError("New sets need an exercise name")
        # For update, null preserves the value; clear_fields explicitly removes missing measurements.
        for field in ("weight", "reps", "note"):
            if change.get(field) is not None:
                value = change[field]
                if field == "note":
                    if not isinstance(value, str) or len(value) > 1000:
                        raise ValueError("Invalid note")
                else:
                    value = numeric(
                        value,
                        field,
                        integer=field == "reps",
                        maximum=500 if field == "reps" else 2000,
                    )
                new[field] = value
        for field in change.get("clear_fields", []):
            if field not in ("weight", "reps", "note"):
                raise ValueError("Invalid field to clear")
            new[field] = "" if field == "note" else None
        new.setdefault("weight", None)
        new.setdefault("reps", None)
        new.setdefault("note", "")
        if old:
            lines.append(
                f"UPDATE {old['exercise']} [{key}]: "
                + json.dumps(old, ensure_ascii=False)
                + " → "
                + json.dumps(new, ensure_ascii=False)
            )
            rows[rows.index(old)] = new
        else:
            if new["weight"] is None and new["reps"] is None:
                raise ValueError("New set needs reps or load")
            rows.append(new)
            lines.append("ADD " + json.dumps(new, ensure_ascii=False))
    if not 1 <= len(rows) <= 250:
        raise ValueError(
            "Keep at least one set, or explicitly delete the whole session"
        )
    if workout and not a.get("set_changes") and len(lines) == 1:
        raise ValueError("No changes requested")
    lines.append(
        f"{len(rows)} total sets after saving. Other sets retained. Undo available."
    )
    return stage(tools, body, lines)


def draft_record(tools, a):
    entity = a["entity"]
    operation = a["operation"]
    key = a.get("key")
    value = a.get("value_json")
    if entity not in ("goal", "muscle", "progression", "recovery") or operation not in (
        "save",
        "delete",
        "archive",
        "restore",
    ):
        raise ValueError("Invalid record type or operation")
    if operation in ("archive", "restore") and entity != "goal":
        raise ValueError("Archive and restore apply only to goals")
    if operation == "save":
        if not isinstance(value, str) or len(value) > 6000:
            raise ValueError("Provide a JSON value (up to 6000 characters)")
        try:
            value = json.loads(
                value,
                parse_constant=lambda _: (_ for _ in ()).throw(
                    ValueError("Invalid numeric constant")
                ),
            )
        except ValueError:
            raise ValueError("Invalid JSON value")
    else:
        value = None
    if entity == "goal":
        before = next(
            (
                g
                for g in tools.data.get("goals", [])
                + tools.data.get("archivedGoals", [])
                if g["id"] == key
            ),
            None,
        )
    else:
        before = tools.data.get(
            {
                "muscle": "muscleOverrides",
                "progression": "progressionRules",
                "recovery": "recoveryOverrides",
            }[entity],
            {},
        ).get(key)
    if operation in ("delete", "archive", "restore") and before is None:
        raise ValueError(
            "Saved record not found; recovery delete removes a manual override, restoring Garmin values"
        )
    if entity == "goal" and key and before is None:
        raise ValueError("Goal not found")
    if entity == "recovery":
        date.fromisoformat(key)
    if entity == "muscle" and operation == "save" and value not in GROUPS:
        raise ValueError("Invalid muscle group")
    if entity != "muscle" and operation == "save" and not isinstance(value, dict):
        raise ValueError("Record must be a JSON object")
    body = {
        "action": "metadata_change",
        "metadataRevision": tools.data.get("metadataRevision"),
        "entity": entity,
        "operation": operation,
        "key": key,
        "value": value,
    }
    if not body["metadataRevision"]:
        raise ValueError("Refresh training data before editing settings")
    lines = [
        f"{operation.upper()} {entity}: {key or 'new'}",
        "Before: " + json.dumps(before, ensure_ascii=False),
        "After: " + json.dumps(value, ensure_ascii=False),
    ]
    if entity == "recovery":
        current = next(
            (r for r in tools.data.get("recovery", []) if r["date"] == key), None
        )
        lines.insert(
            1, "Current displayed data: " + json.dumps(current, ensure_ascii=False)
        )
        lines.append(
            "Manual override; original Garmin data preserved. Delete override to restore Garmin values."
        )
    lines.append("Undo available after saving.")
    return stage(tools, body, lines)
