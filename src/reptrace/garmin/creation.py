"""Build new strength templates from reviewed program steps, never calendar entries."""

from copy import deepcopy
import unicodedata
from reptrace.garmin.workouts import full_workout_edit, saved_workout_matches
from reptrace.storage.state import numeric, text, Conflict


def build_session(session):
    from reptrace.garmin.integration import exercise_mapping

    sport = {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5}
    lines = [text(session.get("name"), "Session name", 120)]

    def build(items, depth=0):
        if depth > 4 or not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise ValueError("Invalid program step list")
        result = []
        for item in items:
            if item.get("kind") == "repeat":
                count = numeric(item.get("count"), "Repeat count", True, 100)
                if count is None or count < 2:
                    raise ValueError("Repeat count must be 2–100")
                lines.append("  " * depth + f"Repeat {count} times:")
                result.append(
                    {
                        "type": "RepeatGroupDTO",
                        "stepType": {
                            "stepTypeId": 6,
                            "stepTypeKey": "repeat",
                            "displayOrder": 6,
                        },
                        "numberOfIterations": count,
                        "workoutSteps": build(item.get("steps"), depth + 1),
                        "smartRepeat": False,
                    }
                )
                continue
            if item.get("kind") != "exercise":
                raise ValueError("Expected exercise or repeat block")
            category, code = exercise_mapping(
                item.get("category"), item.get("exerciseCode")
            )
            notes = item.get("notes") or ""
            if not isinstance(notes, str) or len(notes) > 500:
                raise ValueError("Invalid exercise notes")
            if not code and not notes.strip():
                raise ValueError("Generic exercises need explicit notes")
            reps = numeric(item.get("reps"), "Reps", True, 500)
            seconds = numeric(item.get("seconds"), "Seconds", maximum=86400)
            if reps is not None and seconds is not None:
                raise ValueError("Choose reps or timed duration")
            if reps == 0 or seconds == 0:
                raise ValueError("Exercise target must be positive")
            condition, value, cid = (
                ("reps", reps, 10)
                if reps is not None
                else ("time", seconds, 2)
                if seconds is not None
                else ("lap.button", None, 1)
            )
            weight = numeric(item.get("load"), "Load", maximum=2000)
            unit = item.get("unit")
            convention = item.get("convention")
            if weight is not None and (
                unit not in ("kg", "lb")
                or convention
                not in (
                    "total",
                    "per-dumbbell",
                    "per-side",
                    "machine-stack",
                    "bodyweight",
                    "assistance",
                )
            ):
                raise ValueError("Specify load unit and equipment convention")
            description = notes + (f" [{convention}]" if convention else "")
            result.append(
                {
                    "type": "ExecutableStepDTO",
                    "stepType": {
                        "stepTypeId": 3,
                        "stepTypeKey": "interval",
                        "displayOrder": 3,
                    },
                    "endCondition": {
                        "conditionTypeId": cid,
                        "conditionTypeKey": condition,
                        "displayOrder": cid,
                    },
                    "endConditionValue": value,
                    "targetType": {
                        "workoutTargetTypeId": 1,
                        "workoutTargetTypeKey": "no.target",
                        "displayOrder": 1,
                    },
                    "category": category,
                    "exerciseName": code or "",
                    "description": description or None,
                    "weightValue": weight,
                    "weightUnit": None
                    if weight is None
                    else {
                        "unitId": 8 if unit == "kg" else 9,
                        "unitKey": "kilogram" if unit == "kg" else "pound",
                        "factor": 1000.0 if unit == "kg" else 453.59237,
                    },
                }
            )
            rest = numeric(item.get("restSeconds"), "Rest seconds", maximum=86400)
            if rest != 0:
                rc, rid = ("lap.button", 1) if rest is None else ("time", 2)
                result.append(
                    {
                        "type": "ExecutableStepDTO",
                        "stepType": {
                            "stepTypeId": 5,
                            "stepTypeKey": "rest",
                            "displayOrder": 5,
                        },
                        "endCondition": {
                            "conditionTypeId": rid,
                            "conditionTypeKey": rc,
                            "displayOrder": rid,
                        },
                        "endConditionValue": rest,
                    }
                )
            lines.append(
                "  " * depth
                + f"{(code or category).replace('_', ' ').title()}: {str(reps) + ' reps' if reps is not None else str(seconds) + ' s' if seconds is not None else 'open exercise target'}; {str(weight) + ' ' + unit + ' ' + convention if weight is not None else 'no load target'}; {'open rest' if rest is None else str(rest) + ' s rest'}"
                + (f" · {notes}" if notes else "")
            )
        return result

    segments = [
        {
            "segmentOrder": 1,
            "sportType": sport,
            "workoutSteps": build(session.get("steps")),
        }
    ]
    payload = full_workout_edit(
        {"sportType": sport},
        {
            "name": session["name"],
            "description": session.get("description"),
            "segments": segments,
        },
    )
    return payload, "\n".join(lines)


def matches(expected, actual):
    return saved_workout_matches(
        dict(expected, workoutId=actual.get("workoutId")), actual
    )


def matching_devices(devices):
    result = []
    for d in devices:
        name = d.get("productDisplayName") or d.get("displayName") or ""
        normalized = (
            unicodedata.normalize("NFKD", name)
            .encode("ascii", "ignore")
            .decode()
            .lower()
        )
        if "fenix 7" in normalized and "pro" in normalized:
            result.append({"id": d.get("deviceId"), "name": name})
    return result


