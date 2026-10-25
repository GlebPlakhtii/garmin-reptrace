"""Local operation status and recovery using the owner's original confirmation."""

from contextlib import closing
from datetime import datetime, timezone
import json
import sqlite3
import uuid

from reptrace.storage.coordination import strength_lock
from reptrace.storage.state import Conflict


def operation_identity(value):
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("A valid operation identity is required") from None


def resumable(operation):
    if operation.get("status") in ("preview", "done", "cancelled"):
        return False
    if operation.get("kind") == "correction":
        return operation.get("destination") in ("both", "local")
    if operation.get("kind") == "creation":
        selection = operation.get("selection")
        items = operation.get("items", [])
        return bool(selection) and isinstance(selection, list) and all(
            type(i) is int and 0 <= i < len(items) for i in selection
        )
    return False


def operation_summary(operation, updated=None):
    result = {
        key: operation.get(key)
        for key in ("id", "kind", "activityId", "status", "remoteStatus", "localStatus", "destination")
    }
    result["preview"] = str(operation.get("preview", ""))[:30000]
    result["canResume"] = resumable(operation)
    result["updatedAt"] = (
        datetime.fromtimestamp(updated, timezone.utc).isoformat() if updated else None
    )
    errors = {"remote_revision_conflict", "remote_readback_failed", "revision_conflict", "save_failed"}
    result["localError"] = (
        operation.get("localError")
        if operation.get("status") not in ("done", "cancelled") and operation.get("localError") in errors
        else None
    )
    if operation.get("kind") == "creation":
        selection = operation.get("selection", [])
        result["deviceName"] = operation.get("device", {}).get("name", "Selected device")
        result["items"] = [
            {
                "name": item.get("payload", {}).get("workoutName", "Workout"),
                "selected": index in selection,
                "creation": item.get("creation", "not_started"),
                "delivery": item.get("delivery", "not_started"),
            }
            for index, item in enumerate(operation.get("items", []))
        ]
    return result


def read_operations(journal, identity=None):
    """Read without opening Garmin, creating a journal, or exposing raw responses."""
    if identity is not None:
        identity = operation_identity(identity)
    if not journal.path.exists():
        if identity:
            raise ValueError("Operation not found")
        return {"operations": []}
    with closing(sqlite3.connect(journal.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
        if identity:
            rows = db.execute(
                "SELECT data,updated FROM integration_operations WHERE id=?", (identity,)
            ).fetchall()
            if not rows:
                raise ValueError("Operation not found")
            return operation_summary(json.loads(rows[0][0]), rows[0][1])
        rows = db.execute(
            "SELECT data,updated FROM integration_operations ORDER BY "
            "CASE WHEN status NOT IN ('preview','done','cancelled') THEN 0 ELSE 1 END, updated DESC LIMIT 100"
        ).fetchall()
        return {"operations": [operation_summary(json.loads(data), updated) for data, updated in rows]}


def resume_operation(service, body):
    """Only continue a durable confirmation; never accept a new destination/selection."""
    identity = operation_identity(body.get("requestId"))
    if "destination" in body or "selection" in body:
        raise ValueError("Recovery uses the original confirmed destination and selection")
    with strength_lock():
        operation = service.journal.get(identity)
        if operation["status"] == "done":
            return operation_summary(operation)
        if not resumable(operation):
            raise Conflict("Only an already confirmed, unfinished operation can be continued")
        if operation["kind"] == "correction":
            result = service.apply(identity, operation["destination"])
        else:
            from reptrace.garmin.creation import Creation

            result = Creation(service.journal, service.adapter).apply(operation, operation["selection"])
        return operation_summary(result)
