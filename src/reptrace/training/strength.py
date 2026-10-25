"""Convert Garmin exercise sets to stable, queryable strength measurements."""

from collections import defaultdict
from datetime import datetime, timezone
from math import isfinite

# Recorded loads on bodyweight/assisted movements cannot estimate a total-load 1RM.
BODYWEIGHT_CATEGORIES = {
    "PULL_UP",
    "PUSH_UP",
    "DIP",
    "CRUNCH",
    "SIT_UP",
    "PLANK",
    "LEG_RAISE",
}
EXERCISE_NAME_ALIASES = {
    "Bench Press": "Barbell Bench Press",
    "Flye": "Machine Chest Fly",
    "Machine Fly": "Machine Chest Fly",
    "Fly": "Cable Chest Fly",
    "Banded Fly": "Cable Chest Fly",
    "Cable Fly": "Cable Chest Fly",
    "Cable Crossover": "Cable Chest Fly",
    "Weighted Seated Calf Raise": "Leg Press Calf Raise",
    "Weighted Leg Curl": "Lying Leg Curl",
    "Weighted Leg Extensions": "Machine Leg Extension",
    "Leg Extensions": "Machine Leg Extension",
    "Leg Extension": "Machine Leg Extension",
    "Triceps Extension": "Cable Triceps Extension",
    "Cable Tricep Extension": "Cable Triceps Extension",
}


def number(value):
    """Keep missing/invalid metrics missing instead of turning them into zero."""
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) and value >= 0 else None


def utc_time(value):
    # Garmin exerciseSets startTime is GMT, even when its ISO string lacks Z.
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).isoformat()


def has_manual_strength_details(client, version, activity_id):
    """A reviewed manual session takes precedence over the raw Garmin sets."""
    activity_id = str(int(activity_id))
    query = f'SELECT "importedSets" FROM "StrengthManualSession" WHERE "ActivityID" = \'{activity_id}\''
    if version == "1":
        return bool(list(client.query(query).get_points()))
    return bool(client.query(query, language="influxql").to_pylist())


def build_strength_points(activity, payload, device, database):
    """Return one point per rep-based active set and per exercise per workout.

    Garmin's exerciseSets endpoint reports weights in grams; store kg. Ignore
    warmup/cardio records without reps, and attach following rest to each set.
    Volume is recorded external load x reps, without bodyweight corrections.
    """
    sets = payload.get("exerciseSets") or []
    points, by_exercise = [], defaultdict(list)
    workout_time = utc_time(activity["startTimeGMT"].replace(" ", "T"))
    common = {
        "Device": device,
        "Database_Name": database,
        "ActivityID": str(activity["activityId"]),
    }
    if activity.get("User_ID"):
        common["User_ID"] = activity["User_ID"]
    for index, item in enumerate(sets):
        reps = number(item.get("repetitionCount"))
        if item.get("setType") != "ACTIVE" or reps is None or reps <= 0:
            continue
        candidates = item.get("exercises") or []
        exercise = (
            max(candidates, key=lambda e: number(e.get("probability")) or 0)
            if candidates
            else {}
        )
        category = exercise.get("category") or "UNKNOWN"
        code = exercise.get("name") or category
        original_name = code.replace("_", " ").title()
        name = EXERCISE_NAME_ALIASES.get(original_name, original_name)
        tags = dict(common, Exercise=name, ExerciseCategory=category)
        fields = {
            "setCount": 1,
            "reps": int(reps),
            "setOrder": index + 1,
            "setNumber": len(by_exercise[(name, category)]) + 1,
            "workoutName": activity.get("activityName") or "Strength training",
            "exerciseCode": code,
            "activityId": int(activity["activityId"]),
            "activityUrl": f"https://connect.garmin.com/modern/activity/{activity['activityId']}",
            "source": "Garmin",
        }
        if name != original_name:
            fields["originalExercise"] = original_name
        duration = number(item.get("duration"))
        if duration is not None:
            fields["durationSeconds"] = duration
        # Only attach rest when Garmin actually recorded a following rest block.
        rests = []
        for following in sets[index + 1 :]:
            if following.get("setType") != "REST":
                break
            rest = number(following.get("duration"))
            if rest is not None:
                rests.append(rest)
        if rests:
            fields["restAfterSeconds"] = sum(rests)
        weight = number(item.get("weight"))
        if weight is not None:
            weight /= 1000.0
            fields["weightKg"] = weight
            fields["volumeKg"] = weight * reps
            if weight > 0 and 1 <= reps <= 10 and category not in BODYWEIGHT_CATEGORIES:
                fields["estimated1RMKg"] = (
                    weight if reps == 1 else weight * (1 + reps / 30)
                )
        stamp = utc_time(item["startTime"]) if item.get("startTime") else workout_time
        # SetIndex also distinguishes sets with identical/missing timestamps.
        points.append(
            {
                "measurement": "StrengthSet",
                "time": stamp,
                "tags": dict(tags, SetIndex=str(index)),
                "fields": fields,
            }
        )
        by_exercise[(name, category)].append(fields)
    for (name, category), records in by_exercise.items():
        fields = {
            "sets": len(records),
            "totalReps": sum(r["reps"] for r in records),
            "bestReps": max(r["reps"] for r in records),
            "workoutName": activity.get("activityName") or "Strength training",
            "activityId": int(activity["activityId"]),
            "activityUrl": f"https://connect.garmin.com/modern/activity/{activity['activityId']}",
            "source": "Garmin",
            "workoutLabel": f"{workout_time[:16].replace('T', ' ')} UTC · {activity.get('activityName') or 'Strength training'} | {activity['activityId']}",
        }
        for source, dest, reducer in [
            ("weightKg", "bestWeightKg", max),
            ("volumeKg", "volumeKg", sum),
            ("estimated1RMKg", "estimated1RMKg", max),
            ("durationSeconds", "activeSeconds", sum),
            ("restAfterSeconds", "restSeconds", sum),
        ]:
            values = [r[source] for r in records if source in r]
            if values:
                fields[dest] = float(reducer(values))
        # Avoid reporting an incomplete total as if every set had a load.
        fields["setsWithWeight"] = sum("weightKg" in r for r in records)
        points.append(
            {
                "measurement": "StrengthExercise",
                "time": workout_time,
                "tags": dict(common, Exercise=name, ExerciseCategory=category),
                "fields": fields,
            }
        )
    return points
