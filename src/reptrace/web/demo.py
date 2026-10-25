"""Run an isolated, read-only showcase with synthetic training history.

No Garmin account, InfluxDB server, or production configuration is used.
"""

import argparse
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
import os
from pathlib import Path
import tempfile


def sample_records(today=None):
    """Create deterministic examples relative to today, never personal records."""
    today = today or datetime.now(timezone.utc).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    records = {
        name: []
        for name in (
            "StrengthSet",
            "ActivitySummary",
            "SleepSummary",
            "DailyStats",
            "BodyComposition",
            "TrainingStatus",
            "TrainingReadiness",
            "BodyBatteryIntraday",
            "DeviceSync",
            "CollectorPoll",
        )
    }
    upper = [
        ("Barbell Bench Press", "BENCH_PRESS", 50),
        ("Seated Cable Row", "ROW", 40),
        ("Incline Dumbbell Bench Press", "BENCH_PRESS", 18),
        ("Cable Lateral Raise", "LATERAL_RAISE", 5),
        ("Cable Triceps Extension", "TRICEPS_EXTENSION", 20),
    ]
    lower = [
        ("Barbell Squat", "SQUAT", 60),
        ("Romanian Deadlift", "DEADLIFT", 50),
        ("Leg Press", "LEG_PRESS", 100),
        ("Lying Leg Curl", "LEG_CURL", 30),
        ("Calf Raise Machine", "CALF_RAISE", 35),
    ]
    for i in range(48):
        stamp = today - timedelta(days=96 - i * 2)
        identity = f"demo-{i:03}"
        records["ActivitySummary"].append(
            {
                "time": stamp.isoformat(),
                "ActivityID": identity,
                "activityType": "strength_training",
                "activityName": "Lower 1" if i % 2 else "Upper 1",
                "elapsedDuration": 3300 + (i % 4) * 180,
                "averageHR": 112,
                "calories": 290 + i % 6 * 12,
                "source": "Garmin",
            }
        )
        for j, (exercise, category, base) in enumerate(lower if i % 2 else upper):
            for k in range(3):
                weight = float(base + (i // 12) * (1 if base < 20 else 2.5))
                reps = 8 + (i // 4 + k) % 5
                records["StrengthSet"].append(
                    {
                        "time": (
                            stamp + timedelta(seconds=j * 360 + k * 120)
                        ).isoformat(),
                        "ActivityID": identity,
                        "SetIndex": str(j * 3 + k + 1),
                        "Exercise": exercise,
                        "ExerciseCategory": category,
                        "weightKg": weight,
                        "reps": reps,
                        "volumeKg": weight * reps,
                        "estimated1RMKg": weight * (1 + reps / 30)
                        if reps <= 10
                        else None,
                        "setNumber": k + 1,
                        "setOrder": j * 3 + k + 1,
                        "durationSeconds": 35,
                        "restAfterSeconds": 90,
                        "source": "Garmin",
                    }
                )
    for i in range(100):
        stamp = (today - timedelta(days=i)).isoformat()
        records["SleepSummary"].append(
            {
                "time": stamp,
                "sleepTimeSeconds": 25200 + i % 5 * 720,
                "avgOvernightHrv": 46 + i % 9,
                "restingHeartRate": 52 + i % 4,
                "sleepScore": 78 + i % 12,
                "deepSleepSeconds": 4800,
                "lightSleepSeconds": 14400 + i % 5 * 720,
                "remSleepSeconds": 6000,
                "awakeSleepSeconds": 900,
            }
        )
        records["DailyStats"].append(
            {
                "time": stamp,
                "bodyBatteryAtWakeTime": 73 + i % 16,
                "activeKilocalories": 480 + i % 5 * 35,
                "bmrKilocalories": 1800,
            }
        )
        if i % 5 == 0:
            records["BodyComposition"].append({"time": stamp, "weight": 78000 + i * 8})
    return records


class DemoClient:
    """Minimal read-only adapter for the application's normal data pipeline."""

    def __init__(self, records):
        self.records = records

    def query(self, query):
        if query == "SHOW MEASUREMENTS":
            return [{"name": name} for name in self.records]
        for name, rows in self.records.items():
            if f'FROM "{name}"' in query:
                return rows
        return []

    def close(self):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=3002)
    parser.add_argument(
        "--empty", action="store_true", help="Show the empty-account experience"
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="training-demo-") as directory:
        # Set paths before importing the web module, whose stores initialize at import.
        os.environ["WEB_STATE_PATH"] = str(Path(directory) / "state.sqlite")
        os.environ["GARMIN_WORKOUT_STATE_PATH"] = str(Path(directory) / "garmin.sqlite")
        os.environ["USER_TIMEZONE"] = "UTC"
        from reptrace.web import server as web

        client = DemoClient({} if args.empty else sample_records())
        web.STORE = web.DataStore(
            factory=lambda: (client, client.query), state_store=web.STATE
        )

        class DemoHandler(web.Handler):
            def do_POST(self):
                if self.local_request():
                    self.send_body(
                        b'{"error":"Read-only demo: saving and external integrations are disabled."}',
                        "application/json",
                        403,
                    )

        server = ThreadingHTTPServer(("127.0.0.1", args.port), DemoHandler)
        print(f"Synthetic, read-only demo: http://127.0.0.1:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
