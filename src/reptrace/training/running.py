"""Garmin running measurements in explicit display units, without account metadata."""

from datetime import datetime, timezone
import json
import math
from pathlib import Path

METRICS = json.loads(Path(__file__).with_name("running_metrics.json").read_text())


def numeric(value, signed=False):
    if isinstance(value, bool) or value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and (signed or value >= 0) else None


def pace(speed):
    speed = numeric(speed)
    return 1000 / speed if speed else None


def summary_metrics(raw):
    result = {}
    for spec in METRICS:
        if "source" in spec:
            value = numeric(raw.get(spec["source"]), spec.get("signed", False))
            result[spec["key"]] = (
                value * spec.get("scale", 1) if value is not None else None
            )
    result["averagePace"] = pace(raw.get("averageSpeed"))
    result["bestPace"] = pace(raw.get("maxSpeed"))
    distance, moving = result.get("distanceKm"), result.get("movingSeconds")
    result["movingPace"] = moving / distance if distance and moving else None
    benefit = raw.get("trainingEffectLabel")
    result["primaryBenefit"] = (
        str(benefit).replace("_", " ").title() if benefit else None
    )
    return result


# Detail response values already use the descriptor's unit. Its factor is NOT a multiplier.
STREAMS = {
    "sumDuration": ("seconds", 1),
    "sumElapsedDuration": ("elapsedSeconds", 1),
    "sumDistance": ("distanceKm", 0.001),
    "directSpeed": ("speed", 1),
    "directHeartRate": ("heartRate", 1),
    "directDoubleCadence": ("cadence", 1),
    "directPower": ("power", 1),
    "directElevation": ("elevation", 1),
    "directAltitude": ("elevation", 1),
    "directTemperature": ("temperature", 1),
    "directGroundContactTime": ("groundContactMs", 1),
    "directVerticalOscillation": ("verticalOscillationCm", 1),
    "directVerticalRatio": ("verticalRatio", 1),
    "directStrideLength": ("strideLengthM", 0.01),
    "directAvailableStamina": ("stamina", 1),
    "directPotentialStamina": ("potentialStamina", 1),
    "directBodyBattery": ("bodyBattery", 1),
    "directLatitude": ("latitude", 1),
    "directLongitude": ("longitude", 1),
}


def normalize_detail(base, activity, details=None, splits=None, zones=None):
    activity = activity or {}
    if str(activity.get("activityId")) != str(base["id"]):
        raise ValueError("Garmin returned a different activity")
    kind = (activity.get("activityTypeDTO") or {}).get("typeKey", base.get("type", ""))
    if kind != "running" and not kind.endswith("_running"):
        raise ValueError("Choose a running activity")
    raw = activity.get("summaryDTO") or {}
    summary = {
        **base,
        **{k: v for k, v in summary_metrics(raw).items() if v is not None},
    }
    summary["name"] = str(activity.get("activityName") or base.get("name") or "Run")
    samples = []
    details = details or {}
    descriptors = {
        d["key"]: d["metricsIndex"]
        for d in details.get("metricDescriptors", [])
        if isinstance(d.get("metricsIndex"), int) and d["metricsIndex"] >= 0
    }
    for row in details.get("activityDetailMetrics", []):
        values = row.get("metrics") or []

        def get(key):
            index = descriptors.get(key)
            return (
                numeric(values[index], True)
                if index is not None and index < len(values)
                else None
            )

        sample = {}
        for source, (target, scale) in STREAMS.items():
            value = get(source)
            if value is not None and (
                value >= 0
                or target in ("elevation", "temperature", "latitude", "longitude")
            ):
                sample[target] = value * scale
        if "cadence" not in sample and numeric(get("directRunCadence")) is not None:
            sample["cadence"] = 2 * (
                get("directRunCadence") + (numeric(get("directFractionalCadence")) or 0)
            )
        sample["pace"] = pace(sample.get("speed"))
        if "seconds" not in sample:
            sample["seconds"] = sample.get("elapsedSeconds")
        if sample.get("seconds") is not None:
            samples.append(sample)
    samples.sort(key=lambda r: r["seconds"])
    laps = []
    for index, lap in enumerate((splits or {}).get("lapDTOs", [])):
        laps.append(
            {
                "index": int(lap.get("lapIndex") or index + 1),
                "intensity": str(lap.get("intensityType") or "Lap")
                .replace("_", " ")
                .title(),
                **summary_metrics(lap),
            }
        )
    normalized_zones = []
    for zone in zones or []:
        number = numeric(zone.get("zoneNumber"))
        seconds = numeric(zone.get("secsInZone"))
        if number is not None and 1 <= number <= 5 and seconds is not None:
            normalized_zones.append(
                {
                    "zone": int(number),
                    "seconds": seconds,
                    "lowBpm": numeric(zone.get("zoneLowBoundary")),
                }
            )
    if not normalized_zones:
        normalized_zones = [
            {"zone": n, "seconds": numeric(base.get(f"hrZone{n}")), "lowBpm": None}
            for n in range(1, 6)
            if numeric(base.get(f"hrZone{n}")) is not None
        ]
    return {
        "summary": summary,
        "samples": samples,
        "laps": laps,
        "zones": sorted(normalized_zones, key=lambda r: r["zone"]),
        "metricCatalog": METRICS,
        "notes": detail_notes(summary, samples, laps),
        "sampleCount": len(samples),
        "sourceSampleCount": details.get("measurementCount"),
        "syncedAt": datetime.now(timezone.utc).isoformat(),
        "source": "Garmin Connect",
    }


def detail_notes(summary, samples, laps):
    notes = []
    sample_distances = [
        s["distanceKm"] for s in samples if s.get("distanceKm") is not None
    ]
    if (
        sample_distances
        and summary.get("distanceKm")
        and abs(max(sample_distances) - summary["distanceKm"])
        > max(0.1, summary["distanceKm"] * 0.02)
    ):
        notes.append(
            "Sample distance differs from the activity summary. A treadmill calibration or activity edit may explain this. Charts use original sample distance; totals use the Garmin summary."
        )
    if not samples:
        notes.append("Garmin has no chart samples for this activity.")
    if not laps:
        notes.append("No Garmin lap splits are available.")
    return notes


def running_totals(runs):
    def total(key):
        values = [r[key] for r in runs if numeric(r.get(key)) is not None]
        return sum(values) if values else None

    paired = [r for r in runs if r.get("distanceKm", 0) and r.get("movingSeconds", 0)]
    distance = sum(r["distanceKm"] for r in paired)
    return {
        "count": len(runs),
        "distanceKm": total("distanceKm"),
        "movingSeconds": total("movingSeconds"),
        "calories": total("calories"),
        "elevationGain": total("elevationGain"),
        "movingPace": sum(r["movingSeconds"] for r in paired) / distance
        if distance
        else None,
        "paceRunCount": len(paired),
        "coverage": {
            key: sum(numeric(r.get(key)) is not None for r in runs)
            for key in ("distanceKm", "movingSeconds", "calories", "elevationGain")
        },
    }


def compare_runs(left, right):
    return [
        {
            "key": spec["key"],
            "label": spec["label"],
            "unit": spec["unit"],
            "left": left.get(spec["key"]),
            "right": right.get(spec["key"]),
            "change": right[spec["key"]] - left[spec["key"]]
            if numeric(left.get(spec["key"]), True) is not None
            and numeric(right.get(spec["key"]), True) is not None
            else None,
        }
        for spec in METRICS
        if left.get(spec["key"]) is not None or right.get(spec["key"]) is not None
    ]
