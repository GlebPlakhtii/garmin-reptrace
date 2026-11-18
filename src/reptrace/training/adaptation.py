"""Read-only, priority-preserving session adjustments shared by web and Telegram."""

from copy import deepcopy
from datetime import date, timedelta
from statistics import median

from reptrace.training.planning import build_next_sessions, known, ordered


def adapt_session(data, options, as_of=None):
    day = (
        as_of
        if isinstance(as_of, date)
        else date.fromisoformat(as_of)
        if as_of
        else date.today()
    )
    plans = build_next_sessions(data, day, baseline_id=options.get("session_id"))
    plan = deepcopy(
        next(
            (
                p
                for p in plans
                if options.get("session_id") or p["type"] == options.get("workout_type")
            ),
            None,
        )
    )
    if not plan or not plan["exercises"]:
        raise ValueError(
            "Choose a completed session or a workout type with recorded sets"
        )
    minutes = options.get("time_minutes")
    if minutes is not None and (type(minutes) is not int or not 10 <= minutes <= 180):
        raise ValueError("Time budget must be 10–180 minutes")
    notes = options.get("notes") or ""
    if not isinstance(notes, str) or len(notes) > 1200:
        raise ValueError("Notes must be at most 1200 characters")
    original = deepcopy(plan["exercises"])
    names = {e["name"] for e in original}

    def selection(key):
        values = options.get(key) or []
        if not isinstance(values, list) or any(
            not isinstance(n, str) or n not in names for n in values
        ):
            raise ValueError(
                "Choose " + key.replace("_", " ") + " from the selected session"
            )
        return set(values)

    priorities = selection("priority_exercises")
    unavailable = selection("unavailable_exercises")
    substitutions = options.get("substitutions") or []
    if not isinstance(substitutions, list):
        raise ValueError("Substitutions must be a list")
    replacements = {}
    for item in substitutions:
        if (
            not isinstance(item, dict)
            or item.get("from_exercise") not in names
            or not isinstance(item.get("to_exercise"), str)
        ):
            raise ValueError("Choose a substitution source from the selected session")
        if item["from_exercise"] in replacements:
            raise ValueError("Choose only one replacement per exercise")
        replacements[item["from_exercise"]] = item["to_exercise"]
    if (priorities & unavailable) - replacements.keys():
        raise ValueError(
            "A priority exercise is unavailable; supply a replacement or remove its priority"
        )
    rows = [r for r in data["sets"] if r["date"] <= day.isoformat()]
    changes, exercises, source_names = [], [], {}
    for e in plan["exercises"]:
        source = e["name"]
        replacement = replacements.get(source)
        if replacement:
            if replacement in unavailable or (
                replacement in names and replacement != source
            ):
                raise ValueError(
                    "Replacement is unavailable or already included in this session"
                )
            history = sorted(
                (r for r in rows if r["exercise"] == replacement),
                key=lambda r: (r["date"], r.get("time") or "", r.get("order") or 0),
                reverse=True,
            )
            if not history:
                raise ValueError(
                    "Substitutions need their own recorded targets; create a new Garmin workout to prescribe an unfamiliar exercise"
                )
            targets = [
                {"weight": r.get("weight"), "reps": r.get("reps")}
                for r in ordered(
                    [r for r in history if r["sessionId"] == history[0]["sessionId"]]
                )[: len(e["proposed"])]
            ]
            e.update(
                name=replacement,
                previous=deepcopy(targets),
                proposed=targets,
                status="review",
                reason="Uses this exercise's own last recorded sets; no equivalent load conversion.",
                history=[],
            )
            changes.append(source + " → " + replacement)
        elif source in unavailable:
            changes.append("Removed " + source + " (unavailable)")
            continue
        if e["name"] in source_names:
            raise ValueError("Two exercises cannot use the same replacement")
        e["priority"] = source in priorities
        source_names[e["name"]] = source
        exercises.append(e)
    if not exercises:
        raise ValueError(
            "Constraints remove every exercise; provide an available substitution"
        )

    baseline = next(w for w in data["workouts"] if w["id"] == plan["baselineId"])
    baseline_rows = [r for r in rows if r["sessionId"] == baseline["id"]]
    duration = baseline.get("duration")
    # Reserve preparation once; elapsed duration already contains rest/setup time.
    historical = (
        ((duration - 300) / len(baseline_rows))
        if known(duration) and duration > 300 and baseline_rows
        else None
    )
    fallback = historical if historical is not None and 30 <= historical <= 480 else 180
    timings = {}
    for e in exercises:
        sample = [r for r in baseline_rows if r["exercise"] == e["name"]]
        complete = sample and all(
            known(r.get("duration"))
            and r["duration"] > 0
            and known(r.get("rest"))
            and r["rest"] >= 0
            for r in sample
        )
        seconds = (
            median(r["duration"] + r["rest"] for r in sample) if complete else fallback
        )
        timings[e["name"]] = {
            "secondsPerSet": seconds,
            "source": "recorded set and rest durations"
            if complete
            else "recorded session duration"
            if historical == fallback
            else "assumed 3 minutes per set",
        }

    def seconds():
        return 300 + sum(
            len(e["proposed"]) * timings[e["name"]]["secondsPerSet"] for e in exercises
        )

    before_seconds = seconds()
    before_counts = {e["name"]: len(e["proposed"]) for e in exercises}
    if minutes:
        while seconds() > minutes * 60:
            candidate = next(
                (
                    e
                    for e in reversed(exercises)
                    if not e["priority"] and len(e["proposed"]) > 1
                ),
                None,
            )
            if candidate:
                candidate["proposed"].pop()
            else:
                candidate = next(
                    (e for e in reversed(exercises) if not e["priority"]), None
                )
                if candidate is None or len(exercises) == 1:
                    break
                exercises.remove(candidate)
        for name, count in before_counts.items():
            e = next((e for e in exercises if e["name"] == name), None)
            after = len(e["proposed"]) if e else 0
            if after != count:
                changes.append(
                    f"{'Reduced' if after else 'Removed'} {name}: {count} → {after} sets"
                )
                if e:
                    e["reason"] += " Set count reduced for today's time budget."
                    if e["proposed"] == e["previous"][:after]:
                        e["status"] = "repeat"
    exceeds = bool(minutes and seconds() > minutes * 60)
    if exceeds:
        changes.append(
            "Priority sets or the final remaining set exceed this budget. Allow more time or change priorities; protected sets were not cut."
        )
    week_start = (day - timedelta(days=day.weekday())).isoformat()
    impact = []
    for name in dict.fromkeys(
        [e["name"] for e in original] + [e["name"] for e in exercises]
    ):
        impact.append(
            {
                "exercise": name,
                "recordedThisWeek": sum(
                    r["exercise"] == name and r["date"] >= week_start for r in rows
                ),
                "originalPlannedSets": sum(
                    len(e["proposed"]) for e in original if e["name"] == name
                ),
                "adaptedPlannedSets": sum(
                    len(e["proposed"]) for e in exercises if e["name"] == name
                ),
            }
        )
    detail = "Estimate includes 5 minutes preparation; equipment waits and changed rest times can extend it. Recorded sets may include warm-ups. Weekly recorded sets and proposed sets are shown separately."
    plan.update(
        exercises=exercises,
        name=plan["name"] + " · adapted",
        adapted=True,
        adaptedNotes=notes,
        imagePages=1,
        notice="Separate proposal for today. " + " ".join(changes),
    )
    plan["adaptation"] = {
        "changes": changes,
        "timeBudget": minutes,
        "estimatedMinutes": round(seconds() / 60, 1),
        "originalEstimatedMinutes": round(before_seconds / 60, 1),
        "budgetExceeded": exceeds,
        "timing": timings,
        "setImpact": impact,
        "notes": notes,
        "limitations": detail,
    }
    return plan
