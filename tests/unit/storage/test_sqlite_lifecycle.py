"""SQLite contexts commit or roll back, and always release their connection."""

from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from reptrace.garmin.operations import OperationJournal
from reptrace.garmin.workouts import GarminWorkouts
from reptrace.storage.state import WebState
from reptrace.telegram.card_demo import CardDemo
from reptrace.telegram.conversation import Inbox


class SQLiteLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def stores(self):
        return [
            WebState(self.root / "web.sqlite"),
            OperationJournal(self.root / "operations.sqlite"),
            CardDemo(Mock(), self.root / "cards.sqlite", 42),
        ]

    def assert_closed(self, connection):
        with self.assertRaisesRegex(sqlite3.ProgrammingError, "closed database"):
            connection.execute("SELECT 1")

    def test_success_commits_and_body_failure_rolls_back_before_closing(self):
        for store in self.stores():
            with self.subTest(store=type(store).__name__):
                with store.connect() as connection:
                    connection.execute("CREATE TABLE lifecycle (value TEXT)")
                    connection.execute("INSERT INTO lifecycle VALUES ('committed')")
                self.assert_closed(connection)
                with self.assertRaisesRegex(ValueError, "interrupted"):
                    with store.connect() as connection:
                        connection.execute("INSERT INTO lifecycle VALUES ('rolled back')")
                        raise ValueError("interrupted")
                self.assert_closed(connection)
                with store.connect() as connection:
                    self.assertEqual(
                        [row[0] for row in connection.execute("SELECT value FROM lifecycle")],
                        ["committed"],
                    )
                self.assert_closed(connection)

    def test_commit_failure_rolls_back_and_closes(self):
        for store in self.stores():
            with self.subTest(store=type(store).__name__):
                with store.connect() as connection:
                    connection.executescript("""
                        CREATE TABLE parent (id INTEGER PRIMARY KEY);
                        CREATE TABLE child (parent_id INTEGER REFERENCES parent(id)
                            DEFERRABLE INITIALLY DEFERRED);
                    """)
                with self.assertRaises(sqlite3.IntegrityError):
                    with store.connect() as connection:
                        connection.execute("PRAGMA foreign_keys=ON")
                        connection.execute("INSERT INTO child VALUES (123)")
                self.assert_closed(connection)
                with store.connect() as connection:
                    self.assertEqual(connection.execute("SELECT count(*) FROM child").fetchone()[0], 0)

    def test_initialization_failure_closes_new_connections(self):
        class FailedSchema(sqlite3.Connection):
            def execute(self, sql, *args):
                if "CREATE TABLE" in sql:
                    raise sqlite3.OperationalError("schema unavailable")
                return super().execute(sql, *args)

            def executescript(self, sql):
                raise sqlite3.OperationalError("schema unavailable")

        real_connect = sqlite3.connect
        connections = []

        def failing_connection(*args, **kwargs):
            connection = real_connect(*args, factory=FailedSchema, **kwargs)
            connections.append(connection)
            return connection

        def open_context(store):
            with store.connect():
                self.fail("Failed initialization must not expose a connection")

        factories = [
            lambda: open_context(WebState(self.root / "web.sqlite")),
            lambda: open_context(OperationJournal(self.root / "operations.sqlite")),
            lambda: GarminWorkouts(self.root / "workouts.sqlite").connect(),
            lambda: CardDemo(Mock(), self.root / "cards.sqlite", 42),
            lambda: Inbox(self.root / "inbox.sqlite"),
        ]
        with patch("sqlite3.connect", side_effect=failing_connection):
            for factory in factories:
                with self.assertRaisesRegex(sqlite3.OperationalError, "schema unavailable"):
                    factory()
                self.assert_closed(connections[-1])


if __name__ == "__main__":
    unittest.main()
