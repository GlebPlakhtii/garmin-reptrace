"""Read-only Garmin running imports in a separate, durable display cache."""

from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
import json
import re
import sqlite3
import threading

from reptrace.training.running import METRICS, detail_notes, normalize_detail


def client_factory():
    from reptrace.garmin.workouts import GarminAdapter

    return GarminAdapter().client


def current_summary(run, imported):
    """Keep identity, collection dates and the validated link from current history."""
    summary = {**run, **imported}
    for key in ("id", "date", "time", "type", "url"):
        if key in run:
            summary[key] = run[key]
        else:
            summary.pop(key, None)
    return summary


class RunningStore:
    def __init__(self, path, factory=client_factory):
        self.path = Path(path)
        self.factory = factory
        self.lock = threading.RLock()

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        self.path.chmod(0o600)
        try:
            with connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS running_details (id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
                )
                yield connection
        finally:
            connection.close()

    def read(self, identity):
        if not self.path.exists():
            return None
        with self.connect() as db:
            row = db.execute(
                "SELECT payload FROM running_details WHERE id=?", (str(identity),)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def enrich(self, runs):
        if not runs or not self.path.exists():
            return runs
        with self.connect() as db:
            rows = db.execute(
                """SELECT id, json_extract(payload, '$.summary'), json_extract(payload, '$.syncedAt')
                   FROM running_details WHERE id IN (SELECT value FROM json_each(?))""",
                (json.dumps([run["id"] for run in runs]),),
            )
            saved = {
                identity: {**json.loads(summary), "detailsSyncedAt": stamp}
                for identity, summary, stamp in rows
            }
        return [
            current_summary(run, saved[run["id"]]) if run["id"] in saved else run
            for run in runs
        ]

    def get(self, run, refresh=False):
        identity = str(run["id"])
        with self.lock:
            if not re.fullmatch(r"[1-9][0-9]{0,19}", identity):
                raise ValueError("Choose a recorded Garmin run")
            cached = self.read(identity)
            if cached:
                cached["summary"] = current_summary(run, cached["summary"])
                if not refresh:
                    return cached
            try:
                client = self.factory()
                activity = client.get_activity(identity)
                failures = []

                def optional(method, empty):
                    try:
                        return getattr(client, method)(identity)
                    except Exception:
                        failures.append(method)
                        return empty

                details = optional("get_activity_details", {})
                splits = optional("get_activity_splits", {})
                zones = optional("get_activity_hr_in_timezones", [])
                result = normalize_detail(run, activity, details, splits, zones)
                # A partial refresh must not discard previously imported detail.
                for failed, key in [
                    ("get_activity_details", "samples"),
                    ("get_activity_splits", "laps"),
                    ("get_activity_hr_in_timezones", "zones"),
                ]:
                    if failed in failures and cached:
                        result[key] = deepcopy(cached[key])
                if "get_activity_details" in failures and cached:
                    result["sampleCount"] = len(result["samples"])
                    result["sourceSampleCount"] = cached.get("sourceSampleCount")
                if failures:
                    result["notes"] = detail_notes(result["summary"], result["samples"], result["laps"])
                    result["notes"].append(
                        "Some Garmin detail requests failed. Previously imported sections, if any, were retained; refresh to retry."
                    )
                    result["partial"] = True
                body = json.dumps(result, allow_nan=False, separators=(",", ":"))
                with self.connect() as db:
                    db.execute(
                        "INSERT INTO running_details VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                        (identity, body),
                    )
                return result
            except Exception:
                if cached:
                    return {
                        **cached,
                        "stale": True,
                        "warning": "Garmin refresh failed. Showing the last imported detail.",
                    }
                return {
                    "summary": run,
                    "samples": [],
                    "laps": [],
                    "zones": [
                        {"zone": n, "seconds": run[f"hrZone{n}"], "lowBpm": None}
                        for n in range(1, 6)
                        if run.get(f"hrZone{n}") is not None
                    ],
                    "metricCatalog": METRICS,
                    "notes": [],
                    "syncedAt": None,
                    "warning": "Garmin detail is temporarily unavailable. Check Garmin authentication and retry.",
                    "source": "Collected summary",
                }
