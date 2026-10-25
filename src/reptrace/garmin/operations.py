"""Durable, additive integration journal; remote uncertainty is never replayed."""

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from reptrace.storage.state import Conflict


class OperationJournal:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30)
        try:
            self.path.chmod(0o600)
            db.row_factory = sqlite3.Row
            db.execute("""CREATE TABLE IF NOT EXISTS integration_operations (
                id TEXT PRIMARY KEY, activity TEXT, kind TEXT NOT NULL, request TEXT NOT NULL,
                data TEXT NOT NULL, status TEXT NOT NULL, updated REAL NOT NULL)""")
            with db:
                yield db
        finally:
            db.close()

    def stage(self, identity, kind, request, data, activity=None):
        encoded = json.dumps(request, sort_keys=True, allow_nan=False)
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM integration_operations WHERE id=?", (identity,)
            ).fetchone()
            if row:
                if row["request"] != encoded or row["kind"] != kind:
                    raise Conflict(
                        "Request identity already belongs to different changes"
                    )
                return json.loads(row["data"])
            data = dict(data, id=identity, kind=kind, status="preview")
            db.execute(
                "INSERT INTO integration_operations VALUES (?,?,?,?,?,?,?)",
                (
                    identity,
                    activity,
                    kind,
                    encoded,
                    json.dumps(data, allow_nan=False),
                    "preview",
                    time.time(),
                ),
            )
            return data

    def get(self, identity):
        with self.connect() as db:
            row = db.execute(
                "SELECT data FROM integration_operations WHERE id=?", (identity,)
            ).fetchone()
            if not row:
                raise ValueError("Operation not found")
            return json.loads(row[0])

    def save(self, data):
        with self.connect() as db:
            db.execute(
                "UPDATE integration_operations SET data=?,status=?,updated=? WHERE id=?",
                (
                    json.dumps(data, allow_nan=False),
                    data["status"],
                    time.time(),
                    data["id"],
                ),
            )

    def unresolved(self, activity):
        with self.connect() as db:
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT data FROM integration_operations WHERE activity=? AND status NOT IN ('preview','done','cancelled')",
                    (activity,),
                )
            ]

    def recent(self):
        with self.connect() as db:
            rows = db.execute(
                "SELECT data FROM integration_operations ORDER BY CASE WHEN status NOT IN ('preview','done','cancelled') THEN 0 ELSE 1 END, updated DESC LIMIT 100"
            ).fetchall()
        return [
            {
                key: value
                for key, value in json.loads(row[0]).items()
                if key
                in (
                    "id",
                    "kind",
                    "activityId",
                    "status",
                    "remoteStatus",
                    "localStatus",
                    "preview",
                    "localError",
                )
            }
            for row in rows
        ]
