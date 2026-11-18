"""Synthetic Garmin responses and isolated SQLite cache; no live writes."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from reptrace.garmin.running import RunningStore
from reptrace.training.running import normalize_detail, running_totals, compare_runs

BASE = {
    "id": "123",
    "name": "Synthetic run",
    "type": "treadmill_running",
    "time": "2026-11-01T09:00:00Z",
    "date": "2026-11-01",
    "distanceKm": 5,
    "movingSeconds": 1500,
    "hrZone1": 60,
}
ACTIVITY = {
    "activityId": 123,
    "activityName": "<Run>",
    "activityTypeDTO": {"typeKey": "treadmill_running"},
    "userProfileId": "never-export",
    "summaryDTO": {
        "distance": 5000,
        "duration": 1600,
        "movingDuration": 1500,
        "elapsedDuration": 1800,
        "averageSpeed": 3.125,
        "maxSpeed": 4,
        "averageRunCadence": 174,
        "strideLength": 110,
        "verticalOscillation": 8.5,
        "groundContactTime": 245,
        "trainingEffect": 3.4,
        "anaerobicTrainingEffect": 0,
        "differenceBodyBattery": -8,
        "averagePower": 250,
    },
}
DETAILS = {
    "metricDescriptors": [
        {"key": key, "metricsIndex": i, "unit": {"factor": factor}}
        for i, (key, factor) in enumerate(
            [
                ("sumDuration", 1000),
                ("sumDistance", 100),
                ("directSpeed", 0.1),
                ("directRunCadence", 1),
                ("directFractionalCadence", 1),
                ("directHeartRate", 1),
                ("directStrideLength", 1),
                ("directVerticalOscillation", 1),
                ("directGroundContactTime", 1),
            ]
        )
    ],
    "activityDetailMetrics": [
        {"metrics": [0, 0, 3, 86, 0.5, 140, 105, 8, 245]},
        {"metrics": [1500, 4400, 0, 0, 0, None, None, 0, 0]},
    ],
    "measurementCount": 2000,
}
SPLITS = {
    "lapDTOs": [
        {
            "lapIndex": 1,
            "intensityType": "ACTIVE",
            "distance": 1000,
            "duration": 300,
            "movingDuration": 290,
            "averageSpeed": 1000 / 300,
            "averageHR": 145,
        }
    ]
}
ZONES = [
    {"zoneNumber": 1, "secsInZone": 60, "zoneLowBoundary": 100},
    {"zoneNumber": 2, "secsInZone": 0, "zoneLowBoundary": 120},
]


class RunningNormalizationTests(unittest.TestCase):
    def test_summary_units_time_bases_and_sensitive_fields(self):
        detail = normalize_detail(BASE, ACTIVITY, DETAILS, SPLITS, ZONES)
        s = detail["summary"]
        self.assertEqual(s["distanceKm"], 5)
        self.assertEqual(s["averagePace"], 320)
        self.assertEqual(s["movingPace"], 300)
        self.assertEqual(s["bestPace"], 250)
        self.assertEqual(s["strideLengthM"], 1.1)
        self.assertEqual(s["verticalOscillationCm"], 8.5)
        self.assertEqual(s["bodyBatteryChange"], -8)
        self.assertEqual(s["anaerobicEffect"], 0)
        self.assertNotIn("never-export", json.dumps(detail))
        self.assertEqual(detail["laps"][0]["averagePace"], 300)
        self.assertEqual(detail["zones"][1]["seconds"], 0)

    def test_descriptor_factors_are_not_applied_again_and_calibration_is_explicit(self):
        d = normalize_detail(BASE, ACTIVITY, DETAILS, SPLITS, ZONES)
        first, last = d["samples"]
        self.assertEqual(last["seconds"], 1500)
        self.assertEqual(last["distanceKm"], 4.4)
        self.assertAlmostEqual(first["pace"], 1000 / 3)
        self.assertEqual(first["cadence"], 173)
        self.assertEqual(first["strideLengthM"], 1.05)
        self.assertEqual(first["verticalOscillationCm"], 8)
        self.assertNotIn("heartRate", last)
        self.assertIsNone(last["pace"])
        self.assertTrue(any("calibration" in n for n in d["notes"]))
        self.assertEqual(d["sourceSampleCount"], 2000)

    def test_direct_double_cadence_takes_precedence_and_nonfinite_stays_absent(self):
        details = deepcopy(DETAILS)
        details["metricDescriptors"].append(
            {"key": "directDoubleCadence", "metricsIndex": 9}
        )
        details["activityDetailMetrics"][0]["metrics"].append(176)
        details["activityDetailMetrics"][1]["metrics"].append(float("nan"))
        d = normalize_detail(BASE, ACTIVITY, details)
        self.assertEqual(d["samples"][0]["cadence"], 176)
        json.dumps(d, allow_nan=False)
        self.assertEqual(d["zones"][0]["seconds"], 60)

    def test_wrong_activity_or_non_running_type_is_rejected(self):
        for changes in (
            {"activityId": 456},
            {"activityTypeDTO": {"typeKey": "cycling"}},
        ):
            with self.assertRaises(ValueError):
                normalize_detail(BASE, {**ACTIVITY, **changes})

    def test_totals_use_only_paired_records_and_comparison_is_right_minus_left(self):
        rows = [
            BASE,
            {**BASE, "id": "456", "distanceKm": 10, "movingSeconds": 3600},
            {**BASE, "id": "789", "distanceKm": 2, "movingSeconds": None},
        ]
        totals = running_totals(rows)
        self.assertEqual(totals["movingPace"], 340)
        self.assertEqual(totals["distanceKm"], 17)
        self.assertEqual(totals["coverage"]["movingSeconds"], 2)
        self.assertIsNone(totals["calories"])
        metrics = compare_runs(
            {"averagePace": 350, "cadence": None}, {"averagePace": 320, "cadence": 170}
        )
        self.assertEqual(metrics[0]["change"], -30)
        self.assertIsNone(metrics[1]["change"])


class RunningCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "running.sqlite"
        self.client = Mock()
        self.client.get_activity.return_value = deepcopy(ACTIVITY)
        self.client.get_activity_details.return_value = deepcopy(DETAILS)
        self.client.get_activity_splits.return_value = deepcopy(SPLITS)
        self.client.get_activity_hr_in_timezones.return_value = deepcopy(ZONES)
        self.factory = Mock(return_value=self.client)
        self.store = RunningStore(self.path, self.factory)

    def tearDown(self):
        self.directory.cleanup()

    def test_retry_readback_restart_and_enrichment_do_not_call_garmin_again(self):
        detail = self.store.get(BASE)
        self.assertEqual(self.store.get(BASE), detail)
        restarted = RunningStore(
            self.path, Mock(side_effect=AssertionError("remote read"))
        )
        self.assertEqual(restarted.get(BASE), detail)
        self.assertEqual(restarted.enrich([BASE])[0]["cadence"], 174)
        self.factory.assert_called_once()
        self.assertEqual(
            {call[0] for call in self.client.mock_calls},
            {
                "get_activity",
                "get_activity_details",
                "get_activity_splits",
                "get_activity_hr_in_timezones",
            },
        )
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_cached_metrics_keep_current_history_date_and_validated_link(self):
        old = self.store.get({**BASE, "url": "https://example.invalid/obsolete"})
        current = {**BASE, "date": "2026-11-02", "url": "https://connect.garmin.com/modern/activity/123"}
        for summary in (self.store.enrich([current])[0], self.store.get(current)["summary"]):
            self.assertEqual(summary["date"], current["date"])
            self.assertEqual(summary["url"], current["url"])
            self.assertEqual(summary["cadence"], old["summary"]["cadence"])
        without_link = {key: value for key, value in current.items() if key != "url"}
        self.assertNotIn("url", self.store.get(without_link)["summary"])
        self.factory.assert_called_once()

    def test_failed_and_partial_refresh_preserve_existing_details(self):
        old = self.store.get(BASE)
        self.client.get_activity_details.side_effect = RuntimeError("secret response")
        partial = self.store.get(BASE, refresh=True)
        self.assertEqual(partial["samples"], old["samples"])
        self.assertTrue(partial["partial"])
        self.assertTrue(any("calibration" in note for note in partial["notes"]))
        self.assertFalse(any("no chart samples" in note for note in partial["notes"]))
        self.client.get_activity.side_effect = RuntimeError("secret token")
        stale = self.store.get(BASE, refresh=True)
        self.assertTrue(stale["stale"])
        self.assertEqual(stale["samples"], old["samples"])
        self.assertNotIn("secret", json.dumps(stale))
        self.assertEqual(self.store.read("123")["samples"], old["samples"])

    def test_first_failure_is_retryable_without_caching_empty_success(self):
        self.client.get_activity.side_effect = RuntimeError("secret")
        self.assertIn("warning", self.store.get(BASE))
        self.assertIsNone(self.store.read("123"))
        self.client.get_activity.side_effect = None
        self.assertTrue(self.store.get(BASE)["samples"])

    def test_interrupted_transaction_rolls_back_and_retry_keeps_one_record(self):
        detail = self.store.get(BASE)
        with self.assertRaises(RuntimeError):
            with self.store.connect() as db:
                db.execute(
                    "UPDATE running_details SET payload=? WHERE id=?", ("{}", "123")
                )
                raise RuntimeError("interrupted write")
        self.assertEqual(self.store.read("123"), detail)
        self.store.get(BASE, refresh=True)
        with self.store.connect() as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM running_details").fetchone()[0], 1
            )

    def test_invalid_id_never_contacts_garmin(self):
        with self.assertRaises(ValueError):
            self.store.get({**BASE, "id": "123' OR true"})
        self.factory.assert_not_called()

    def test_concurrent_first_reads_import_once_and_return_same_snapshot(self):
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.store.get(BASE), range(2)))
        self.assertEqual(results[0], results[1])
        self.client.get_activity.assert_called_once_with("123")
