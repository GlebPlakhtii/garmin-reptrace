"""Backfill exercise sets for strength workouts already stored in InfluxDB."""

import argparse
import os
import time
from datetime import date

from garminconnect import Garmin
from influxdb import InfluxDBClient
from influxdb_client_3 import InfluxDBClient3

from reptrace.training.strength import (
    build_strength_points,
    has_manual_strength_details,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument(
        "--delay", type=float, default=5, help="Seconds between Garmin requests"
    )
    args = parser.parse_args()
    if args.start_date and args.end_date and args.start_date > args.end_date:
        parser.error("start-date must be on or before end-date")
    if args.delay < 0:
        parser.error("delay must be nonnegative")
    version = os.getenv("INFLUXDB_VERSION", "1")
    database = os.getenv("INFLUXDB_DATABASE", "GarminStats")
    host = os.getenv("INFLUXDB_HOST", "influxdb")
    port = int(os.getenv("INFLUXDB_PORT", "8086"))
    secure = os.getenv("INFLUXDB_ENDPOINT_IS_HTTP", "true").lower() in (
        "false",
        "0",
        "no",
    )
    if version == "1":
        client = InfluxDBClient(
            host=host,
            port=port,
            username=os.getenv("INFLUXDB_USERNAME"),
            password=os.getenv("INFLUXDB_PASSWORD"),
            database=database,
            ssl=secure,
            verify_ssl=secure,
        )

        def query(q):
            return list(client.query(q).get_points())

        def write(points):
            if not client.write_points(points):
                raise RuntimeError("InfluxDB did not accept strength points")
    elif version == "3":
        client = InfluxDBClient3(
            host=f"{'https' if secure else 'http'}://{host}:{port}",
            token=os.getenv("INFLUXDB_V3_ACCESS_TOKEN"),
            database=database,
        )

        def query(q):
            return client.query(q, language="influxql").to_pylist()

        def write(points):
            client.write(record=points)
    else:
        parser.error("INFLUXDB_VERSION must be 1 or 3")
    clauses = ["\"activityType\" = 'strength_training'"]
    if args.start_date:
        clauses.append(f"time >= '{args.start_date}T00:00:00Z'")
    if args.end_date:
        from datetime import timedelta

        clauses.append(f"time < '{args.end_date + timedelta(days=1)}T00:00:00Z'")
    workouts = query(
        'SELECT "Activity_ID", "activityName", "Device", "User_ID" FROM "ActivitySummary" WHERE '
        + " AND ".join(clauses)
        + " ORDER BY time DESC"
    )
    print(f"Found {len(workouts)} stored strength workouts", flush=True)
    if not workouts:
        client.close()
        return
    garmin = Garmin(is_cn=os.getenv("GARMINCONNECT_IS_CN", "false").lower() == "true")
    # Reuse existing authorization, without prompting or printing credentials.
    garmin.login(os.getenv("TOKEN_DIR", "~/.garminconnect"))
    total = 0
    for index, workout in enumerate(workouts):
        if workout["Activity_ID"] < 0 or has_manual_strength_details(
            client, version, workout["Activity_ID"]
        ):
            print(
                f"{index + 1}/{len(workouts)}: preserved reviewed manual session",
                flush=True,
            )
            continue
        activity = {
            "activityId": workout["Activity_ID"],
            "activityName": workout["activityName"],
            "startTimeGMT": str(workout["time"]),
            "User_ID": workout.get("User_ID"),
        }
        payload = garmin.get_activity_exercise_sets(activity["activityId"])
        points = build_strength_points(
            activity, payload, workout.get("Device") or "Unknown", database
        )
        if points:
            write(points)
        total += len(points)
        print(
            f"{index + 1}/{len(workouts)}: {workout['activityName']} — {len(points)} set/exercise points",
            flush=True,
        )
        if index + 1 < len(workouts):
            time.sleep(args.delay)
    client.close()
    print(
        f"Strength backfill complete: {len(workouts)} workouts, {total} points",
        flush=True,
    )


if __name__ == "__main__":
    main()
