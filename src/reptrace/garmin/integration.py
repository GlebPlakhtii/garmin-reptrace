"""Reviewed Garmin operations. Only the HTTP confirmation path may apply them."""

from copy import deepcopy
import uuid
from reptrace.garmin.workouts import GarminAdapter, fingerprint, identity
from reptrace.garmin.operations import OperationJournal
from reptrace.storage.coordination import strength_lock
from reptrace.storage.state import (
    Conflict,
    numeric,
    snapshot,
    snapshot_rows,
    revision,
    snapshot_revision,
)


def exercise_mapping(category, code):
    from fitparse.profile import FIELD_TYPES

    field = FIELD_TYPES.get(str(category).lower() + "_exercise_name")
    if not field or (
        code and code not in {str(x).upper() for x in (field.values or {}).values()}
    ):
        raise ValueError("Unsupported Garmin exercise mapping; select a catalog entry")
    return category, code or None


class GarminIntegration:
    def __init__(self, path, state, factory, database, zone, adapter=GarminAdapter):
        self.journal = OperationJournal(path)
        self.state, self.factory, self.database, self.zone, self.adapter = (
            state,
            factory,
            database,
            zone,
            adapter,
        )

    def local(self, activity):
        client, query = self.factory()
        try:
            return snapshot(query, activity)
        finally:
            client.close()

    def ensure_available(self, activity, request_id):
        if any(op["id"] != request_id for op in self.journal.unresolved(activity)):
            raise Conflict(
                "Another Garmin correction is unresolved for this activity; reconcile it before starting a new correction"
            )

    def details(self, activity):
        activity = str(identity(activity))
        with strength_lock():
            local = self.local(activity)
            remote = self.adapter().activity_sets(activity)
            rows = snapshot_rows(local)
            if not rows:
                raise ValueError("No editable local Garmin sets for this activity")
            return dict(
                activityId=activity,
                localRevision=snapshot_revision(local),
                remoteRevision=fingerprint(remote),
                local=rows,
                remote=remote,
            )

    def preview(self, body):
        activity = str(identity(body["activityId"]))
        request_id = str(uuid.UUID(body["requestId"]))
        with strength_lock():
            self.ensure_available(activity, request_id)
            details = self.details(activity)
            if (
                body.get("localRevision") != details["localRevision"]
                or body.get("remoteRevision") != details["remoteRevision"]
            ):
                raise Conflict("Activity changed since reading; fetch current sets")
            original = details["remote"]
            after = deepcopy(original)
            local = self.local(activity)
            rows = details["local"]
            edits = [
                {
                    "id": activity + ":" + str(r["SetIndex"]),
                    "exercise": r["Exercise"],
                    "weight": r.get("weightKg"),
                    "reps": r.get("reps"),
                    "note": r.get("dataNote", ""),
                }
                for r in rows
            ]
            changes = body.get("changes")
            if not isinstance(changes, list) or not 1 <= len(changes) <= 250:
                raise ValueError("Supply 1–250 existing-set corrections")
            seen, lines = (
                set(),
                [
                    f"Activity {activity} · completed Garmin sets",
                    "Default: RepTrace + Garmin. RepTrace-only is available.",
                ],
            )
            for c in changes:
                if not isinstance(c, dict) or set(c) - {
                    "setId",
                    "reps",
                    "load",
                    "unit",
                    "category",
                    "exerciseCode",
                }:
                    raise ValueError(
                        "Only exercise identity, reps and load can be corrected"
                    )
                key = c.get("setId")
                if key in seen:
                    raise ValueError("Set targeted twice")
                seen.add(key)
                row = next((r for r in edits if r["id"] == key), None)
                raw = next(
                    (r for r in rows if activity + ":" + str(r["SetIndex"]) == key),
                    None,
                )
                if not row or not str(raw["SetIndex"]).isdigit():
                    raise ValueError(
                        "No stable Garmin source identity for this set; use local editing"
                    )
                index = int(raw["SetIndex"])
                if index >= len(after.get("exerciseSets", [])):
                    raise Conflict("Garmin source set order changed")
                item = after["exerciseSets"][index]
                if item.get("setType") != "ACTIVE":
                    raise ValueError("Rest blocks cannot be edited")
                # Stable source position plus original timing, independent of exercise name.
                from reptrace.training.strength import utc_time

                if item.get("startTime") and utc_time(item["startTime"]) != utc_time(
                    raw["time"]
                ):
                    raise Conflict(
                        "Local and Garmin set timing differ; mapping requires review"
                    )
                before_item = deepcopy(item)
                candidates = item.get("exercises") or []
                if (
                    len(candidates) == 1
                    and raw.get("exerciseCode")
                    and raw["exerciseCode"]
                    != (candidates[0].get("name") or candidates[0].get("category"))
                    and "category" not in c
                ):
                    raise Conflict(
                        "Local and Garmin exercise identities differ; explicitly review the exercise mapping first"
                    )
                before_row = deepcopy(row)
                if "reps" in c:
                    item["repetitionCount"] = numeric(c["reps"], "Reps", True, 500)
                    row["reps"] = item["repetitionCount"]
                if "load" in c:
                    if c.get("unit") not in ("kg", "lb"):
                        raise ValueError(
                            "Specify kg or lb for the recorded load/assistance"
                        )
                    load = numeric(c["load"], "Recorded load", maximum=2000)
                    kg = (
                        None
                        if load is None
                        else load * (0.45359237 if c["unit"] == "lb" else 1)
                    )
                    item["weight"] = None if kg is None else kg * 1000
                    row["weight"] = kg
                if "category" in c or "exerciseCode" in c:
                    category, code = exercise_mapping(
                        c.get("category"), c.get("exerciseCode")
                    )
                    if len(item.get("exercises") or []) != 1:
                        raise ValueError(
                            "Multiple or missing exercise candidates need explicit mapping review"
                        )
                    item["exercises"][0].update(category=category, name=code)
                    row.update(
                        exercise=(code or category).replace("_", " ").title(),
                        garminCategory=category,
                        garminExerciseCode=code,
                    )
                if row == before_row:
                    raise ValueError("No correction supplied for this set")
                lines.append(
                    f"Set {key}: {before_row['exercise']} · {before_row['reps']} reps · {before_row['weight']} kg → {row['exercise']} · {row['reps']} reps · {row['weight']} kg"
                    + (f" (entered {c['load']} {c['unit']})" if "load" in c else "")
                )

                def remote_label(value):
                    names = (
                        ", ".join(
                            str(e.get("name") or e.get("category"))
                            for e in value.get("exercises", [])
                        )
                        or "unknown exercise"
                    )
                    grams = value.get("weight")
                    load = (
                        "unknown load"
                        if grams is None
                        else str(grams / 1000) + " kg recorded load/assistance"
                    )
                    return (
                        names
                        + " · "
                        + str(value.get("repetitionCount"))
                        + " reps · "
                        + load
                    )

                lines.append(
                    "Garmin: " + remote_label(before_item) + " → " + remote_label(item)
                )
            local_body = dict(
                action="workout_save",
                sessionId=activity,
                revision=revision(rows),
                sets=edits,
                requestId=str(uuid.uuid5(uuid.UUID(request_id), "local")),
            )
            data = dict(
                activityId=activity,
                original=original,
                proposed=after,
                localOriginal=local,
                localRevision=details["localRevision"],
                remoteRevision=details["remoteRevision"],
                localBody=local_body,
                remoteStatus="not_started",
                localStatus="not_started",
                preview="\n".join(lines),
            )
            return self.journal.stage(request_id, "correction", body, data, activity)

    def apply(self, request_id, destination="both"):
        if destination not in ("both", "local"):
            raise ValueError("Invalid destination")
        with strength_lock():
            op = self.journal.get(request_id)
            if op["kind"] != "correction":
                raise ValueError("Wrong operation kind")
            if op["status"] == "cancelled":
                raise Conflict("Cancelled preview")
            if op.get("destination", destination) != destination:
                raise Conflict("This operation already has a confirmed destination")
            if op["status"] == "done":
                return op
            self.ensure_available(op["activityId"], request_id)
            client = self.adapter() if destination == "both" else None
            if client and op["remoteStatus"] == "saved":
                try:
                    current_remote = client.activity_sets(op["activityId"])
                    op["remoteReadback"] = current_remote
                    if current_remote != op["proposed"]:
                        op.update(
                            status="local_pending",
                            localStatus="pending",
                            localError="remote_revision_conflict",
                        )
                        self.journal.save(op)
                        return op
                except Exception:
                    op.update(
                        status="local_pending",
                        localStatus="pending",
                        localError="remote_readback_failed",
                    )
                    self.journal.save(op)
                    return op
            if op["status"] == "preview":
                if (
                    snapshot_revision(self.local(op["activityId"]))
                    != op["localRevision"]
                ):
                    raise Conflict("RepTrace changed; request a fresh preview")
                if (
                    client
                    and fingerprint(client.activity_sets(op["activityId"]))
                    != op["remoteRevision"]
                ):
                    raise Conflict("Garmin changed; request a fresh preview")
                op.update(status="intent", destination=destination)
                self.journal.save(op)
            if client and op["remoteStatus"] != "saved":
                if op["remoteStatus"] == "not_started":
                    if (
                        snapshot_revision(self.local(op["activityId"]))
                        != op["localRevision"]
                        or fingerprint(client.activity_sets(op["activityId"]))
                        != op["remoteRevision"]
                    ):
                        raise Conflict(
                            "Activity changed before remote write; request a fresh preview"
                        )
                    op["remoteStatus"] = "uncertain"
                    self.journal.save(op)  # Commit before the external write.
                    try:
                        client.update_activity_sets(op["activityId"], op["proposed"])
                    except Exception:
                        pass  # Reconcile even when the server response was lost.
                try:
                    actual = client.activity_sets(op["activityId"])
                    op["remoteReadback"] = actual
                except Exception:
                    op["status"] = "remote_uncertain"
                    self.journal.save(op)
                    return op
                if actual != op["proposed"]:
                    op["status"] = "remote_unresolved"
                    self.journal.save(op)
                    return op
                op.update(remoteStatus="saved", status="local_pending")
                self.journal.save(op)
            elif not client:
                op["remoteStatus"] = "not_requested"
            try:
                with self.state.connect() as db:
                    audited = db.execute(
                        "SELECT status FROM audit WHERE id=?",
                        (op["localBody"]["requestId"],),
                    ).fetchone()
                if (
                    not audited
                    and snapshot_revision(self.local(op["activityId"]))
                    != op["localRevision"]
                ):
                    raise Conflict(
                        "RepTrace changed after review; local step remains pending"
                    )
                # Existing audit handles retry after a local commit; revisions reject intervening edits.
                op["localResult"] = self.state.apply(
                    op["localBody"], self.factory, self.database, self.zone
                )
            except Exception as error:
                op["localError"] = (
                    "revision_conflict"
                    if isinstance(error, Conflict)
                    else "save_failed"
                )
                op.update(status="local_pending", localStatus="pending")
                self.journal.save(op)
                return op
            op.update(status="done", localStatus="saved")
            self.journal.save(op)
            return op

    def reversal(self, body):
        import json
        from reptrace.storage.state import snapshots_equal

        request_id = str(uuid.UUID(body["requestId"]))
        with strength_lock():
            prior = self.journal.get(body["originalId"])
            if (
                prior["kind"] != "correction"
                or prior["status"] != "done"
                or prior.get("destination") != "both"
            ):
                raise ValueError(
                    "Only a completed combined correction can use this reversal"
                )
            self.ensure_available(prior["activityId"], request_id)
            current = self.local(prior["activityId"])
            with self.state.connect() as db:
                audit = db.execute(
                    "SELECT after_data FROM audit WHERE id=? AND status='done'",
                    (prior["localBody"]["requestId"],),
                ).fetchone()
            if not audit or not snapshots_equal(current, json.loads(audit[0])):
                raise Conflict(
                    "RepTrace changed after correction; review a new targeted correction"
                )
            remote = self.adapter().activity_sets(prior["activityId"])
            if remote != prior["proposed"]:
                raise Conflict(
                    "Garmin changed after correction; review a new targeted correction"
                )
            rows = snapshot_rows(prior["localOriginal"])
            restored_sets = []
            for row in rows:
                category = row.get("ExerciseCategory")
                code = row.get("exerciseCode")
                try:
                    category, code = exercise_mapping(
                        category, None if code == category else code
                    )
                except ValueError:
                    raise ValueError(
                        "An original exercise mapping cannot be restored automatically; review a new targeted correction"
                    ) from None
                restored_sets.append(
                    dict(
                        id=prior["activityId"] + ":" + str(row["SetIndex"]),
                        exercise=row["Exercise"],
                        weight=row.get("weightKg"),
                        reps=row.get("reps"),
                        note=row.get("dataNote", ""),
                        garminCategory=category,
                        garminExerciseCode=code,
                    )
                )
            local_body = dict(
                action="workout_save",
                sessionId=prior["activityId"],
                revision=revision(snapshot_rows(current)),
                requestId=str(uuid.uuid5(uuid.UUID(request_id), "local")),
                sets=restored_sets,
            )
            data = dict(
                activityId=prior["activityId"],
                original=remote,
                proposed=prior["original"],
                localOriginal=current,
                localRevision=snapshot_revision(current),
                remoteRevision=fingerprint(remote),
                localBody=local_body,
                remoteStatus="not_started",
                localStatus="not_started",
                reversalOf=prior["id"],
                preview="REVERSE completed correction "
                + prior["id"]
                + " for activity "
                + prior["activityId"]
                + "\nRestore the stored original exercise identities, reps and loads.\nOriginal reviewed change (reverse its arrows):\n"
                + prior["preview"],
            )
            return self.journal.stage(
                request_id, "correction", body, data, prior["activityId"]
            )

    def call(self, body):
        kind = body.get("operation")
        from reptrace.garmin.creation import Creation

        creation = Creation(self.journal, self.adapter)
        if kind == "device_list":
            return creation.devices()
        if kind == "creation_preview":
            with strength_lock():
                return creation.preview(body)
        if kind == "creation_apply":
            with strength_lock():
                return creation.apply(
                    self.journal.get(body["requestId"]), body.get("selection")
                )
        if kind == "activity_reverse_preview":
            return self.reversal(body)
        if kind == "activity_details":
            return self.details(body["activityId"])
        if kind == "activity_preview":
            return self.preview(body)
        if kind == "integration_apply":
            return self.apply(body["requestId"], body.get("destination", "both"))
        if kind == "integration_list":
            return {"operations": self.journal.recent()}
        if kind == "integration_resume":
            from reptrace.garmin.recovery import resume_operation

            return resume_operation(self, body)
        if kind == "integration_status":
            return self.journal.get(body["requestId"])
        if kind == "integration_cancel":
            with strength_lock():
                op = self.journal.get(body["requestId"])
                if op["status"] != "preview":
                    raise Conflict("A started operation cannot be cancelled")
                op["status"] = "cancelled"
                self.journal.save(op)
                return op
        raise ValueError("Unknown integration operation")
