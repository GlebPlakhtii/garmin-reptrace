"""Import a reviewed manual training TSV, preserving provenance and missing data.

Dry-run by default. --write archives conflicting Garmin exercise data, merges
same-day workouts, and writes a registry used by both Garmin collectors.
"""

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from reptrace.training.strength import (
    BODYWEIGHT_CATEGORIES,
    EXERCISE_NAME_ALIASES,
    number,
    utc_time,
)


# Names reviewed with the user. New exercises keep their manual names.
EXERCISE_ALIASES = {
    "EZ Bar Skull Crusher": "Lying Ez Bar Triceps Extension",
    "Cable Tricep Extension": "Cable Triceps Extension",
    "Pull-up": "Pull Up",
    "Lat Prayer": "Straight Arm Pulldown",
    "EZ Bar Curl": "Standing Ez Bar Biceps Curl",
    "Cable Bicep Curl": "Cable Biceps Curl",
    "Bench Press": "Barbell Bench Press",
    "Incline Dumbbell Press": "Incline Dumbbell Bench Press",
    "Cable Fly": "Cable Chest Fly",  # User confirmed cables, despite Garmin's banded-fly label.
    "Machine Fly": "Machine Chest Fly",
    "Cable Lateral Raise": "One Arm Cable Lateral Raise",
    "Lying Leg Curl": "Lying Leg Curl",
    "Leg Extension": "Machine Leg Extension",
    "Leg Press Calf Raise": "Leg Press Calf Raise",
    "Deadlift": "Barbell Deadlift",
    "Barbell Squat": "Overhead Barbell Squat",
    "Barbell squat": "Overhead Barbell Squat",
    "Push-up": "Push Up",
}


