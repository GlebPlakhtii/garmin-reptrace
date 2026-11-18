"""Explainable next-session targets from named workouts; never writes workout data."""

from collections import Counter, OrderedDict
from copy import deepcopy
from datetime import date, datetime, timezone
import math
import re

from reptrace.training.metrics import is_assisted

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


def retained_structure(usable, sets):
    """Keep a recent structure when the latest session only leaves sets out.

    Compare adjacent actual sessions, not previous proposals: repeated reductions
    then become the new structure, without accumulating old exercises forever.
    """
    if len(usable) < 2:
        return None
    latest, previous = usable[:2]
    gap = (
        date.fromisoformat(latest["date"]) - date.fromisoformat(previous["date"])
    ).days
    current_counts = Counter(r["exercise"] for r in sets[latest["id"]])
    previous_counts = Counter(r["exercise"] for r in sets[previous["id"]])
    if gap <= 42 and current_counts < previous_counts:
        return previous
    return None


def share_exercise_loads(plans):
    """Use one exercise's latest load proposal across the four named routines."""
    groups = {}
    for plan in plans:
        if plan["type"] in TYPES:
            for exercise in plan["exercises"]:
                groups.setdefault(exercise["name"], []).append((plan, exercise))

    def source_key(item):
        plan, exercise = item
        performed = plan.get("lastPerformed", {}).get(exercise["name"], {})
        timestamp = performed.get("time") or performed.get("date") or plan.get("baselineTime") or plan.get("baselineDate")
        instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00")) if timestamp else datetime.min.replace(tzinfo=timezone.utc)
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        manual = exercise.get("manualSavedAt", 0) if exercise.get("status") == "saved" else 0
        original = exercise.get("manualSourceType", plan["type"]) == plan["type"]
        return bool(manual), manual, original if manual else False, instant

    for name, entries in groups.items():
        if len(entries) < 2:
            continue
        source_plan, source = max(entries, key=source_key)
        targets = deepcopy(source["proposed"])
        if not targets:
            continue
        loads = [(s.get("weight"), s.get("unit", "kg")) for s in targets]
        uniform = len(set(loads)) == 1
        manual = source.get("status") == "saved" and bool(source.get("manualSavedAt"))
        if manual:
            source.setdefault("manualSourceType", source_plan["type"])
        for plan, exercise in entries:
            exercise["sharedLoad"] = {"sourceType": source_plan["type"], "sourceDate": source_plan.get("baselineDate"), "manual": manual}
            if exercise is source:
                continue
            if not uniform and len(exercise["proposed"]) != len(targets):
                exercise["status"] = "review"
                exercise["reason"] = "Shared exercise has different set counts and multiple loads. Review top/back-off set mapping before choosing a common load."
                continue
            changed = False
            for index, target in enumerate(exercise["proposed"]):
                load, unit = loads[0 if uniform else index]
                prior = target.get("weight")
                if (prior, target.get("unit", "kg")) != (load, unit):
                    changed = True
                    target["weight"] = load
                    if unit != "kg" or "unit" in target:
                        target["unit"] = unit
                    # Do not carry high reps at the old load into a heavier target.
                    if known(prior) and known(load) and load > prior and unit == "kg":
                        target["reps"] = min(target["reps"], exercise.get("rule", {}).get("repMin", 8)) if known(target.get("reps")) else None
            if changed or manual:
                original_reason = exercise.setdefault("reasonBeforeSharedLoad", exercise.get("reason", ""))
                exercise["reason"] = f"Same exercise, shared load from {source_plan['name']}. Set count stays specific to this routine. "
                if manual:
                    exercise["status"] = "saved"
                    exercise["manualSavedAt"] = source["manualSavedAt"]
                    exercise["manualSourceType"] = source["manualSourceType"]
                    exercise["reason"] += "Your manual load applies once, until this exercise is next completed in any named routine."
                    plan["source"] = "manual_override"
                    plan["notice"] = "Your one-time manual exercise load is shared across routines. Other exercises use normal progression suggestions."
                elif source.get("status") == "review" or exercise.get("status") == "review" or any(load is None for load, _ in loads):
                    exercise["status"] = "review"
                    exercise["reason"] += source.get("reason", original_reason)
                else:
                    exercise["status"] = "shared_load"
    return plans


