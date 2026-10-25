"""Read approved food entries alongside daily Garmin measurements."""

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from reptrace.training.metrics import known, total


def nutrition_history(data, today, from_date=None, to_date=None, limit=14):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 180:
        raise ValueError("Limit must be 1–180 recorded days")
    zone = ZoneInfo(data.get("timezone") or "Europe/Kyiv")
    grouped = defaultdict(list)
    for entry in data.get("foodLog", []):
        stamp = datetime.fromisoformat(entry["time"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("Food timestamps must include a timezone")
        day = stamp.astimezone(zone).date().isoformat()
        if (not from_date or day >= from_date) and (not to_date or day <= to_date):
            grouped[day].append(entry)
    recovery = {row["date"]: row for row in data.get("recovery", [])}
    weights = sorted(
        (day, row)
        for day, row in recovery.items()
        if day <= today.isoformat()
        and known(row.get("bodyWeightKg"))
        and row["bodyWeightKg"] > 0
    )

    def weight_at(day):
        matches = [(d, row) for d, row in weights if d <= day]
        if not matches:
            return None
        d, row = matches[-1]
        return {
            "date": d,
            "kg": row["bodyWeightKg"],
            "time": row.get("bodyWeightTime"),
            "source": row.get("bodyWeightSource"),
        }

    days = []
    for day in sorted(grouped, reverse=True)[:limit]:
        entries = sorted(grouped[day], key=lambda e: e["time"])
        amounts = {
            key: total(e.get(key) for e in entries)
            if all(known(e.get(key)) for e in entries)
            else None
            for key in ("calories", "protein_g", "carbs_g", "fat_g")
        }
        weight = weight_at(day)
        recorded = recovery.get(day, {})
        burn = {
            key: recorded.get(key)
            for key in ("activeCalories", "restingCalories", "totalCalories")
        }
        if not known(burn["totalCalories"]):
            burn["totalCalories"] = (
                burn["activeCalories"] + burn["restingCalories"]
                if all(known(burn[k]) for k in ("activeCalories", "restingCalories"))
                else None
            )
        days.append(
            {
                "date": day,
                "entryCount": len(entries),
                "totals": amounts,
                "bodyWeight": weight,
                "proteinGramsPerKg": round(amounts["protein_g"] / weight["kg"], 3)
                if weight and known(amounts["protein_g"])
                else None,
                "garminCalories": burn,
                "intakeMinusBurnKcal": round(
                    amounts["calories"] - burn["totalCalories"], 2
                )
                if known(amounts["calories"]) and known(burn["totalCalories"])
                else None,
                "isToday": day == today.isoformat(),
                "entries": [
                    {
                        k: e.get(k)
                        for k in (
                            "id",
                            "time",
                            "name",
                            "calories",
                            "protein_g",
                            "carbs_g",
                            "fat_g",
                            "note",
                        )
                    }
                    for e in entries[:20]
                ],
                "entriesTruncated": len(entries) > 20,
            }
        )
    return {
        "timezone": str(zone),
        "foodLogAvailable": "foodLog" in data,
        "matchingDays": len(grouped),
        "truncated": len(grouped) > limit,
        "days": days,
        "latestBodyWeight": weight_at(today.isoformat()),
        "averagesPerLoggedDay": {
            key: total(d["totals"][key] for d in days) / len(days)
            if days and all(known(d["totals"][key]) for d in days)
            else None
            for key in ("calories", "protein_g", "carbs_g", "fat_g")
        },
        "note": "Approved food estimates only; an entry does not prove the whole day was logged. "
        "Unlogged days are missing, not zero. Today may be incomplete. Daily totals include all entries, "
        "even if entry details are truncated. Averages cover returned logged days only. "
        "Weight is the latest measurement on or before each day; check its date for staleness. "
        "Garmin burn is an estimate; intake minus burn is not a measured energy deficit.",
    }