def read_records(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    required = {"Session ID", "Date", "Exersize", "Sets", "Weights", "Reps"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(
            "Expected a tab-separated manual log with Session ID, Date, Exersize, Sets, Weights, Reps"
        )
    records = []
    for index, raw in enumerate(rows, 1):
        record = {
            "sourceRow": index,
            "raw": raw,
            "session": raw["Session ID"].strip(),
            "date": datetime.strptime(raw["Date"].strip(), "%d/%m/%Y").date(),
            "exercise": raw["Exersize"].strip(),
            "sets": int(raw["Sets"].strip()),
            "weights": raw["Weights"].split(),
            "reps": raw["Reps"].split(),
        }
        if not record["session"] or not record["exercise"] or record["sets"] <= 0:
            raise ValueError(f"Invalid identity or set count at source entry {index}")
        records.append(record)
    return records


def reviewed_records(records, profile=None):
    """Apply an explicitly supplied review profile, preserving correction notes.

    Personal record-specific rules belong in a private JSON file, not source code.
    Without a profile, extra values fail validation instead of being discarded.
    """
    rules = (profile or {}).get("rules", [])
    for rule in rules:
        match = rule.get("match", {})
        if not {"session", "date", "exercise"}.issubset(match):
            raise ValueError("Review rules must identify session, date, and exercise")
        replacements = rule.get("replace", {})
        if set(replacements) - {"weights", "reps"}:
            raise ValueError("Review rules may replace only weights or reps")
        if any(
            not isinstance(values, list) or any(not isinstance(v, str) for v in values)
            for values in replacements.values()
        ):
            raise ValueError("Reviewed weights and reps must be lists of strings")
        if replacements and not rule.get("correction"):
            raise ValueError("Reviewed replacements require an explanation")
    seen = set()
    for original in records:
        record = dict(original)
        key = (record["session"], record["exercise"].casefold())
        record["skipReason"] = ""
        comparable = dict(record, date=record["date"].isoformat())
        for rule in rules:
            if all(
                comparable.get(key) == value for key, value in rule["match"].items()
            ):
                if rule.get("duplicateOnly") and key not in seen:
                    continue
                record.update(rule.get("replace", {}))
                for field in ("skipReason", "correction"):
                    if rule.get(field):
                        record[field] = rule[field]
        seen.add(key)
        if not record["skipReason"] and (
            len(record["weights"]) > record["sets"]
            or len(record["reps"]) > record["sets"]
        ):
            raise ValueError(f"Unreviewed extra values at entry {record['sourceRow']}")
        yield record


def quote(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def summarize(points, tags, stamp, workout_name, label, activity_id=None):
    groups = defaultdict(list)
    for point in points:
        groups[(point["tags"]["Exercise"], point["tags"]["ExerciseCategory"])].append(
            point["fields"]
        )
    summaries = []
    for (exercise, category), sets in groups.items():
        fields = {
            "sets": len(sets),
            "setsWithWeight": sum("weightKg" in s for s in sets),
            "setsWithReps": sum("reps" in s for s in sets),
            "workoutName": workout_name,
            "workoutLabel": label,
            "source": "Manual CSV",
            "timeAccuracy": "date-only",
        }
        if activity_id is not None:
            fields.update(
                activityId=activity_id,
                activityUrl=f"https://connect.garmin.com/modern/activity/{activity_id}",
            )
        for field, output, aggregate in [
            ("weightKg", "bestWeightKg", max),
            ("reps", "totalReps", sum),
            ("reps", "bestReps", max),
            ("volumeKg", "volumeKg", sum),
            ("estimated1RMKg", "estimated1RMKg", max),
        ]:
            values = [s[field] for s in sets if field in s]
            if values:
                value = aggregate(values)
                fields[output] = int(value) if field == "reps" else float(value)
        summaries.append(
            {
                "measurement": "StrengthExercise",
                "time": stamp,
                "tags": dict(tags, Exercise=exercise, ExerciseCategory=category),
                "fields": fields,
            }
        )
    return summaries


def build_session(records, workout, catalog, database, source_hash, local_zone):
    """Build points without modifying the database. Missing values stay absent."""
    session = records[0]["session"]
    day = records[0]["date"]
    if any(r["date"] != day or r["session"] != session for r in records):
        raise ValueError("A session must have one date and identity")
    activity_id = int(workout["Activity_ID"]) if workout else None
    identity = str(activity_id) if workout else f"manual-csv-session-{session}"
    stamp = (
        utc_time(workout["time"])
        if workout
        else datetime.combine(
            day, datetime.min.time().replace(hour=12), ZoneInfo(local_zone)
        )
        .astimezone(timezone.utc)
        .isoformat()
    )
    title = workout["activityName"] if workout else f"Manual workout {session}"
    # The CSV has dates only; noon is a date placement, not a recorded start time.
    selector_label = f"{day} · {title} | {identity}"
    tags = {
        "Device": workout["Device"] if workout else "Manual log",
        "Database_Name": database,
        "ActivityID": identity,
    }
    if workout and workout.get("User_ID"):
        tags["User_ID"] = workout["User_ID"]
    points = []
    set_numbers = defaultdict(int)
    order = 0
    audit = []
    for record in records:
        audit.append(
            {
                "measurement": "StrengthManualSource",
                "time": stamp,
                "tags": dict(tags, SourceRow=str(record["sourceRow"])),
                "fields": {
                    "sourceHash": source_hash,
                    "sourceSession": session,
                    "sourceRow": record["sourceRow"],
                    "originalRecord": json.dumps(record["raw"], ensure_ascii=False),
                    "skipReason": record.get("skipReason", ""),
                    "correction": record.get("correction", ""),
                },
            }
        )
        if record.get("skipReason"):
            continue
        exercise = EXERCISE_ALIASES.get(record["exercise"], record["exercise"])
        exercise = EXERCISE_NAME_ALIASES.get(exercise, exercise)
        category, code = catalog.get(exercise, ("MANUAL", record["exercise"]))
        if exercise in {"Dip", "Decline Crunch", "Leg Raise", "Cable Crunch"}:
            category = {
                "Dip": "DIP",
                "Decline Crunch": "CRUNCH",
                "Leg Raise": "LEG_RAISE",
                "Cable Crunch": "CRUNCH",
            }[exercise]
        for i in range(record["sets"]):
            order += 1
            set_numbers[exercise] += 1
            raw_weight = record["weights"][i] if i < len(record["weights"]) else ""
            raw_reps = record["reps"][i] if i < len(record["reps"]) else ""
            fields = {
                "setCount": 1,
                "setNumber": set_numbers[exercise],
                "setOrder": order,
                "workoutName": title,
                "exerciseCode": code,
                "source": "Manual CSV",
                "originalExercise": record["exercise"],
                "sourceSession": session,
                "sourceRow": record["sourceRow"],
                "sourceDate": day.isoformat(),
                "sourceHash": source_hash,
                "rawWeight": raw_weight,
                "rawReps": raw_reps,
                "timeAccuracy": "date-only",
            }
            if activity_id is not None:
                fields.update(
                    activityId=activity_id,
                    activityUrl=f"https://connect.garmin.com/modern/activity/{activity_id}",
                )
            if ":" in raw_weight or ":" in raw_reps:
                fields["dataNote"] = (
                    f"Unresolved notation: load {raw_weight}, reps {raw_reps}; numeric metrics omitted"
                )
            else:
                weight, reps = number(raw_weight), number(raw_reps)
                if weight is not None:
                    fields["weightKg"] = weight
                if reps is not None:
                    if reps != int(reps):
                        raise ValueError(
                            f"Noninteger reps at entry {record['sourceRow']}"
                        )
                    fields["reps"] = int(reps)
                if weight is not None and reps is not None:
                    fields["volumeKg"] = weight * reps
                    if (
                        weight > 0
                        and 1 <= reps <= 10
                        and category not in BODYWEIGHT_CATEGORIES
                    ):
                        fields["estimated1RMKg"] = (
                            weight if reps == 1 else weight * (1 + reps / 30)
                        )
            # A shared date placeholder avoids fabricating set times or duration.
            points.append(
                {
                    "measurement": "StrengthSet",
                    "time": stamp,
                    "tags": dict(
                        tags,
                        Exercise=exercise,
                        ExerciseCategory=category,
                        SetIndex=f"manual-{session}-{record['sourceRow']}-{i}",
                    ),
                    "fields": fields,
                }
            )
    summaries = summarize(points, tags, stamp, title, selector_label, activity_id)
    if not workout:
        # Deterministic negative ID is in a separate namespace from Garmin IDs.
        numeric_id = -int(day.strftime("%Y%m%d") + session.zfill(4))
        audit.append(
            {
                "measurement": "ActivitySummary",
                "time": stamp,
                "tags": dict(tags, ActivitySelector=identity),
                "fields": {
                    "Activity_ID": numeric_id,
                    "activityName": title,
                    "activityType": "strength_training",
                    "source": "Manual CSV",
                    "timeAccuracy": "date-only",
                    "sourceSession": session,
                },
            }
        )
    marker = {
        "measurement": "StrengthManualSession",
        "time": stamp,
        "tags": tags,
        "fields": {
            "importedSets": len(points),
            "sourceHash": source_hash,
            "sourceSession": session,
            "source": "Manual CSV",
            "mergedWithGarmin": bool(workout),
        },
    }
    return points + summaries + audit + [marker]


def already_imported(markers, source_hash, session):
    if not markers:
        return False
    if any(p.get("sourceHash") != source_hash for p in markers):
        raise ValueError(
            "Reviewed data or a different CSV version already exists for "
            + session
            + "; reconcile it explicitly"
        )
    return True


def main():
    from influxdb import InfluxDBClient

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--timezone", default="Europe/Kyiv")
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--review-profile",
        type=Path,
        help="Private JSON with explicitly reviewed corrections",
    )
    args = parser.parse_args()
    if os.getenv("INFLUXDB_VERSION", "1") != "1":
        parser.error("This archive-and-merge importer currently requires InfluxDB 1.x")
    database = os.getenv("INFLUXDB_DATABASE", "GarminStats")
    secure = os.getenv("INFLUXDB_ENDPOINT_IS_HTTP", "true").lower() in (
        "false",
        "0",
        "no",
    )
    client = InfluxDBClient(
        host=os.getenv("INFLUXDB_HOST", "influxdb"),
        port=int(os.getenv("INFLUXDB_PORT", "8086")),
        username=os.getenv("INFLUXDB_USERNAME"),
        password=os.getenv("INFLUXDB_PASSWORD"),
        database=database,
        ssl=secure,
        verify_ssl=secure,
    )

    def query(q):
        return list(client.query(q).get_points())

    profile = (
        json.loads(args.review_profile.read_text()) if args.review_profile else None
    )
    records = list(reviewed_records(read_records(args.path), profile))
    source_hash = hashlib.sha256(args.path.read_bytes()).hexdigest()
    sessions = defaultdict(list)
    for r in records:
        sessions[r["session"]].append(r)
    # Fetch existing names/codes before touching any data.
    catalog = {}
    for row in query(
        'SELECT "Exercise", "ExerciseCategory", LAST("exerciseCode") FROM "StrengthSet" GROUP BY "Exercise", "ExerciseCategory"'
    ):
        catalog[row["Exercise"]] = (row["ExerciseCategory"], row["last"])
    workouts = defaultdict(list)
    for row in query(
        'SELECT "Activity_ID", "activityName", "Device", "User_ID" FROM "ActivitySummary" WHERE "activityType" = \'strength_training\' AND "Activity_ID" > 0'
    ):
        day = (
            datetime.fromisoformat(row["time"].replace("Z", "+00:00"))
            .astimezone(ZoneInfo(args.timezone))
            .date()
        )
        workouts[day].append(row)
    plan = []
    for session, rows in sessions.items():
        matches = workouts.get(rows[0]["date"], [])
        if len(matches) > 1:
            raise ValueError(
                f"More than one Garmin strength workout on {rows[0]['date']}; explicit matching required"
            )
        points = build_session(
            rows,
            matches[0] if matches else None,
            catalog,
            database,
            source_hash,
            args.timezone,
        )
        marker = points[-1]
        existing = query(
            'SELECT * FROM "StrengthManualSession" WHERE "ActivityID" = '
            + quote(marker["tags"]["ActivityID"])
        )
        if already_imported(existing, source_hash, session):
            print(f"Session {session}: already imported; skipping", flush=True)
            continue
        archived = []
        for measurement in ["StrengthSet", "StrengthExercise"]:
            for row in query(
                f'SELECT * FROM "{measurement}" WHERE "ActivityID" = '
                + quote(marker["tags"]["ActivityID"])
            ):
                if row.get("source") == "Manual CSV":
                    continue  # Never overwrite the originals with a partial retry.
                tag_keys = [
                    "Device",
                    "Database_Name",
                    "ActivityID",
                    "Exercise",
                    "ExerciseCategory",
                    "SetIndex",
                    "User_ID",
                ]
                archived.append(
                    {
                        "measurement": measurement + "GarminArchive",
                        "time": row["time"],
                        "tags": {k: row[k] for k in tag_keys if row.get(k) is not None},
                        "fields": {
                            k: v
                            for k, v in row.items()
                            if k not in tag_keys + ["time"] and v is not None
                        },
                    }
                )
        sets = [p for p in points if p["measurement"] == "StrengthSet"]
        print(
            f"Session {session} ({rows[0]['date']}): {len(sets)} manual sets; "
            + (
                "merge into Garmin " + marker["tags"]["ActivityID"]
                if matches
                else "new manual workout"
            )
            + f"; archive {len(archived)} Garmin points",
            flush=True,
        )
        plan.append((points, archived))
    if not args.write:
        print(
            f"DRY RUN: {len(plan)} sessions, {sum(p[-1]['fields']['importedSets'] for p, a in plan)} sets; no database changes",
            flush=True,
        )
        client.close()
        return
    # Persist the complete originals before any replacement. Old source data stays
    # available in archive measurements; manual raw rows are also stored verbatim.
    all_archived = [p for _, archive in plan for p in archive]
    if all_archived and not client.write_points(all_archived):
        raise RuntimeError("Could not archive Garmin originals; import aborted")
    for points, archive in plan:
        identity = points[-1]["tags"]["ActivityID"]
        for measurement in ["StrengthSet", "StrengthExercise"]:
            client.query(
                f'DELETE FROM "{measurement}" WHERE "ActivityID" = ' + quote(identity)
            )
        # Registry is written last, so an interrupted session is retried.
        if not client.write_points(points[:-1]) or not client.write_points(
            [points[-1]]
        ):
            raise RuntimeError(
                "Manual import failed for "
                + identity
                + "; originals are in archive measurements"
            )
    client.close()
    print(
        f"IMPORTED: {len(plan)} sessions, {sum(p[-1]['fields']['importedSets'] for p, a in plan)} sets",
        flush=True,
    )


if __name__ == "__main__":
    main()
