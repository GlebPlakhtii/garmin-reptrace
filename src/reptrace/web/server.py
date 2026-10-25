"""Local strength dashboard with reversible edits backed by the existing InfluxDB."""

from collections import defaultdict
from datetime import datetime, timezone
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import math
import os
import re
from pathlib import Path
import threading
import time
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from reptrace.garmin.workouts import GarminWorkouts
from reptrace.storage.reader import DatabaseReader
from reptrace.storage.state import WebState, Conflict, revision
from reptrace.storage.coordination import StrengthBusy, strength_lock
from reptrace.training.planning import build_next_sessions
from reptrace.exports.plans import render_plan
from reptrace.exports.sessions import export_sessions, MIME

STATIC = Path(__file__).with_name("static")
ZONE = ZoneInfo(os.getenv("USER_TIMEZONE") or "Europe/Kyiv")


def metric(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (ValueError, TypeError):
        return None
    return value if math.isfinite(value) else None


def timestamp(stamp):
    value = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def local_date(stamp):
    return timestamp(stamp).astimezone(ZONE).date().isoformat()


def make_client():
    host = os.getenv("INFLUXDB_HOST", "influxdb")
    port = int(os.getenv("INFLUXDB_PORT", "8086"))
    database = os.getenv("INFLUXDB_DATABASE", "GarminStats")
    secure = os.getenv("INFLUXDB_ENDPOINT_IS_HTTP", "true").lower() in (
        "false",
        "0",
        "no",
    )
    if os.getenv("INFLUXDB_VERSION", "1") == "3":
        from influxdb_client_3 import InfluxDBClient3

        client = InfluxDBClient3(
            host=f"{'https' if secure else 'http'}://{host}:{port}",
            database=database,
            token=os.getenv("INFLUXDB_V3_ACCESS_TOKEN"),
        )
        return client, lambda q: client.query(q, language="influxql").to_pylist()
    from influxdb import InfluxDBClient

    client = InfluxDBClient(
        host=host,
        port=port,
        database=database,
        username=os.getenv("INFLUXDB_USERNAME"),
        password=os.getenv("INFLUXDB_PASSWORD"),
        ssl=secure,
        verify_ssl=secure,
        timeout=15,
        retries=1,
    )
    return client, lambda q: list(client.query(q).get_points())


def build_payload(
    raw_sets,
    raw_workouts,
    raw_sleep,
    raw_daily=None,
    raw_body=None,
    raw_status=None,
    raw_readiness=None,
    raw_battery=None,
    raw_device_sync=None,
    raw_collector=None,
):
    """Return only display data; no credentials, import hashes or raw audit rows."""
    # A workout crossing midnight belongs to its start date. Exact set times
    # remain available separately; date filters must not split its set log.
    session_dates = {str(r["ActivityID"]): local_date(r["time"]) for r in raw_workouts}
    sets = []
    sets_by_session = defaultdict(list)
    for r in raw_sets:
        session = str(r["ActivityID"])
        sets_by_session[session].append(r)
        exercise = r["Exercise"]
        # Undo the retired rear-delt alias for historical sets without rewriting
        # their raw Influx records. Explicit Reverse Pec Deck Fly stays intact.
        if exercise == "Reverse Pec Deck Fly":
            original = r.get("originalExercise")
            if original in ("Rear Delt Fly", "Seated Rear Lateral Raise"):
                exercise = original
            elif not original and r.get("exerciseCode") == "SEATED_REAR_LATERAL_RAISE":
                exercise = "Seated Rear Lateral Raise"
        sets.append(
            {
                "id": session + ":" + str(r["SetIndex"]),
                "sessionId": session,
                "exercise": exercise,
                "category": r.get("ExerciseCategory", "UNKNOWN"),
                "date": r.get("sourceDate")
                or session_dates.get(session)
                or local_date(r["time"]),
                "time": str(r["time"]),
                "dateOnly": r.get("timeAccuracy") == "date-only",
                "source": "manual"
                if (r.get("source") or "").startswith("Manual")
                else "garmin",
                "number": metric(r.get("setNumber")),
                "order": metric(r.get("setOrder")),
                "weight": metric(r.get("weightKg")),
                "reps": metric(r.get("reps")),
                "volume": metric(r.get("volumeKg")),
                "estimatedMax": metric(r.get("estimated1RMKg")),
                "rest": metric(r.get("restAfterSeconds")),
                "duration": metric(r.get("durationSeconds")),
                "originalExercise": r.get("originalExercise") or "",
                "note": r.get("dataNote") or "",
            }
        )
    workouts = []
    for r in raw_workouts:
        identity = str(r["ActivityID"])
        workouts.append(
            {
                "id": identity,
                "date": local_date(r["time"]),
                "time": str(r["time"]),
                "name": r.get("activityName") or "Strength training",
                "source": "manual"
                if (r.get("source") or "").startswith("Manual")
                else "garmin",
                "dateOnly": r.get("timeAccuracy") == "date-only",
                "duration": metric(r.get("elapsedDuration")),
                "calories": metric(r.get("calories")),
                "averageHR": metric(r.get("averageHR")),
                "maxHR": metric(r.get("maxHR")),
                "url": r.get("activityUrl") or "",
                "revision": revision(sets_by_session[identity]),
            }
        )
    recovery = {}
    for r in raw_sleep:
        day = local_date(r["time"])
        seconds = metric(r.get("sleepTimeSeconds"))
        recovery[day] = {
            "date": day,
            "sleepHours": seconds / 3600 if seconds is not None else None,
            "hrv": metric(r.get("avgOvernightHrv")),
            "restingHR": metric(r.get("restingHeartRate")),
            "sleepScore": metric(r.get("sleepScore")),
            "bodyBattery": None,
            "deepSeconds": metric(r.get("deepSleepSeconds")),
            "lightSeconds": metric(r.get("lightSleepSeconds")),
            "remSeconds": metric(r.get("remSleepSeconds")),
            "awakeSeconds": metric(r.get("awakeSleepSeconds")),
        }
    for r in raw_daily or []:
        day = local_date(r["time"])
        row = recovery.setdefault(day, {"date": day})
        resting = metric(r.get("restingHeartRate"))
        if resting is not None:
            row["restingHR"] = resting
        row["bodyBattery"] = metric(r.get("bodyBatteryAtWakeTime"))
        row["bodyBatteryCharged"] = metric(r.get("bodyBatteryChargedValue"))
        row["bodyBatteryDrained"] = metric(r.get("bodyBatteryDrainedValue"))
        row["activeCalories"] = metric(r.get("activeKilocalories"))
        row["restingCalories"] = metric(r.get("bmrKilocalories"))
        row["totalCalories"] = (
            row["activeCalories"] + row["restingCalories"]
            if row["activeCalories"] is not None and row["restingCalories"] is not None
            else None
        )
    for r in sorted(raw_body or [], key=lambda r: timestamp(r["time"])):
        grams = metric(r.get("weight"))
        if grams is None or grams <= 0:
            continue
        day = local_date(r["time"])
        row = recovery.setdefault(day, {"date": day})
        row.update(
            bodyWeightKg=grams / 1000,
            bodyWeightTime=str(r["time"]),
            bodyWeightSource="garmin",
        )
    sleep = sorted(recovery.values(), key=lambda row: row["date"])
    status = []
    for r in raw_status or []:
        phrase = str(r.get("trainingStatusFeedbackPhrase") or "").split("_")[0]
        label = (
            phrase.title()
            if phrase
            in {
                "PEAKING",
                "PRODUCTIVE",
                "MAINTAINING",
                "RECOVERY",
                "STRAINED",
                "UNPRODUCTIVE",
                "DETRAINING",
                "OVERREACHING",
            }
            else None
        )
        status.append(
            {
                "date": r.get("calendarDate") or local_date(r["time"]),
                "time": str(r["time"]),
                "label": label,
                "acuteLoad": metric(r.get("dailyTrainingLoadAcute")),
                "chronicLoad": metric(r.get("dailyTrainingLoadChronic")),
                "loadRatio": metric(r.get("dailyAcuteChronicWorkloadRatio")),
                "optimalMin": metric(r.get("minTrainingLoadChronic")),
                "optimalMax": metric(r.get("maxTrainingLoadChronic")),
            }
        )
    readiness = []
    for r in raw_readiness or []:
        level = r.get("level")
        score = metric(r.get("score"))
        readiness.append(
            {
                "date": r.get("calendarDate") or local_date(r["time"]),
                "time": str(r["time"]),
                "score": score if score is not None and 0 <= score <= 100 else None,
                "level": level.title()
                if level in {"POOR", "LOW", "MODERATE", "HIGH", "PRIME"}
                else None,
            }
        )
    battery = None
    if raw_battery:
        latest = max(raw_battery, key=lambda r: timestamp(r["time"]))
        level = metric(latest.get("BodyBatteryLevel"))
        if level is not None and 0 <= level <= 100:
            battery = {
                "level": level,
                "time": str(latest["time"]),
                "date": local_date(latest["time"]),
            }

    def latest(rows):
        times = []
        for row in rows or []:
            try:
                times.append(timestamp(row["time"]))
            except (KeyError, TypeError, ValueError):
                continue
        return max(times).isoformat() if times else None

    watch = max(
        raw_device_sync or [], key=lambda row: timestamp(row["time"]), default=None
    )
    collector = max(
        raw_collector or [], key=lambda row: timestamp(row["time"]), default=None
    )
    sync = {
        "watchUploadAt": str(watch["time"]) if watch else None,
        "deviceName": str(watch.get("Device_Name") or watch.get("Device") or "")
        if watch
        else None,
        "collectorPollAt": str(collector["time"]) if collector else None,
        "collectorResult": str(collector.get("result") or "") if collector else None,
        "sources": {
            name: latest(rows)
            for name, rows in [
                (
                    "Strength sets",
                    [
                        r
                        for r in raw_sets
                        if not (r.get("source") or "").startswith("Manual")
                    ],
                ),
                (
                    "Strength activities",
                    [
                        r
                        for r in raw_workouts
                        if not (r.get("source") or "").startswith("Manual")
                    ],
                ),
                ("Daily health", raw_daily),
                ("Sleep", raw_sleep),
                ("Body weight", raw_body),
                ("Training status", raw_status),
                ("Training readiness", raw_readiness),
                ("Body Battery", raw_battery),
            ]
        },
    }
    return {
        "sets": sets,
        "workouts": workouts,
        "recovery": sleep,
        "sync": sync,
        "training": {
            "status": sorted(status, key=lambda r: r["time"]),
            "readiness": sorted(readiness, key=lambda r: r["time"]),
            "bodyBatteryLatest": battery,
        },
        "refreshedAt": datetime.now(timezone.utc).isoformat(),
        "timezone": str(ZONE),
    }


class DataStore:
    def __init__(self, factory=make_client, ttl=60, state_store=None, snapshot_timeout=1):
        self.factory = factory
        self.ttl = ttl
        self.lock = threading.Lock()
        self.cached = None
        self.expires = 0
        self.state_store = state_store
        self.snapshot_timeout = snapshot_timeout

    def attach_metadata(self, result):
        if self.state_store:
            result.update(self.state_store.read())
            food = self.state_store.food_entries()
            result["foodLog"] = food if isinstance(food, list) else []
            recovery = {r["date"]: r for r in result["recovery"]}
            for day, values in result.get("recoveryOverrides", {}).items():
                recovery.setdefault(day, {"date": day}).update(values)
                if "bodyWeightKg" in values:
                    recovery[day].update(bodyWeightTime=None, bodyWeightSource="manual")
                recovery[day]["manualOverride"] = True
            result["recovery"] = sorted(recovery.values(), key=lambda r: r["date"])
        # Assistance is not lifted resistance. Keep API/CSV/Excel views aligned
        # with the chart; full exports still retain untouched source records.
        rules = result.get("volumeSettings", {}).get("exercises", {})
        for row in result.get("sets", []):
            configured = rules.get(row["exercise"], {}).get("assistance")
            assisted = (
                configured
                if isinstance(configured, bool)
                else bool(
                    re.search(r"\bassisted\b|\bassistance\b", row["exercise"], re.I)
                )
            )
            if assisted:
                row["estimatedMax"] = None
        return result

    def full_export(self):
        # Always acquire the process lock before cache/state locks, matching writers.
        with strength_lock(timeout=self.snapshot_timeout), self.lock:
            client, query = self.factory()
            try:
                base = {
                    "StrengthSet",
                    "StrengthExercise",
                    "StrengthManualSession",
                    "ActivitySummary",
                    "SleepSummary",
                    "DailyStats",
                    "BodyComposition",
                    "TrainingStatus",
                    "TrainingReadiness",
                    "DeviceSync",
                    "CollectorPoll",
                }
                available = {r["name"] for r in query("SHOW MEASUREMENTS")}
                names = sorted(
                    name
                    for name in available
                    if name in base
                    or re.fullmatch(
                        r"(StrengthSet|StrengthExercise|StrengthManualSession|ActivitySummary)(WebArchive|GarminArchive)",
                        name,
                    )
                )
                records = {}
                for name in names:
                    where = (
                        " WHERE \"activityType\" = 'strength_training' OR \"activityType\" = 'strength_training_end'"
                        if name == "ActivitySummary"
                        else ""
                    )
                    records[name] = query(
                        'SELECT * FROM "' + name + '"' + where + " ORDER BY time ASC"
                    )
                workouts = [
                    r
                    for r in records.get("ActivitySummary", [])
                    if r.get("activityType") == "strength_training"
                ]
                result = build_payload(
                    records.get("StrengthSet", []),
                    workouts,
                    records.get("SleepSummary", []),
                    records.get("DailyStats", []),
                    records.get("BodyComposition", []),
                )
                self.attach_metadata(result)
                if self.state_store:
                    records.update(self.state_store.export_records())
            finally:
                client.close()
        # Workbook rendering uses the captured snapshot and need not hold up writers.
        return export_sessions(result, full=True, source_records=records)

    def get(self, force=False):
        with self.lock:
            if (
                not force
                and self.cached is not None
                and time.monotonic() < self.expires
            ):
                return self.cached
        with strength_lock(timeout=self.snapshot_timeout), self.lock:
            # A concurrent reader may have refreshed while this request waited.
            if (
                not force
                and self.cached is not None
                and time.monotonic() < self.expires
            ):
                return self.cached
            client, query = self.factory()
            try:
                sets = query('SELECT * FROM "StrengthSet"')
                workouts = query(
                    'SELECT "ActivityID", "activityName", "activityUrl", "elapsedDuration", "calories", "averageHR", "maxHR", "source", "timeAccuracy" FROM "ActivitySummary" WHERE "activityType" = \'strength_training\''
                )
                sleep = query(
                    'SELECT "sleepTimeSeconds", "avgOvernightHrv", "restingHeartRate", "sleepScore", "deepSleepSeconds", "lightSleepSeconds", "remSleepSeconds", "awakeSleepSeconds" FROM "SleepSummary" ORDER BY time ASC'
                )
                daily = query(
                    'SELECT "restingHeartRate", "bodyBatteryAtWakeTime", "bodyBatteryChargedValue", "bodyBatteryDrainedValue", "activeKilocalories", "bmrKilocalories" FROM "DailyStats" ORDER BY time ASC'
                )
                body = query('SELECT "weight" FROM "BodyComposition" ORDER BY time ASC')
                status = query(
                    'SELECT "calendarDate", "trainingStatusFeedbackPhrase", "dailyTrainingLoadAcute", "dailyTrainingLoadChronic", "dailyAcuteChronicWorkloadRatio", "minTrainingLoadChronic", "maxTrainingLoadChronic" FROM "TrainingStatus" ORDER BY time DESC LIMIT 100'
                )
                readiness = query(
                    'SELECT "calendarDate", "score", "level" FROM "TrainingReadiness" ORDER BY time DESC LIMIT 100'
                )
                battery = query(
                    'SELECT "BodyBatteryLevel" FROM "BodyBatteryIntraday" ORDER BY time DESC LIMIT 1'
                )
                watch = query(
                    'SELECT "Device_Name" FROM "DeviceSync" ORDER BY time DESC LIMIT 1'
                )
                collector = query(
                    'SELECT "result" FROM "CollectorPoll" ORDER BY time DESC LIMIT 1'
                )
                result = build_payload(
                    sets,
                    workouts,
                    sleep,
                    daily,
                    body,
                    status,
                    readiness,
                    battery,
                    watch,
                    collector,
                )
                self.attach_metadata(result)
                result["nextSessions"] = build_next_sessions(
                    result, datetime.now(ZONE).date()
                )
                # Strict JSON ensures missing/nonfinite measurements never break the UI.
                body = json.dumps(
                    result, ensure_ascii=False, allow_nan=False, separators=(",", ":")
                ).encode()
                self.cached = (result, body, gzip.compress(body))
                self.expires = time.monotonic() + self.ttl
                return self.cached
            finally:
                client.close()


STATE = WebState(os.getenv("WEB_STATE_PATH", "/var/lib/form/state.sqlite"))
STORE = DataStore(state_store=STATE)
GARMIN_WORKOUTS = GarminWorkouts(
    os.getenv("GARMIN_WORKOUT_STATE_PATH", "/var/lib/form/garmin-workouts.sqlite")
)


from reptrace.garmin.integration import GarminIntegration
GARMIN_INTEGRATION = GarminIntegration(
    os.getenv('GARMIN_OPERATION_STATE_PATH', '/var/lib/form/garmin-operations.sqlite'),
    STATE, make_client, os.getenv('INFLUXDB_DATABASE', 'GarminStats'), ZONE,
)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def send_body(self, body, kind, status=200, compressed=False, retry_after=None):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        if retry_after is not None:
            self.send_header("Retry-After", str(retry_after))
        self.send_header(
            "Cache-Control", "no-store" if self.path.startswith("/api/") else "no-cache"
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        )
        if compressed:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def local_request(self):
        """Validate reads as well as writes against untrusted Host/DNS rebinding."""
        port = str(self.server.server_port)
        allowed = {
            f"localhost:{port}",
            f"127.0.0.1:{port}",
            f"[::1]:{port}",
            f"strength-web:{port}",
        }
        allowed.update(
            host.strip()
            for host in os.getenv("WEB_ALLOWED_HOSTS", "").split(",")
            if host.strip()
        )
        origin = self.headers.get("Origin")
        try:
            parsed = urlsplit(origin) if origin else None
            valid_origin = not parsed or (
                parsed.scheme in ("http", "https")
                and parsed.netloc in allowed
                and not parsed.username
                and not parsed.password
                and parsed.path in ("", "/")
            )
        except ValueError:
            valid_origin = False
        if self.headers.get("Host") not in allowed or not valid_origin:
            self.send_body(
                b'{"error":"This request must come from an allowed application host"}',
                "application/json",
                403,
            )
            return False
        return True

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        self.close_connection = True
        path = urlsplit(self.path).path
        if path not in (
            "/api/actions",
            "/api/database",
            "/api/garmin-workouts",
            "/api/food",
        ):
            self.send_body(b'{"error":"Not found"}', "application/json", 404)
            return
        if not self.local_request():
            return
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            self.send_body(b'{"error":"JSON is required"}', "application/json", 415)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 512000:
                raise ValueError("Request must contain at most 512 KB")
            body = json.loads(
                self.rfile.read(length),
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError("Nonfinite values are not allowed")
                ),
            )
            if not isinstance(body, dict):
                raise ValueError("Expected an object")
            if path == "/api/food":
                result = STATE.food_action(body)
                with STORE.lock:
                    STORE.expires = 0
            elif path == "/api/garmin-workouts":
                operation = body.get("operation")
                if not isinstance(operation, str) or not operation:
                    raise ValueError("A Garmin operation is required")
                if operation.startswith(('activity_', 'integration_', 'creation_', 'device_')):
                    result = GARMIN_INTEGRATION.call(body)
                    with STORE.lock:
                        STORE.expires = 0
                    self.send_body(json.dumps(result).encode(), 'application/json; charset=utf-8')
                    return
                plans = (
                    STORE.get(force=body.get("operation") in ("preview", "apply"))[0][
                        "nextSessions"
                    ]
                    if body.get("operation") not in ("list", "review")
                    else []
                )
                result = GARMIN_WORKOUTS.call(body, plans)
            elif path == "/api/database":
                operation = body.pop("operation", None)
                result = DatabaseReader(make_client, STATE).call(operation, **body)
            else:
                result = STATE.apply(
                    body,
                    make_client,
                    os.getenv("INFLUXDB_DATABASE", "GarminStats"),
                    ZONE,
                )
                with STORE.lock:
                    STORE.expires = 0
            self.send_body(
                json.dumps(result).encode(), "application/json; charset=utf-8"
            )
        except StrengthBusy as error:
            self.send_body(
                json.dumps({"error": str(error)}).encode(), "application/json", 503,
                retry_after=1,
            )
        except Conflict as error:
            self.send_body(
                json.dumps({"error": str(error)}).encode(), "application/json", 409
            )
        except (ValueError, TypeError, KeyError) as error:
            self.send_body(
                json.dumps({"error": str(error)}).encode(), "application/json", 400
            )
        except Exception as error:
            logging.error("Data request failed: %s", type(error).__name__)
            message = (
                "Garmin request failed. If applying an update, check Garmin before retrying."
                if path == "/api/garmin-workouts"
                else "Database query is temporarily unavailable."
                if path == "/api/database"
                else "Could not confirm changes. Reload and check the workout before retrying."
            )
            self.send_body(
                json.dumps({"error": message}).encode(), "application/json", 503
            )

    def do_GET(self):
        if not self.local_request():
            return
        url = urlsplit(self.path)
        path = url.path
        if path == "/api/garmin-operations":
            from reptrace.garmin.recovery import read_operations

            try:
                params = parse_qs(url.query, keep_blank_values=True)
                identities = params.get("id", [])
                if len(identities) > 1:
                    raise ValueError("Choose one operation")
                result = read_operations(GARMIN_INTEGRATION.journal, identities[0] if identities else None)
                self.send_body(json.dumps(result).encode(), "application/json; charset=utf-8")
            except ValueError as error:
                self.send_body(json.dumps({"error": str(error)}).encode(), "application/json", 400)
            except Exception:
                self.send_body(b'{"error":"Operation history is temporarily unavailable."}', "application/json", 503)
            return
        if path == "/training/exercise_catalog.json":
            from importlib.resources import files

            self.send_body(files("reptrace.training").joinpath("exercise_catalog.json").read_bytes(), "application/json; charset=utf-8")
            return
        if path == "/api/sessions.xlsx":
            try:
                params = parse_qs(url.query)
                get = lambda key: params.get(key, [None])[0]
                if get("full") == "1":
                    body, filename, counts = STORE.full_export()
                else:
                    payload, _, _ = STORE.get(force=True)
                    body, filename, counts = export_sessions(
                        payload,
                        from_date=get("from"),
                        to_date=get("to"),
                        source=get("source") or "all",
                        session_id=get("session"),
                        workout_kind=get("type"),
                        search=get("search") or "",
                    )
                self.send_response(200)
                self.send_header("Content-Type", MIME)
                self.send_header(
                    "Content-Disposition", 'attachment; filename="' + filename + '"'
                )
                self.send_header("X-Export-Sessions", str(counts["sessions"]))
                self.send_header("X-Export-Sets", str(counts["sets"]))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)
            except StrengthBusy as error:
                self.send_body(
                    str(error).encode(), "text/plain; charset=utf-8", 503,
                    retry_after=1,
                )
            except ValueError as error:
                self.send_body(str(error).encode(), "text/plain; charset=utf-8", 400)
            except Exception:
                logging.exception("Excel export failed")
                self.send_body(
                    b"Excel export is temporarily unavailable", "text/plain", 503
                )
            return
        if path == "/api/plan.png":
            try:
                params = parse_qs(url.query)
                payload, _, _ = STORE.get(force=params.get("refresh") == ["1"])
                plan = next(
                    (
                        p
                        for p in payload["nextSessions"]
                        if p["type"] == params.get("type", [""])[0]
                    ),
                    None,
                )
                if not plan:
                    raise ValueError("Choose upper1, upper2, lower1 or lower2")
                body = render_plan(plan, int(params.get("page", ["0"])[0]))
                self.send_body(body, "image/png")
            except StrengthBusy as error:
                self.send_body(
                    str(error).encode(), "text/plain; charset=utf-8", 503,
                    retry_after=1,
                )
            except ValueError as error:
                self.send_body(str(error).encode(), "text/plain", 400)
            except Exception:
                self.send_body(
                    b"Proposal is temporarily unavailable", "text/plain", 503
                )
            return
        if path in ("/api/data", "/api/health"):
            try:
                force = path == "/api/data" and parse_qs(url.query).get("refresh") == [
                    "1"
                ]
                payload, body, compressed = STORE.get(force=force)
                if path == "/api/health":
                    body = json.dumps(
                        {
                            "status": "ok",
                            "sets": len(payload["sets"]),
                            "workouts": len(payload["workouts"]),
                        }
                    ).encode()
                    self.send_body(body, "application/json; charset=utf-8")
                else:
                    accepts_gzip = "gzip" in self.headers.get("Accept-Encoding", "")
                    self.send_body(
                        compressed if accepts_gzip else body,
                        "application/json; charset=utf-8",
                        compressed=accepts_gzip,
                    )
            except StrengthBusy as error:
                self.send_body(
                    json.dumps({"error": str(error)}).encode(),
                    "application/json; charset=utf-8", 503, retry_after=1,
                )
            except Exception as error:
                logging.error("Training data request failed: %s", type(error).__name__)
                self.send_body(
                    b'{"error":"Training data is temporarily unavailable. Please try again."}',
                    "application/json; charset=utf-8",
                    503,
                )
            return
        assets = {
            "/": ("index.html", "text/html"),
            "/index.html": ("index.html", "text/html"),
            "/theme.js": ("theme.js", "text/javascript"),
            "/app.js": ("app.js", "text/javascript"),
            "/model.mjs": ("model.mjs", "text/javascript"),
            "/recovery.mjs": ("recovery.mjs", "text/javascript"),
            "/muscle-map.mjs": ("muscle-map.mjs", "text/javascript"),
            "/styles.css": ("styles.css", "text/css"),
            "/favicon.svg": ("favicon.svg", "image/svg+xml"),
        }
        asset = assets.get(path)
        if asset is None:
            self.send_body(b"Not found", "text/plain; charset=utf-8", 404)
            return
        try:
            self.send_body(
                (STATIC / asset[0]).read_bytes(), asset[1] + "; charset=utf-8"
            )
        except OSError:
            self.send_body(b"Asset unavailable", "text/plain; charset=utf-8", 500)

    def log_message(self, format, *args):
        logging.info(format, *args)


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    port = int(os.getenv("WEB_PORT", "3001"))
    server = ThreadingHTTPServer((os.getenv("WEB_HOST", "127.0.0.1"), port), Handler)
    logging.info("Garmin RepTrace listening on port %s", port)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
