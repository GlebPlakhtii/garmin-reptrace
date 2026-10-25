"""Coherent snapshots use real process locks and disposable synthetic records."""

from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from contextlib import contextmanager
import json
import multiprocessing as mp
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from reptrace.storage.coordination import StrengthBusy, strength_lock


def write_records(root, generation, measurement):
    common = {"time": "2026-10-01T09:00:00Z", "ActivityID": "synthetic"}
    rows = (
        [
            dict(
                common,
                SetIndex="1",
                Exercise="Barbell Bench Press",
                weightKg=generation * 10,
                reps=5,
            )
        ]
        if measurement == "StrengthSet"
        else [
            dict(
                common,
                activityType="strength_training",
                activityName=f"Generation {generation}",
            )
        ]
    )
    (Path(root) / (measurement + ".json")).write_text(json.dumps(rows))


def separate_writer(root, start, attempting, acquired, release):
    if not start.wait(10):
        raise RuntimeError("Reader did not start")
    attempting.set()
    with strength_lock():
        write_records(root, 2, "StrengthSet")
        acquired.set()
        if not release.wait(10):
            raise RuntimeError("Writer was not released")
        write_records(root, 2, "ActivitySummary")


class CoherentReadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.env = patch.dict(
            os.environ,
            {
                "STRENGTH_MUTATION_LOCK_PATH": str(self.root / "strength.lock"),
                "WEB_STATE_PATH": str(self.root / "state.sqlite"),
                "GARMIN_WORKOUT_STATE_PATH": str(self.root / "garmin.sqlite"),
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        # Import after setting disposable paths, including in standalone test runs.
        from reptrace.web import server

        self.web = server
        self.client = Mock()
        for measurement in ("StrengthSet", "ActivitySummary"):
            write_records(self.root, 1, measurement)
        self.after_sets = None
        self.factory = Mock(return_value=(self.client, self.query))
        self.store = self.web.DataStore(self.factory, snapshot_timeout=0.05)
        self.ctx = mp.get_context("spawn")

    def query(self, query):
        if query == "SHOW MEASUREMENTS":
            return [{"name": name} for name in ("StrengthSet", "ActivitySummary")]
        for measurement in ("StrengthSet", "ActivitySummary"):
            if f'FROM "{measurement}"' in query:
                rows = json.loads((self.root / (measurement + ".json")).read_text())
                if measurement == "StrengthSet" and self.after_sets:
                    self.after_sets()
                return rows
        return []

    def writer(self):
        events = [self.ctx.Event() for _ in range(4)]
        process = self.ctx.Process(target=separate_writer, args=(self.root, *events))
        process.start()

        def cleanup():
            events[0].set()
            events[3].set()
            process.join(5)
            if process.is_alive():
                process.terminate()
                process.join(5)
            process.close()

        self.addCleanup(cleanup)
        return process, events

    def test_busy_cross_process_writer_preserves_cache_and_blocks_cold_reads_and_exports(
        self,
    ):
        cached = self.store.get()
        process, (start, attempting, acquired, release) = self.writer()
        start.set()
        self.assertTrue(acquired.wait(10))
        self.factory.reset_mock()
        self.assertIs(
            self.store.get(), cached
        )  # Still a valid complete cached snapshot.
        cold = self.web.DataStore(self.factory, snapshot_timeout=0.05)
        for read in (
            lambda: self.store.get(force=True),
            cold.get,
            self.store.full_export,
        ):
            before = time.monotonic()
            with self.assertRaises(StrengthBusy):
                read()
            self.assertLess(time.monotonic() - before, 1)
        self.assertIs(self.store.cached, cached)
        self.assertIsNone(cold.cached)
        self.factory.assert_not_called()
        release.set()
        process.join(10)
        self.assertEqual(process.exitcode, 0)
        current = self.store.get(force=True)[0]
        self.assertEqual(current["sets"][0]["weight"], 20)
        self.assertEqual(current["workouts"][0]["name"], "Generation 2")

    def test_dashboard_and_export_finish_the_snapshot_before_a_separate_writer_enters(
        self,
    ):
        for export in (False, True):
            with self.subTest(export=export):
                for measurement in ("StrengthSet", "ActivitySummary"):
                    write_records(self.root, 1, measurement)
                process, (start, attempting, acquired, release) = self.writer()
                release.set()

                def after_sets():
                    start.set()
                    self.assertTrue(attempting.wait(10))
                    self.assertFalse(
                        acquired.wait(0.05), "Writer entered during snapshot"
                    )

                self.after_sets = after_sets
                if export:
                    with patch.object(
                        self.web,
                        "export_sessions",
                        side_effect=lambda result, **_: result,
                    ):
                        result = self.store.full_export()
                else:
                    result = self.store.get(force=True)[0]
                self.after_sets = None
                self.assertEqual(result["sets"][0]["weight"], 10)
                self.assertEqual(result["workouts"][0]["name"], "Generation 1")
                process.join(10)
                self.assertEqual(process.exitcode, 0)
                self.assertTrue(acquired.is_set())

    def test_timeout_covers_in_process_writers_and_reentrant_use_remains_available(
        self,
    ):
        acquired, release = threading.Event(), threading.Event()

        def writer():
            with strength_lock():
                acquired.set()
                release.wait(5)

        thread = threading.Thread(target=writer)
        thread.start()
        try:
            self.assertTrue(acquired.wait(5))
            with self.assertRaises(StrengthBusy):
                self.store.get()
            self.factory.assert_not_called()
        finally:
            release.set()
            thread.join(5)
        with strength_lock(), strength_lock(timeout=0):
            self.assertEqual(self.store.get()[0]["sets"][0]["weight"], 10)

    def test_waiting_refresh_does_not_hold_cache_mutex(self):
        cached = self.store.get()
        self.store.snapshot_timeout = 0.5
        acquired, release = threading.Event(), threading.Event()
        waiting, finished = threading.Event(), threading.Event()
        outcomes = []

        def writer():
            with strength_lock():
                acquired.set()
                release.wait(5)

        @contextmanager
        def observed_lock(**options):
            waiting.set()
            with strength_lock(**options):
                yield

        def refresh():
            try:
                self.store.get(force=True)
            except StrengthBusy:
                outcomes.append("busy")
            finally:
                finished.set()

        writer_thread = threading.Thread(target=writer)
        reader_thread = threading.Thread(target=refresh)
        writer_thread.start()
        try:
            self.assertTrue(acquired.wait(5))
            with patch.object(self.web, "strength_lock", observed_lock):
                reader_thread.start()
                self.assertTrue(waiting.wait(5))
                self.assertIs(self.store.get(), cached)
                self.assertFalse(finished.is_set())
                reader_thread.join(5)
            self.assertEqual(outcomes, ["busy"])
        finally:
            release.set()
            writer_thread.join(5)
            if reader_thread.ident is not None:
                reader_thread.join(5)

    def test_http_busy_responses_are_retryable_without_exposing_partial_data(self):
        store = Mock()
        store.get.side_effect = StrengthBusy()
        store.full_export.side_effect = StrengthBusy()
        server = ThreadingHTTPServer(("127.0.0.1", 0), self.web.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        try:
            with patch.object(self.web, "STORE", store):
                for path in (
                    "/api/data?refresh=1",
                    "/api/health",
                    "/api/sessions.xlsx",
                    "/api/sessions.xlsx?full=1",
                    "/api/plan.png?type=upper1",
                ):
                    client.request("GET", path)
                    response = client.getresponse()
                    body = response.read().decode()
                    self.assertEqual(response.status, 503, path)
                    self.assertEqual(response.getheader("Retry-After"), "1", path)
                    self.assertIn("Training records are being updated", body)
        finally:
            client.close()
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
