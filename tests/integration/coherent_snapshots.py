"""Verify dashboard/export snapshots during a paused real Influx replacement.

Requires an explicitly configured disposable development InfluxDB endpoint.
Only a uniquely named synthetic database is created and removed.
"""

import multiprocessing as mp
import os
import tempfile
import uuid

from influxdb import InfluxDBClient


def records(generation):
    tags = {"ActivityID": "synthetic"}
    return [
        {
            "measurement": "StrengthSet",
            "time": "2026-10-01T09:00:01Z",
            "tags": dict(tags, SetIndex="1", Exercise="Barbell Bench Press"),
            "fields": {"weightKg": generation * 10.0, "reps": 5},
        },
        {
            "measurement": "ActivitySummary",
            "time": "2026-10-01T09:00:00Z",
            "tags": tags,
            "fields": {
                "activityType": "strength_training",
                "activityName": f"Generation {generation}",
            },
        },
    ]


def paused_replacement(options, partial, finish):
    from reptrace.storage.coordination import strength_lock

    client = InfluxDBClient(**options)
    try:
        with strength_lock():
            client.query('DELETE FROM "StrengthSet"')
            client.query('DELETE FROM "ActivitySummary"')
            assert client.write_points(records(2)[:1])
            partial.set()
            if not finish.wait(15):
                raise RuntimeError("Snapshot check did not release writer")
            assert client.write_points(records(2)[1:])
    finally:
        client.close()


def main():
    assert os.environ.get("INFLUXDB_HOST") and os.environ.get("INFLUXDB_PORT"), (
        "Explicit development endpoint required"
    )
    assert os.environ.get("WEB_STATE_PATH") and os.environ.get(
        "GARMIN_WORKOUT_STATE_PATH"
    ), "Temporary state paths required"
    from reptrace.storage.coordination import StrengthBusy
    from reptrace.web.server import DataStore

    options = {
        "host": os.environ["INFLUXDB_HOST"],
        "port": int(os.environ["INFLUXDB_PORT"]),
        "database": "SnapshotIntegration_" + uuid.uuid4().hex,
    }
    admin = InfluxDBClient(**options)
    admin.create_database(options["database"])
    ctx = mp.get_context("spawn")

    def factory():
        client = InfluxDBClient(**options)
        return client, lambda q: list(client.query(q).get_points())

    try:
        with tempfile.TemporaryDirectory() as directory:
            os.environ["STRENGTH_MUTATION_LOCK_PATH"] = directory + "/strength.lock"
            assert admin.write_points(records(1))
            store = DataStore(factory, snapshot_timeout=0.1)
            cached = store.get()
            assert cached[0]["sets"][0]["weight"] == 10
            assert cached[0]["workouts"][0]["name"] == "Generation 1"
            partial, finish = ctx.Event(), ctx.Event()
            worker = ctx.Process(
                target=paused_replacement, args=(options, partial, finish)
            )
            worker.start()
            try:
                assert partial.wait(10)
                # The real storage engine is between measurements at this point.
                assert (
                    list(admin.query('SELECT * FROM "ActivitySummary"').get_points())
                    == []
                )
                assert store.get() is cached
                cold = DataStore(factory, snapshot_timeout=0.1)
                for read in (
                    lambda: store.get(force=True),
                    cold.get,
                    store.full_export,
                ):
                    try:
                        read()
                    except StrengthBusy:
                        pass
                    else:
                        raise AssertionError(
                            "Read accepted a partial Influx replacement"
                        )
                assert store.cached is cached and cold.cached is None
                finish.set()
                worker.join(10)
                assert worker.exitcode == 0
                result = store.get(force=True)[0]
                assert result["sets"][0]["weight"] == 20
                assert result["workouts"][0]["name"] == "Generation 2"
                body, _, counts = store.full_export()
                assert body.startswith(b"PK")
                assert counts["sets"] == 1 and counts["sessions"] == 1
            finally:
                finish.set()
                worker.join(5)
                if worker.is_alive():
                    worker.terminate()
                    worker.join(5)
                worker.close()
    finally:
        admin.drop_database(options["database"])
        admin.close()
    print(
        "PASS: real Influx partial replacement rejected; cache preserved; coherent refresh and export after writer completion"
    )


if __name__ == "__main__":
    main()
