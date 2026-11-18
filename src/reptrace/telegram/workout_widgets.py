"""Private, read-only workout snapshots for Telegram's HTML widget renderer."""

from contextlib import closing
import json
import logging
import math
import os
from pathlib import Path
import re
import sqlite3
import time
import zlib

PAGE_SIZE = 4
MAX_WIDGETS = 100
MAX_AGE = 30 * 86400


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def label(value, limit=120):
    text = str(value or "").replace("\x00", "")
    raw = text.encode("utf-8")
    return (
        text if len(raw) <= limit else raw[: limit - 3].decode("utf-8", "ignore") + "…"
    )


def number(value):
    if not isinstance(value, (float, int)) or not math.isfinite(value):
        return "—"
    return (
        f"{value:.1f}".rstrip("0").rstrip(".") if abs(value) < 1e9 else f"{value:.2g}"
    )


def snapshot(facts):
    """Keep only displayed facts, never recovery data, coaching memory or targets."""
    workout, totals = facts["workout"], facts["totals"]
    return {
        "title": label(workout["name"]),
        "date": label(workout["date"], 20),
        "summary": f"{number(totals['sets'])} sets · {number(totals['reps'])} reps",
        "volume": f"{number(totals['volume'])} kg·reps",
        "coverage": f"{number(totals['volumeKnown'])}/{number(totals['sets'])} sets with volume",
        "exercises": [
            {
                "name": label(exercise["exercise"]),
                "rows": [
                    [number(row.get("weight")), number(row.get("reps"))]
                    for row in exercise["sets"]
                ],
            }
            for exercise in facts["exercises"]
        ],
    }


def page(data, exercise=0, offset=0):
    exercises = data["exercises"]
    if not exercises:
        if exercise or offset:
            raise ValueError("Invalid page")
        selected = {"name": "No recorded sets", "rows": []}
    elif 0 <= exercise < len(exercises):
        selected = exercises[exercise]
    else:
        raise ValueError("Invalid exercise")
    pages = max(1, math.ceil(len(selected["rows"]) / PAGE_SIZE))
    if not 0 <= offset < pages:
        raise ValueError("Invalid page")
    result = {
        key: data[key] for key in ("title", "date", "summary", "volume", "coverage")
    }
    result.update(
        v=1,
        e=exercise,
        p=offset,
        ec=len(exercises),
        pc=pages,
        exercise=selected["name"],
        count=len(selected["rows"]),
        rows=selected["rows"][offset * PAGE_SIZE : (offset + 1) * PAGE_SIZE],
    )
    encoded = compact(result)
    if len(encoded.encode("utf-8")) > 1024:
        raise ValueError("Widget state exceeds Telegram's limit")
    return encoded


def widget_html():
    html = Path(__file__).with_name("workout_widget.html").read_text()
    raw = html.encode("utf-8")
    if "\x00" in html or len(raw) > 32768 or len(zlib.compress(raw, 9)) > 4096:
        raise ValueError("Widget HTML exceeds Telegram's limit")
    return html


class WorkoutWidgets:
    def __init__(self, path, owner, api, clock=time.time):
        self.path, self.owner, self.api, self.clock = str(path), owner, api, clock

    def connect(self):
        db = sqlite3.connect(self.path, timeout=2)
        os.chmod(self.path, 0o600)
        db.execute("""CREATE TABLE IF NOT EXISTS widgets (
            owner INTEGER, request TEXT, message INTEGER, created REAL, snapshot TEXT,
            PRIMARY KEY(owner,request), UNIQUE(owner,message))""")
        return db

    def prune(self, db):
        db.execute("DELETE FROM widgets WHERE created < ?", (self.clock() - MAX_AGE,))
        db.execute(
            """DELETE FROM widgets WHERE rowid NOT IN (
            SELECT rowid FROM widgets ORDER BY created DESC, rowid DESC LIMIT ?)""",
            (MAX_WIDGETS,),
        )

    def sent(self, request):
        with closing(self.connect()) as db:
            return db.execute(
                "SELECT message FROM widgets WHERE owner=? AND request=?",
                (self.owner, request),
            ).fetchone()

    def send(self, request, facts):
        if self.sent(request):
            return
        data = snapshot(facts)
        result = self.api.call(
            "sendWidget",
            {
                "chat_id": self.owner,
                "html": widget_html(),
                "chat_data": page(data),
                "allow_queries": True,
                "protect_content": True,
                "caption": f"{data['title']} · {data['date']}\nRead-only snapshot. Use /widget for fresh data or /report for the full report.",
                "reply_markup": {
                    "inline_keyboard": [
                        [
                            {
                                "text": "Latest full report",
                                "callback_data": "report:latest",
                            }
                        ]
                    ]
                },
            },
        )
        with closing(self.connect()) as db, db:
            db.execute(
                "INSERT OR REPLACE INTO widgets VALUES (?,?,?,?,?)",
                (
                    self.owner,
                    request,
                    result["message_id"],
                    self.clock(),
                    compact(data),
                ),
            )
            self.prune(db)

    def query(self, query):
        """Answer immediately from a local snapshot, independently of the AI queue."""
        answer = compact(
            {"error": "This widget is unavailable. Send /widget for a new report."}
        )
        chat = query.get("chat", {})
        valid = (
            self.owner
            and query.get("from", {}).get("id") == self.owner
            and chat.get("id") == self.owner
            and chat.get("type") == "private"
            and type(query.get("message_id")) is int
            and not query.get("inline_message_id")
            and not query.get("widget_id")
            and query.get("type", {}).get("type") == "data"
        )
        command = query.get("data", "")
        match = (
            re.fullmatch(r"view:(\d{1,5}):(\d{1,5})", command)
            if isinstance(command, str)
            else None
        )
        success = False
        if valid and match:
            try:
                with closing(self.connect()) as db:
                    row = db.execute(
                        """SELECT snapshot FROM widgets
                        WHERE owner=? AND message=? AND created>=?""",
                        (self.owner, query["message_id"], self.clock() - MAX_AGE),
                    ).fetchone()
                if row:
                    answer = page(json.loads(row[0]), int(match[1]), int(match[2]))
                    success = True
            except (ValueError, sqlite3.Error, OSError):
                logging.warning("Workout widget snapshot unavailable.")
        from reptrace.telegram.bot import TelegramError

        try:
            self.api.call(
                "answerWidgetQuery", {"widget_query_id": query["id"], "data": answer}
            )
        except TelegramError as error:
            if error.code not in (400, 404):
                raise
            return  # Expired queries must not keep the polling offset stuck.
        if success:
            # Answer first to meet the 15-second deadline; an edit also preserves
            # the selected page when the message is reopened on another device.
            try:
                self.api.call(
                    "editMessageWidgetData",
                    {
                        "chat_id": self.owner,
                        "message_id": query["message_id"],
                        "chat_data": answer,
                    },
                )
            except TelegramError as error:
                # The caller already has its page. A later navigation can retry
                # persistence, including after flood waits or unchanged-state errors.
                if not error.not_modified:
                    logging.warning(
                        "Workout widget page persistence deferred (status %s).",
                        error.code,
                    )