def build_next_sessions(data, as_of=None, baseline_id=None):
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
    types = TYPES
    selected = None
    if baseline_id is not None:
        selected = next((w for w in sessions if w["id"] == baseline_id), None)
        if selected is None:
            raise ValueError(
                "Choose an existing completed session, not a future workout"
            )
        types = {"session": selected["name"]}
        sessions = sessions[sessions.index(selected) :]
    plans = []
    shared_performed = {}
    if not selected:
        for session in sessions:
            if workout_type(session["name"]):
                for entry in sets.get(session["id"], []):
                    shared_performed.setdefault(entry["exercise"], {
                        "date": session["date"],
                        "time": session.get("time") if not session.get("dateOnly") else None,
                    })
    for key, label in types.items():
        if selected:
            # An explicit baseline may have any name; generic names do not establish
            # a repeatable program and therefore supply no progression evidence.
            generic = label.strip().casefold() in (
                "",
                "strength",
                "strength training",
                "workout",
            )
            history = (
                [selected]
                if generic
                else [
                    w
                    for w in sessions
                    if w["name"].strip().casefold() == label.strip().casefold()
                ]
            )
        else:
            history = [w for w in sessions if workout_type(w["name"]) == key]
        usable = [w for w in history if sets.get(w["id"])]
        if selected and (not usable or usable[0]["id"] != selected["id"]):
            raise ValueError("The selected session has no identified exercise sets")
        baseline = usable[0] if usable else None
        plan = {
            "type": key,
            "name": label,
            "generatedDate": day.isoformat(),
            "evidenceCount": len(usable),
            "baselineDate": baseline["date"] if baseline else None,
            "baselineTime": baseline.get("time") if baseline and not baseline.get("dateOnly") else None,
            "baselineId": baseline["id"] if baseline else None,
            "exercises": [],
            "omittedExercises": [],
            "imagePages": 1,
            "stale": False,
            "lastPerformed": {},
        }
        if not selected:
            plan["sharedLastPerformed"] = shared_performed
        for session in usable:
            for entry in sets[session["id"]]:
                plan["lastPerformed"].setdefault(entry["exercise"], {
                    "date": session["date"],
                    "time": session.get("time") if not session.get("dateOnly") else None,
                })
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
        # Explicitly chosen sessions remain exact templates for one-off adaptations.
        structure = retained_structure(usable, sets) if not selected else None
        template = OrderedDict()
        for row in ordered(sets[(structure or baseline)["id"]]):
            template.setdefault(row["exercise"], []).append(row)
        if structure:
            plan["retainedStructureDate"] = structure["date"]
            plan["notice"] += (
                f" The latest session has fewer sets; the exercise order and set counts from {structure['date']} are retained."
                " A single shortened session does not replace the plan. Affected exercises repeat their earlier targets without progression."
            )
        for name, template_rows in template.items():
            rows = groups.get(name, [])
            restored = len(rows) < len(template_rows)
            target_rows = template_rows if restored else rows
            earlier = []
            for workout in usable[1:]:
                entries = ordered(
                    [s for s in sets[workout["id"]] if s["exercise"] == name]
                )
                if entries:
                    earlier.append((workout, entries))
            recent = earlier[0] if earlier else None
            proposed = [clean_set(r) for r in target_rows]
            rule = progression_rule(name, target_rows, data.get("progressionRules", {}))
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
            if not valid(target_rows) or (rows and not valid(rows)):
                status = "review"
                reason = "Check missing values, zero loads or set notes before choosing targets."
            elif is_assisted(name, data.get("volumeSettings", {})):
                status = "review"
                reason = "Recorded kg represent assistance: increasing this setting reduces resistance. Choose assistance manually; automatic load progression is paused."
            elif name.casefold() not in REVIEW_EXERCISES and any(
                r["weight"] == 0 for r in target_rows
            ):
                status = "review"
                reason = "A zero external load is recorded for this exercise; confirm it before progressing."
            elif name.casefold() in REVIEW_EXERCISES and any(
                r["weight"] > 0 for r in target_rows
            ):
                status = "review"
                reason = "Confirm the exercise and load meaning (added weight, assistance or bodyweight) before progressing."
            elif profile and any(
                not any(abs(r["weight"] - load) < 1e-6 for load in profile["loads"])
                for r in target_rows
            ):
                status = "review"
                reason = "A historical load is unavailable in the assigned equipment profile. Choose an available load before progressing."
            elif age > 28 or (
                restored and (day - date.fromisoformat(structure["date"])).days > 28
            ):
                status = "review"
                reason = (
                    "Older session: review these historical loads before returning."
                )
            elif restored:
                reason = "Repeat the earlier targets; fewer recorded sets are not evidence for progression."
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
            if restored:
                reason = (
                    f"Only {len(rows)} of {len(template_rows)} sets were recorded in the latest session. "
                    f"Keep all {len(template_rows)} sets from {structure['date']}; a one-time omission does not change the plan. "
                    + reason
                )
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
                            "time": w.get("time") if not w.get("dateOnly") else None,
                            "sets": [clean_set(r) for r in rr],
                        }
                        for w, rr in [(baseline, rows), *earlier[:2]]
                    ],
                }
            )
        earlier_names = OrderedDict()
        for w in usable[1:3]:
            for r in ordered(sets[w["id"]]):
                if r["exercise"] not in template:
                    earlier_names.setdefault(r["exercise"], w["date"])
        plan["omittedExercises"] = [
            {"name": n, "lastDate": d} for n, d in earlier_names.items()
        ]
        plans.append(plan)
    return share_exercise_loads(plans) if not selected else plans