class Creation:
    def __init__(self, journal, adapter):
        self.journal, self.adapter = journal, adapter

    def devices(self):
        with self.journal.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS integration_settings (key TEXT PRIMARY KEY, value TEXT)"
            )
            row = db.execute(
                "SELECT value FROM integration_settings WHERE key='device'"
            ).fetchone()
        devices = matching_devices(self.adapter().devices())
        selected = row[0] if row else None
        if selected is None and len(devices) == 1:
            selected = str(devices[0]["id"])
            with self.journal.connect() as db:
                db.execute(
                    "INSERT OR IGNORE INTO integration_settings VALUES ('device',?)",
                    (selected,),
                )
        return {"devices": devices, "selectedDeviceId": selected}

    def preview(self, body):
        import uuid

        request_id = str(uuid.UUID(body["requestId"]))
        sessions = body.get("sessions")
        if not isinstance(sessions, list) or not 1 <= len(sessions) <= 12:
            raise ValueError("Supply 1–12 named sessions")
        devices = self.devices()
        device = body.get("deviceId") or devices["selectedDeviceId"]
        if device is None and len(devices["devices"]) == 1:
            device = devices["devices"][0]["id"]
        selected = next(
            (d for d in devices["devices"] if str(d["id"]) == str(device)), None
        )
        if not selected:
            raise ValueError("Choose one fēnix 7 Pro from device_list before review")
        items = []
        for session in sessions:
            payload, preview = build_session(session)
            items.append(
                dict(
                    payload=payload,
                    preview=preview,
                    creation="not_started",
                    delivery="not_started",
                    workoutId=None,
                )
            )
        return self.journal.stage(
            request_id,
            "creation",
            body,
            dict(
                device=selected,
                items=items,
                preview="NEW saved workouts; existing same-name workouts retained.\nDevice: "
                + selected["name"]
                + "\n\n"
                + "\n\n".join(i["preview"] for i in items)
                + "\nDelivery requested after save; sync your watch. No scheduling or automatic start.",
            ),
        )

    def apply(self, op, selection):
        if op["kind"] != "creation":
            raise ValueError("Wrong operation kind")
        if selection is None:
            selection = list(range(len(op["items"])))
        if (
            not isinstance(selection, list)
            or not selection
            or any(type(i) != int or not 0 <= i < len(op["items"]) for i in selection)
        ):
            raise ValueError("Select valid session indices")
        if op["status"] == "cancelled":
            raise Conflict("Cancelled preview")
        if op.get("selection", selection) != selection:
            raise Conflict("Selection is fixed for this confirmed operation")
        if op["status"] == "done":
            return op
        client = self.adapter()
        op.update(selection=selection, status="running")
        self.journal.save(op)
        with self.journal.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS integration_settings (key TEXT PRIMARY KEY, value TEXT)"
            )
            db.execute(
                "INSERT OR REPLACE INTO integration_settings VALUES ('device',?)",
                (str(op["device"]["id"]),),
            )
        for index in selection:
            item = op["items"][index]
            try:
                if item["creation"] == "not_started":
                    item["beforeIds"] = [str(w["workoutId"]) for w in client.list()]
                    item["creation"] = "uncertain"
                    self.journal.save(op)
                    try:
                        response = client.create(item["payload"])
                        if isinstance(response, dict) and response.get("workoutId"):
                            item["workoutId"] = response["workoutId"]
                            self.journal.save(op)
                    except Exception:
                        pass
                if item["creation"] != "saved":
                    if item["workoutId"] is None:
                        candidates = []
                        for candidate in client.list():
                            if (
                                str(candidate["workoutId"]) in item["beforeIds"]
                                or candidate.get("workoutName")
                                != item["payload"]["workoutName"]
                            ):
                                continue
                            actual = client.get(candidate["workoutId"])
                            if matches(item["payload"], actual):
                                candidates.append(actual)
                        if len(candidates) != 1:
                            item["creation"] = "unresolved"
                            self.journal.save(op)
                            continue
                        item["workoutId"] = candidates[0]["workoutId"]
                    actual = client.get(item["workoutId"])
                    item["readback"] = actual
                    if not matches(item["payload"], actual):
                        item["creation"] = "readback_mismatch"
                        self.journal.save(op)
                        continue
                    item["creation"] = "saved"
                    self.journal.save(op)
                if item["delivery"] in ("not_started", "failed"):
                    item["delivery"] = "uncertain"
                    self.journal.save(op)
                    try:
                        item["deliveryResponse"] = client.deliver(
                            item["workoutId"],
                            op["device"]["id"],
                            item["payload"]["workoutName"],
                        )
                        item["delivery"] = "requested"
                    except Exception as error:
                        # Only an explicit rejection permits retrying delivery.
                        status = getattr(
                            getattr(error, "response", None), "status_code", None
                        )
                        if status in (400, 401, 403, 404, 422, 429):
                            item["delivery"] = "failed"
                    self.journal.save(op)
                if item["delivery"] == "uncertain":
                    messages = client.device_messages()
                    if isinstance(messages, dict):
                        messages = messages.get("messages", [])
                    if any(
                        str(m.get("deviceId")) == str(op["device"]["id"])
                        and str(m.get("metaDataId")) == str(item["workoutId"])
                        for m in messages
                    ):
                        item["delivery"] = "requested"
                        item["deliveryReadback"] = True
                        self.journal.save(op)
            except Exception:
                # Preserve the last durable step; a later Save only reconciles it.
                self.journal.save(op)
        op["status"] = (
            "done"
            if all(op["items"][i]["delivery"] == "requested" for i in selection)
            else "partial"
        )
        self.journal.save(op)
        return op
