"""Compare a Garmin strength template with a completed session, set by set."""

from collections import defaultdict
import math


def number(value):
    return (
        value
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        else None
    )


def compare_plan(facts, template):
    """Compare per-exercise set order; never infer that an unmatched set was performed."""
    if not template or not template.get("plannedSets"):
        return {
            "status": "unavailable",
            "reason": (template or {}).get(
                "reason", "No matching Garmin workout template was available."
            ),
        }
    planned = defaultdict(list)
    actual = defaultdict(list)
    labels = {}
    for row in template["plannedSets"]:
        name = str(row["exercise"]).strip()
        key = name.casefold()
        planned[key].append(row)
        labels.setdefault(key, name)
    for exercise in facts["exercises"]:
        name = exercise["exercise"]
        key = name.casefold()
        actual[key].extend(exercise["sets"])
        labels.setdefault(key, name)
    rows = []
    counts = {"matched": 0, "changed": 0, "missing": 0, "extra": 0, "unknown": 0}
    for key in list(planned) + [key for key in actual if key not in planned]:
        before = planned[key]
        after = actual[key]
        for index in range(max(len(before), len(after))):
            p = before[index] if index < len(before) else None
            a = after[index] if index < len(after) else None
            if p is None:
                status = "extra"
            elif a is None:
                status = "missing"
            elif (
                number(p.get("reps")) is None
                or number(a.get("reps")) is None
                or number(p.get("weight")) is None
                or number(a.get("weight")) is None
            ):
                status = "unknown"
            elif number(p["reps"]) == number(a["reps"]) and number(
                p["weight"]
            ) == number(a["weight"]):
                status = "matched"
            else:
                status = "changed"
            counts[status] += 1
            rows.append(
                {
                    "exercise": labels[key],
                    "set": index + 1,
                    "plannedWeight": number(p.get("weight")) if p else None,
                    "plannedReps": number(p.get("reps")) if p else None,
                    "actualWeight": number(a.get("weight")) if a else None,
                    "actualReps": number(a.get("reps")) if a else None,
                    "status": status,
                }
            )
    return {
        "status": "available",
        "source": template.get("source", "current_template"),
        "asOf": template.get("asOf"),
        "name": template.get("name", ""),
        "counts": counts,
        "rows": rows,
        "note": "Sets are paired by position within each exercise. A skipped middle set can shift later pairs. Unidentified recorded sets are excluded. Recorded kilograms are compared as entered, without equipment conversion. "
        + (
            "This app saved the template before the session; external Garmin edits may not be reflected."
            if template.get("source") == "app_snapshot"
            else "This is the current Garmin template, retrieved after the session; it may differ from the workout shown on your watch then."
        ),
    }
