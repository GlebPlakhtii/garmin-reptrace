"""Synthetic Garmin-shaped running responses for the isolated showcase."""

import math
from reptrace.training.running import normalize_detail


def demo_detail(run):
    distance = run.get("distanceKm") or 5
    duration = run.get("movingSeconds") or 1800
    trail = run.get("type") == "trail_running"
    raw = {
        "distance": distance * 1000,
        "duration": duration,
        "movingDuration": duration,
        "elapsedDuration": duration + 60,
        "averageSpeed": distance * 1000 / duration,
        "maxSpeed": 4.3,
        "averageHR": run.get("averageHR") or 145,
        "maxHR": 172,
        "minHR": 92,
        "averageRunCadence": 172,
        "maxRunCadence": 190,
        "averagePower": 255,
        "maxPower": 370,
        "normalizedPower": 266,
        "groundContactTime": 248,
        "strideLength": 106,
        "verticalOscillation": 8.1,
        "verticalRatio": 7.6,
        "trainingEffect": 3.4,
        "anaerobicTrainingEffect": 0.8,
        "activityTrainingLoad": 97,
        "trainingEffectLabel": "AEROBIC_BASE",
        "waterEstimated": 460,
        "differenceBodyBattery": -9,
        "steps": 5200,
        "beginPotentialStamina": 98,
        "endPotentialStamina": 72,
        "minAvailableStamina": 68,
        "calories": run.get("calories") or 360,
        "bmrCalories": 40,
        "moderateIntensityMinutes": 7,
        "vigorousIntensityMinutes": 23,
    }
    if trail:
        raw.update(
            elevationGain=125,
            elevationLoss=119,
            minElevation=110,
            maxElevation=170,
            averageTemperature=14,
        )
    keys = [
        "sumDuration",
        "sumDistance",
        "directSpeed",
        "directHeartRate",
        "directDoubleCadence",
        "directPower",
        "directGroundContactTime",
        "directStrideLength",
        "directVerticalOscillation",
        "directVerticalRatio",
        "directAvailableStamina",
        "directPotentialStamina",
    ]
    if trail:
        keys += ["directElevation", "directLatitude", "directLongitude"]
    points = []
    for i in range(301):
        f = i / 300
        wave = math.sin(i / 17)
        values = [
            duration * f,
            distance * 1000 * f,
            distance * 1000 / duration * (1 + 0.15 * wave),
            120 + 35 * f + 8 * wave,
            172 + 5 * wave,
            255 + 30 * wave,
            248 - 12 * wave,
            106 + 7 * wave,
            8.1 + 0.5 * wave,
            7.6 + 0.3 * wave,
            98 - 30 * f,
            98 - 26 * f,
        ]
        if trail:
            values += [
                130 + 20 * math.sin(i / 45),
                50.4 + 0.01 * math.sin(f * math.pi * 2),
                30.5 + 0.016 * math.cos(f * math.pi * 2),
            ]
        if 95 < i < 101:
            values[3] = None  # A genuine chart gap, never a zero heart rate.
        points.append({"metrics": values})
    lap_count = max(1, math.ceil(distance))
    splits = {
        "lapDTOs": [
            {
                "lapIndex": i + 1,
                "intensityType": "ACTIVE",
                **raw,
                "distance": min(1, distance - i) * 1000,
                "duration": duration / distance * min(1, distance - i),
                "movingDuration": duration / distance * min(1, distance - i),
                "averageHR": 140 + i * 2,
            }
            for i in range(lap_count)
        ]
    }
    activity = {
        "activityId": run["id"],
        "activityName": run["name"],
        "activityTypeDTO": {"typeKey": run["type"]},
        "summaryDTO": raw,
    }
    details = {
        "metricDescriptors": [
            {"key": key, "metricsIndex": i} for i, key in enumerate(keys)
        ],
        "activityDetailMetrics": points,
        "measurementCount": 301,
    }
    zones = [
        {
            "zoneNumber": i + 1,
            "secsInZone": duration * f,
            "zoneLowBoundary": 100 + i * 18,
        }
        for i, f in enumerate([0.05, 0.25, 0.5, 0.18, 0.02])
    ]
    return normalize_detail(run, activity, details, splits, zones)


class DemoRunningStore:
    def __init__(self):
        self.cache = {}

    def get(self, run, refresh=False):
        if run["id"] not in self.cache or refresh:
            self.cache[run["id"]] = demo_detail(run)
        return self.cache[run["id"]]

    def enrich(self, runs):
        return [
            {
                **run,
                **self.get(run)["summary"],
                "detailsSyncedAt": self.get(run)["syncedAt"],
            }
            for run in runs
        ]
