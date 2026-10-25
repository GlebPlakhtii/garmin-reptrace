from pathlib import Path
import gzip
import json
import sys
import unittest
from unittest.mock import Mock

from reptrace.web.server import build_payload, DataStore


class DashboardTests(unittest.TestCase):
    def records(self):
        sets = [
            {
                "time": "2025-05-01T09:00:00Z",
                "ActivityID": "manual-csv-session-1",
                "SetIndex": "1",
                "Exercise": "Pull Up",
                "source": "Manual CSV",
                "sourceDate": "2025-05-01",
                "weightKg": 16,
                "reps": None,
                "volumeKg": None,
                "timeAccuracy": "date-only",
                "sourceHash": "do-not-expose",
                "rawWeight": "16",
            }
        ]
        workouts = [
            {
                "time": "2025-05-01T09:00:00Z",
                "ActivityID": "manual-csv-session-1",
                "activityName": "Manual workout 1",
                "source": "Manual CSV",
                "timeAccuracy": "date-only",
            }
        ]
        return sets, workouts, []

    def test_midnight_workout_keeps_all_sets_on_workout_date_without_changing_times(
        self,
    ):
        sets, workouts, sleep = self.records()
        workouts[0]["time"] = "2026-10-20T20:50:00Z"  # 23:50 Kyiv
        sets[0].pop("sourceDate")
        sets[0]["time"] = "2026-10-20T21:10:00Z"  # next day locally
        data = build_payload(sets, workouts, sleep)
        self.assertEqual(data["sets"][0]["date"], "2026-10-20")
        self.assertEqual(data["sets"][0]["date"], data["workouts"][0]["date"])
        self.assertEqual(data["sets"][0]["time"], "2026-10-20T21:10:00Z")
        sets[0]["sourceDate"] = "2026-10-22"
        self.assertEqual(
            build_payload(sets, workouts, sleep)["sets"][0]["date"], "2026-10-22"
        )

    def test_missing_metrics_stay_missing_and_no_fake_workout_url(self):
        data = build_payload(*self.records())
        self.assertEqual(data["sets"][0]["weight"], 16)
        self.assertIsNone(data["sets"][0]["reps"])
        self.assertIsNone(data["sets"][0]["volume"])
        self.assertIsNone(data["workouts"][0]["duration"])
        self.assertEqual(data["workouts"][0]["url"], "")
        self.assertTrue(data["sets"][0]["dateOnly"])
        self.assertNotIn("sourceHash", json.dumps(data))

    def test_retired_rear_delt_alias_displays_historical_source_names(self):
        sets, workouts, sleep = self.records()
        manual = dict(
            sets[0],
            Exercise="Reverse Pec Deck Fly",
            originalExercise="Rear Delt Fly",
            exerciseCode="SEATED_REAR_LATERAL_RAISE",
        )
        garmin = dict(
            sets[0],
            SetIndex="2",
            Exercise="Reverse Pec Deck Fly",
            source="Garmin",
            exerciseCode="SEATED_REAR_LATERAL_RAISE",
        )
        explicit = dict(
            sets[0],
            SetIndex="3",
            Exercise="Reverse Pec Deck Fly",
            originalExercise="Reverse Pec Deck Fly",
        )
        data = build_payload([manual, garmin, explicit], workouts, sleep)
        self.assertEqual(
            [row["exercise"] for row in data["sets"]],
            ["Rear Delt Fly", "Seated Rear Lateral Raise", "Reverse Pec Deck Fly"],
        )

    def test_zero_is_preserved_and_nonfinite_values_are_null(self):
        sets, workouts, sleep = self.records()
        sets[0].update(weightKg=0, reps=0, volumeKg=0, estimated1RMKg=float("nan"))
        data = build_payload(sets, workouts, sleep)
        self.assertEqual(data["sets"][0]["weight"], 0)
        self.assertEqual(data["sets"][0]["reps"], 0)
        self.assertEqual(data["sets"][0]["volume"], 0)
        self.assertIsNone(data["sets"][0]["estimatedMax"])
        json.dumps(data, allow_nan=False)

    def test_assistance_estimates_are_omitted_from_api_and_export_view(self):
        rows = [
            {"exercise": "Assisted Pull Up", "estimatedMax": 50},
            {"exercise": "Custom helper", "estimatedMax": 40},
            {"exercise": "Bench", "estimatedMax": 100},
        ]
        result = {
            "sets": rows,
            "volumeSettings": {"exercises": {"Custom helper": {"assistance": True}}},
        }
        DataStore(None).attach_metadata(result)
        self.assertEqual([r["estimatedMax"] for r in rows], [None, None, 100])

    def test_cache_and_forced_refresh_query_same_read_only_data(self):
        client = Mock()
        sets, workouts, sleep = self.records()

        def query(q):
            self.assertTrue(q.startswith("SELECT "))
            if "StrengthSet" in q:
                return sets
            if "ActivitySummary" in q:
                return workouts
            return sleep

        factory = Mock(return_value=(client, query))
        store = DataStore(factory)
        one = store.get()
        two = store.get()
        self.assertIs(one, two)
        factory.assert_called_once()
        self.assertEqual(gzip.decompress(one[2]), one[1])
        self.assertEqual(json.loads(one[1])["sets"][0]["source"], "manual")
        store.get(force=True)
        self.assertEqual(factory.call_count, 2)
        self.assertEqual(client.close.call_count, 2)

    def test_database_failure_closes_client_without_caching_partial_data(self):
        client = Mock()
        query = Mock(side_effect=RuntimeError("offline"))
        store = DataStore(lambda: (client, query))
        with self.assertRaises(RuntimeError):
            store.get()
        self.assertIsNone(store.cached)
        client.close.assert_called_once()

    def test_manual_overlay_keeps_garmin_workout_metadata(self):
        sets, workouts, sleep = self.records()
        sets[0].update(ActivityID="123", source="Manual CSV")
        workouts[0].update(
            ActivityID="123",
            source="Garmin",
            elapsedDuration=3600,
            averageHR=122,
            activityUrl="https://connect.garmin.com/modern/activity/123",
        )
        data = build_payload(sets, workouts, sleep)
        self.assertEqual(data["sets"][0]["sessionId"], data["workouts"][0]["id"])
        self.assertEqual(data["workouts"][0]["duration"], 3600)
        self.assertEqual(data["workouts"][0]["averageHR"], 122)
        self.assertEqual(data["sets"][0]["source"], "manual")

    def test_recovery_converts_sleep_seconds_and_prefers_daily_resting_hr(self):
        sleep = [
            {
                "time": "2026-10-21T00:00:00Z",
                "sleepTimeSeconds": 28080,
                "avgOvernightHrv": 51,
                "restingHeartRate": 48,
                "sleepScore": 77,
                "deepSleepSeconds": 6000,
                "lightSleepSeconds": 16000,
                "remSleepSeconds": 6080,
                "awakeSleepSeconds": 600,
            }
        ]
        daily = [
            {
                "time": "2026-10-21T00:00:00Z",
                "restingHeartRate": 49,
                "bodyBatteryAtWakeTime": 89,
            }
        ]
        row = build_payload([], [], sleep, daily)["recovery"][0]
        self.assertEqual(row["sleepHours"], 7.8)
        self.assertEqual(row["hrv"], 51)
        self.assertEqual(row["restingHR"], 49)
        self.assertEqual(row["bodyBattery"], 89)
        self.assertEqual(row["sleepScore"], 77)
        self.assertEqual(row["deepSeconds"], 6000)

    def test_training_signals_keep_source_dates_and_missing_values(self):
        daily = [
            {
                "time": "2026-10-22T21:00:00Z",
                "bodyBatteryAtWakeTime": 82,
                "bodyBatteryChargedValue": 55,
                "bodyBatteryDrainedValue": 17,
            }
        ]
        status = [
            {
                "time": "2026-10-23T06:50:34Z",
                "calendarDate": "2026-10-23",
                "trainingStatusFeedbackPhrase": "MAINTAINING_1",
                "dailyTrainingLoadAcute": 228,
                "dailyTrainingLoadChronic": 216,
                "dailyAcuteChronicWorkloadRatio": 1.0,
                "minTrainingLoadChronic": 172.8,
                "maxTrainingLoadChronic": 324,
            }
        ]
        readiness = [
            {
                "time": "2026-10-23T06:50:35Z",
                "calendarDate": "2026-10-23",
                "score": 64,
                "level": "MODERATE",
            }
        ]
        battery = [{"time": "2026-10-23T09:27:00Z", "BodyBatteryLevel": 83}]
        data = build_payload([], [], [], daily, None, status, readiness, battery)
        self.assertEqual(data["training"]["status"][0]["label"], "Maintaining")
        self.assertEqual(data["training"]["status"][0]["loadRatio"], 1)
        self.assertEqual(data["training"]["status"][0]["optimalMin"], 172.8)
        self.assertEqual(data["training"]["readiness"][0]["score"], 64)
        self.assertEqual(data["training"]["bodyBatteryLatest"]["level"], 83)
        self.assertEqual(data["recovery"][0]["bodyBatteryCharged"], 55)
        self.assertEqual(data["recovery"][0]["date"], "2026-10-23")
        self.assertIsNone(
            build_payload(
                [],
                [],
                [],
                None,
                None,
                [],
                [{"time": "2026-10-23T06:00:00Z", "score": 120}],
                [],
            )["training"]["readiness"][0]["score"]
        )

    def test_daily_recovery_does_not_invent_sleep_when_missing(self):
        rows = build_payload(
            [], [], [], [{"time": "2026-10-21T00:00:00Z", "restingHeartRate": 49}]
        )["recovery"]
        self.assertEqual(rows[0]["restingHR"], 49)
        self.assertIsNone(rows[0].get("sleepHours"))
        self.assertIsNone(rows[0].get("hrv"))

    def test_garmin_calories_and_sync_timestamps_are_distinct(self):
        data = build_payload(
            [],
            [],
            [],
            [
                {
                    "time": "2026-10-21T00:00:00Z",
                    "activeKilocalories": 520,
                    "bmrKilocalories": 1670,
                }
            ],
            [],
            [],
            [],
            [],
            [{"time": "2026-10-21T21:00:00Z", "Device_Name": "Watch"}],
            [{"time": "2026-10-22T09:00:00Z", "result": "no_new_data"}],
        )
        self.assertEqual(data["recovery"][0]["totalCalories"], 2190)
        self.assertEqual(data["recovery"][0]["activeCalories"], 520)
        self.assertEqual(data["sync"]["deviceName"], "Watch")
        self.assertEqual(data["sync"]["collectorResult"], "no_new_data")
        self.assertEqual(
            data["sync"]["sources"]["Daily health"], "2026-10-21T00:00:00+00:00"
        )
        self.assertIsNone(data["sync"]["sources"]["Sleep"])
        missing = build_payload(
            [], [], [], [{"time": "2026-10-21T00:00:00Z", "activeKilocalories": 520}]
        )
        self.assertIsNone(missing["recovery"][0]["totalCalories"])

    def test_body_weight_grams_use_latest_daily_reading_without_carrying_forward(self):
        readings = [
            {"time": "2026-10-20T10:00:00Z", "weight": 73100},
            {"time": "2026-10-20T13:00:00Z", "weight": 72900},
            {"time": "2026-10-21T22:30:00Z", "weight": 72800},
            {"time": "2026-10-21T10:00:00Z", "weight": 0},
        ]
        rows = build_payload(
            [],
            [],
            [],
            [{"time": "2026-10-21T00:00:00Z", "restingHeartRate": 48}],
            readings,
        )["recovery"]
        by_day = {r["date"]: r for r in rows}
        self.assertEqual(by_day["2026-10-20"]["bodyWeightKg"], 72.9)
        self.assertEqual(by_day["2026-10-20"]["bodyWeightTime"], "2026-10-20T13:00:00Z")
        self.assertNotIn("bodyWeightKg", by_day["2026-10-21"])
        self.assertEqual(by_day["2026-10-22"]["bodyWeightKg"], 72.8)

    def test_body_weight_accepts_mixed_naive_and_aware_timestamps(self):
        rows = build_payload(
            [],
            [],
            [],
            [],
            [
                {"time": "2026-10-20T10:00:00", "weight": 73000},
                {"time": "2026-10-20T12:00:00+03:00", "weight": 74000},
            ],
        )["recovery"]
        self.assertEqual(rows[0]["bodyWeightKg"], 73)
        self.assertEqual(rows[0]["bodyWeightTime"], "2026-10-20T10:00:00")

    def test_full_export_reads_original_training_health_and_archives(self):
        from io import BytesIO
        from zipfile import ZipFile

        sets, workouts, _ = self.records()
        workouts[0]["activityType"] = "strength_training"
        sources = {
            "StrengthSet": sets,
            "ActivitySummary": workouts,
            "StrengthSetGarminArchive": [dict(sets[0], rawWeight="16")],
            "BodyComposition": [{"time": "2026-10-21T00:00:00Z", "weight": 72900}],
        }
        queries = []

        def query(q):
            queries.append(q)
            if q == "SHOW MEASUREMENTS":
                return [{"name": k} for k in sources] + [
                    {"name": "HeartRateIntraday"},
                    {"name": 'bad"name'},
                ]
            for name, rows in sources.items():
                if '"' + name + '"' in q:
                    return rows
            return []

        client = Mock()
        body, filename, counts = DataStore(lambda: (client, query)).full_export()
        self.assertEqual(counts["sets"], 1)
        self.assertEqual(counts["bodyWeightDays"], 1)
        self.assertFalse(
            any("HeartRateIntraday" in q or 'bad"name' in q for q in queries)
        )
        self.assertTrue(
            all(q == "SHOW MEASUREMENTS" or q.startswith("SELECT ") for q in queries)
        )
        client.close.assert_called_once()
        with ZipFile(BytesIO(body)) as archive:
            self.assertIsNone(archive.testzip())


if __name__ == "__main__":
    unittest.main()
