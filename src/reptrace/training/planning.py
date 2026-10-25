"""Explainable next-session targets from named workouts; never writes workout data."""

from collections import OrderedDict
from datetime import date
import math
import re

TYPES = {
    "upper1": "Upper 1",
    "upper2": "Upper 2",
    "lower1": "Lower 1",
    "lower2": "Lower 2",
}
REVIEW_EXERCISES = {"pull up", "push up", "dip"}


def workout_type(name):
    compact = re.sub(r"[^a-z0-9]", "", str(name).lower())
    return {
        "upper1": "upper1",
        "upper2": "upper2",
        "lower1": "lower1",
        "lower2": "lower2",
        "legday1": "lower1",
        "legday2": "lower2",
    }.get(compact)


def known(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def clean_set(row):
    return {
        "weight": row.get("weight") if known(row.get("weight")) else None,
        "reps": row.get("reps") if known(row.get("reps")) else None,
    }


def ordered(rows):
    return sorted(
        rows,
        key=lambda s: (s.get("order") or 0, s.get("number") or 0, s.get("time") or ""),
    )


def total(rows):
    return sum(r["reps"] for r in rows)


def valid(rows):
    return bool(rows) and all(
        known(r.get("weight"))
        and r["weight"] >= 0
        and known(r.get("reps"))
        and 1 <= r["reps"] <= 50
        and int(r["reps"]) == r["reps"]
        and not r.get("note")
        for r in rows
    )


def matching(a, b):
    return (
        valid(a)
        and valid(b)
        and sorted(r["weight"] for r in a) == sorted(r["weight"] for r in b)
    )


def progression_rule(name, rows, overrides):
    custom = overrides.get(name, {})
    positive = [r["weight"] for r in rows if known(r.get("weight")) and r["weight"] > 0]
    smallest = min(positive) if positive else 0
    default_step = 2.5 if smallest >= 25 else 1.0 if smallest >= 10 else 0.5
    return {
        "repMin": custom.get("repMin", 8),
        "repMax": custom.get("repMax", 12),
        "weightStep": custom.get("weightStep") or default_step,
        "stepSource": "custom" if custom.get("weightStep") else "default",
    }


def build_next_sessions(data, as_of=None):
    day = (
        as_of
        if isinstance(as_of, date)
        else date.fromisoformat(as_of)
        if as_of
        else date.today()
    )
    sets = {}
    for row in data["sets"]:
        if str(row.get("exercise", "")).strip().casefold() == "unknown":
            continue
        sets.setdefault(row["sessionId"], []).append(row)
    sessions = sorted(
        (w for w in data["workouts"] if w["date"] <= day.isoformat()),
        key=lambda w: (w["date"], w.get("time", "")),
        reverse=True,
    )
    plans = []
    for key, label in TYPES.items():
        history = [w for w in sessions if workout_type(w["name"]) == key]
        usable = [w for w in history if sets.get(w["id"])]
        baseline = usable[0] if usable else None
        plan = {
            "type": key,
            "name": label,
            "generatedDate": day.isoformat(),
            "evidenceCount": len(usable),
            "baselineDate": baseline["date"] if baseline else None,
            "baselineId": baseline["id"] if baseline else None,
            "exercises": [],
            "omittedExercises": [],
            "imagePages": 1,
            "stale": False,
        }
        if not baseline:
            plan["notice"] = (
                "No named workout with exercise sets is available for this type."
            )
            plans.append(plan)
            continue
        age = (day - date.fromisoformat(baseline["date"])).days
        plan["stale"] = age > 28
        plan["notice"] = (
            "Build reps within the target range. When a load group reaches its rep ceiling in two comparable sessions, increase that load and reset its reps."
        )
        if age > 28:
            plan["notice"] = (
                f"Last session was {age} days ago. Historical targets are shown for review; automatic progression is paused."
            )
        groups = OrderedDict()
        for row in ordered(sets[baseline["id"]]):
            groups.setdefault(row["exercise"], []).append(row)
        for name, rows in groups.items():
            earlier = []
            for workout in usable[1:]:
                entries = ordered(
                    [s for s in sets[workout["id"]] if s["exercise"] == name]
                )
                if entries:
                    earlier.append((workout, entries))
            recent = earlier[0] if earlier else None
            proposed = [clean_set(r) for r in rows]
            rule = progression_rule(name, rows, data.get("progressionRules", {}))
            equipment = data.get("equipment", {})
            profile = equipment.get("profiles", {}).get(
                equipment.get("assignments", {}).get(name)
            )
            if profile:
                rule.update(
                    equipmentName=profile["name"],
                    availableLoads=profile["loads"],
                    stepSource="equipment",
                )
            status = "repeat"
            reason = "Only one session with this exercise in this workout type; repeat to establish a comparison."
            if not valid(rows):
                status = "review"
                reason = "Check missing values, zero loads or set notes before choosing targets."
            elif re.search(r"\bassisted\b|\bassistance\b", name, re.I) or data.get(
                "volumeSettings", {}
            ).get("exercises", {}).get(name, {}).get("assistance"):
                status = "review"
                reason = "Recorded kg represent assistance: increasing this setting reduces resistance. Choose assistance manually; automatic load progression is paused."
            elif name.casefold() not in REVIEW_EXERCISES and any(
                r["weight"] == 0 for r in rows
            ):
                status = "review"
                reason = "A zero external load is recorded for this exercise; confirm it before progressing."
            elif name.casefold() in REVIEW_EXERCISES and any(
                r["weight"] > 0 for r in rows
            ):
                status = "review"
                reason = "Confirm the exercise and load meaning (added weight, assistance or bodyweight) before progressing."
            elif profile and any(
                not any(abs(r["weight"] - load) < 1e-6 for load in profile["loads"])
                for r in rows
            ):
                status = "review"
                reason = "A historical load is unavailable in the assigned equipment profile. Choose an available load before progressing."
            elif age > 28:
                status = "review"
                reason = (
                    "Older session: review these historical loads before returning."
                )
            elif recent:
                workout, previous = recent
                gap = (
                    date.fromisoformat(baseline["date"])
                    - date.fromisoformat(workout["date"])
                ).days
                if gap > 42:
                    reason = "A long gap separates the comparable sessions; repeat before progressing."
                elif not matching(rows, previous):
                    reason = "Loads, set count or data quality changed since the previous session; repeat this structure first."
                else:
                    loads = set(r["weight"] for r in rows)
                    dropped = any(
                        total([r for r in rows if r["weight"] == load])
                        < total([r for r in previous if r["weight"] == load])
                        for load in loads
                    )
                    if dropped:
                        reason = "Reps fell in at least one matching-load group; repeat before adding more."
                    else:
                        ready = [
                            load
                            for load in sorted(loads)
                            if load > 0
                            and all(
                                r["reps"] >= rule["repMax"]
                                for r in [*rows, *previous]
                                if r["weight"] == load
                            )
                        ]
                        next_loads = {
                            load: (
                                next(
                                    (
                                        v
                                        for v in sorted(profile["loads"])
                                        if v > load + 1e-6
                                    ),
                                    None,
                                )
                                if profile
                                else round(load + rule["weightStep"], 4)
                            )
                            for load in ready
                        }
                        safe = [
                            load
                            for load in ready
                            if next_loads[load] is not None
                            and (next_loads[load] - load) / load <= 0.10 + 1e-9
                        ]
                        if safe:
                            for target in proposed:
                                if target["weight"] in safe:
                                    target["weight"] = next_loads[target["weight"]]
                                    target["reps"] = rule["repMin"]
                            status = "weight_progress"
                            changed = ", ".join(
                                f"{load:g} → {next_loads[load]:g} kg" for load in safe
                            )
                            reason = f"All sets at each eligible load reached {rule['repMax']}+ reps in both comparable sessions. Increase {changed}; target {rule['repMin']} reps on those sets. Other loads stay unchanged."
                            if profile:
                                reason += f" Available loads from {profile['name']}."
                            if rule["stepSource"] == "default":
                                reason += " Default increment: confirm it matches your equipment."
                        elif ready:
                            status = "review"
                            reason = (
                                "No available increase within 10% of the ready load in this equipment profile. Repeat or review your equipment."
                                if profile
                                else "The configured weight increment exceeds 10% of the ready load. Set a smaller equipment increment before progressing."
                            )
                        else:
                            candidates = [
                                i
                                for i, r in enumerate(rows)
                                if r["reps"] < rule["repMax"]
                            ]
                            if candidates:
                                index = min(
                                    candidates, key=lambda i: (rows[i]["reps"], -i)
                                )
                                proposed[index]["reps"] += 1
                                status = "progress"
                                reason = f"Matching loads held or improved since {workout['date']}. Aim for one extra rep in set {index + 1}, up to the {rule['repMax']}-rep ceiling; loads stay unchanged."
                            else:
                                reason = f"Rep ceiling reached. Repeat until each load group achieves {rule['repMax']}+ reps in two comparable sessions before increasing weight."
                                if all(r["weight"] == 0 for r in rows):
                                    reason = "Bodyweight rep ceiling reached; added load is not introduced automatically."
            plan["exercises"].append(
                {
                    "name": name,
                    "rule": rule,
                    "status": status,
                    "reason": reason,
                    "previous": [clean_set(r) for r in rows],
                    "proposed": proposed,
                    "comparisonDate": recent[0]["date"] if recent else None,
                    "history": [
                        {
                            "id": w["id"],
                            "date": w["date"],
                            "sets": [clean_set(r) for r in rr],
                        }
                        for w, rr in [(baseline, rows), *earlier[:2]]
                    ],
                }
            )
        earlier_names = OrderedDict()
        for w in usable[1:3]:
            for r in ordered(sets[w["id"]]):
                if r["exercise"] not in groups:
                    earlier_names.setdefault(r["exercise"], w["date"])
        plan["omittedExercises"] = [
            {"name": n, "lastDate": d} for n, d in earlier_names.items()
        ]
        plans.append(plan)
    return plans
