"""Separate-process writer checks; only an isolated, uniquely named development DB."""

import copy
import json
import multiprocessing as mp
import os
import tempfile
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo
from influxdb import InfluxDBClient


def collector(options, points, ready, finished):
    from reptrace.garmin import collector as c

    c.influxdbclient = InfluxDBClient(**options)
    c.INFLUXDB_VERSION = "1"
    c.TAG_MEASUREMENTS_WITH_USER_EMAIL = False
    ready.set()
    try:
        c.write_points_to_influxdb(points)
        finished.put("ok")
    except Exception as error:
        finished.put(type(error).__name__)
    finally:
        c.influxdbclient.close()


def main():
    assert os.environ.get("INFLUXDB_HOST") and os.environ.get("INFLUXDB_PORT"), (
        "Explicit development endpoint required"
    )
    assert os.environ.get("WEB_STATE_PATH") and os.environ.get(
        "GARMIN_WORKOUT_STATE_PATH"
    ), "Temporary paths required"
    from reptrace.storage.state import (
        WebState,
        snapshot,
        snapshot_rows,
        revision,
        Conflict,
    )
    from reptrace.storage.coordination import strength_lock
    from reptrace.garmin.integration import GarminIntegration
    from tests.unit.garmin.test_integration import fixture
    from unittest.mock import Mock

    options = dict(
        host=os.environ["INFLUXDB_HOST"],
        port=int(os.environ["INFLUXDB_PORT"]),
        database="Integration_" + uuid.uuid4().hex,
    )
    admin = InfluxDBClient(**options)
    admin.create_database(options["database"])
    ctx = mp.get_context("spawn")

    def factory():
        client = InfluxDBClient(**options)
        return client, lambda q: list(client.query(q).get_points())

    try:
        with tempfile.TemporaryDirectory() as directory:
            os.environ["STRENGTH_MUTATION_LOCK_PATH"] = directory + "/shared.lock"
            os.environ["GARMIN_OPERATION_STATE_PATH"] = directory + "/operations.sqlite"
            points, remote = fixture()
            points.append(
                {
                    "measurement": "ActivitySummary",
                    "time": "2026-10-01T09:00:00Z",
                    "tags": {
                        "ActivityID": "123",
                        "ActivitySelector": "start",
                        "Device": "Synthetic",
                        "Database_Name": options["database"],
                    },
                    "fields": {
                        "Activity_ID": 123,
                        "activityType": "strength_training",
                        "activityName": "Synthetic",
                        "elapsedDuration": 600.0,
                    },
                }
            )
            for p in points:
                p["tags"].update(Device="Synthetic", Database_Name=options["database"])
            assert admin.write_points(points)
            state = WebState(directory + "/web.sqlite")
            adapter = Mock()
            adapter.activity_sets.side_effect = lambda _: copy.deepcopy(remote)

            def write(_, value):
                remote.clear()
                remote.update(copy.deepcopy(value))

            adapter.update_activity_sets.side_effect = write
            service = GarminIntegration(
                os.environ["GARMIN_OPERATION_STATE_PATH"],
                state,
                factory,
                options["database"],
                ZoneInfo("UTC"),
                lambda: adapter,
            )
            d = service.details("123")
            op = service.preview(
                dict(
                    requestId=str(uuid.uuid4()),
                    activityId="123",
                    localRevision=d["localRevision"],
                    remoteRevision=d["remoteRevision"],
                    changes=[{"setId": "123:2", "load": 22.5, "unit": "kg"}],
                )
            )
            ready, finished = ctx.Event(), ctx.Queue()
            worker = ctx.Process(
                target=collector, args=(options, points, ready, finished)
            )
            with strength_lock():
                worker.start()
                assert ready.wait(10)
                assert finished.empty(), "Collector escaped shared lock"
                result = service.apply(op["id"])
                assert result["status"] == "done", result["status"]
            worker.join(15)
            assert worker.exitcode == 0
            assert finished.get(timeout=2) == "ok"
            actual = service.local("123")
            rows = snapshot_rows(actual)
            assert next(r for r in rows if r["SetIndex"] == "2")["weightKg"] == 22.5
            assert next(r for r in rows if r["SetIndex"] == "0")["weightKg"] == 20
            # Crash after local commit but before integration completion: audit readback completes it.
            op = service.journal.get(op["id"])
            op.update(status="local_pending", localStatus="pending")
            service.journal.save(op)
            assert service.apply(op["id"])["status"] == "done"
            adapter.update_activity_sets.assert_called_once()
            reversal = service.reversal(
                dict(requestId=str(uuid.uuid4()), originalId=op["id"])
            )
            reversed_result = service.apply(reversal["id"])
            if reversed_result["status"] != "done":
                state.apply(
                    reversed_result["localBody"],
                    factory,
                    options["database"],
                    ZoneInfo("UTC"),
                )
            assert reversed_result["status"] == "done", reversed_result["status"]
            assert (
                next(
                    r
                    for r in snapshot_rows(service.local("123"))
                    if r["SetIndex"] == "2"
                )["weightKg"]
                == 20
            )
            try:
                service.reversal(dict(requestId=str(uuid.uuid4()), originalId=op["id"]))
            except Conflict:
                pass
            else:
                raise AssertionError("Stale reversal accepted")
            # An unresolved operation must also protect activities without manual markers.
            fresh = copy.deepcopy(points)
            for p in fresh:
                p["tags"]["ActivityID"] = "124"
                if p["measurement"] == "ActivitySummary":
                    p["fields"]["Activity_ID"] = 124
            assert admin.write_points(fresh)
            unresolved = service.journal.stage(
                str(uuid.uuid4()),
                "correction",
                {},
                dict(remoteStatus="uncertain"),
                activity="124",
            )
            unresolved["status"] = "remote_uncertain"
            service.journal.save(unresolved)
            stale = copy.deepcopy(fresh)
            for p in stale:
                if p["measurement"] == "StrengthSet":
                    p["fields"]["weightKg"] = 999
            ready, finished = ctx.Event(), ctx.Queue()
            worker = ctx.Process(
                target=collector, args=(options, stale, ready, finished)
            )
            worker.start()
            worker.join(15)
            assert worker.exitcode == 0
            assert finished.get(timeout=2) == "ok"
            assert all(r["weightKg"] == 20 for r in snapshot_rows(service.local("124")))
            print(
                "PASS: separate-process stale collector batch, manual marker, durable unresolved operation, combined correction, crash recovery, reversal conflict/readback"
            )
    finally:
        admin.drop_database(options["database"])
        admin.close()


if __name__ == "__main__":
    main()
