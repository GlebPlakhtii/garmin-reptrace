"""Synthetic card sandbox. No Garmin, coach, or training storage dependencies."""

from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import sqlite3


class CardDemo:
    def __init__(self, api, path, owner):
        self.api, self.owner = api, owner
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS cards (id TEXT PRIMARY KEY, state TEXT NOT NULL)"
            )
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    def read(self, identity):
        with self.connect() as db:
            row = db.execute(
                "SELECT state FROM cards WHERE id=?", (identity,)
            ).fetchone()
            return json.loads(row[0]) if row else None

    def store(self, state):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO cards VALUES (?,?)",
                (state["id"], json.dumps(state)),
            )

    def render(self, s):
        text = (
            "DEMO — no Garmin changes\nUpper body · synthetic workout\n\n"
            f"1. {s['exercise']} · 3 × 8 · {s['weight']} kg per dumbbell · rest 90 s\n"
            "2. Seated cable row · 3 × 10 · 35 kg stack · rest 90 s\n"
            "3. Plank · 3 × 30 s · no load target · open rest\n\n"
            + (
                "SIMULATED: saved + delivery requested. Nothing sent to Garmin or watch."
                if s["saved"]
                else "Draft demo · tap a button to try editing."
            )
        )
        details = (
            "Example targets only. All three sets use the displayed target. "
            "The first load is per dumbbell; row load is a machine-stack reading. "
            "Open rest ends manually. No calendar entry or automatic start. "
            "Change weight cycles 20 / 22.5 / 25 kg; Replace exercise cycles two demo alternatives."
        )
        buttons = [
            [
                {
                    "text": label,
                    "callback_data": f"demo:{s['id']}:{s['revision']}:{action}",
                }
                for label, action in row
            ]
            for row in [
                [("Change weight", "weight"), ("Replace exercise", "exercise")],
                [("Hide details" if s["details"] else "Show details", "details")],
                [("Simulate Save & send", "save"), ("Reset demo", "reset")],
            ]
        ]
        blocks = [
            {"type": "paragraph", "text": text},
            {
                "type": "details",
                "summary": "Workout details",
                "blocks": [{"type": "paragraph", "text": details}],
                **({"is_open": True} if s["details"] else {}),
            },
        ]
        return {
            "rich_message": {"blocks": blocks},
            "reply_markup": {"inline_keyboard": buttons},
        }, text + ("\n\n" + details if s["details"] else "")

    def send(self, identity=None):
        identity = identity or secrets.token_hex(6)
        s = self.read(identity)
        if s:
            # An uncertain send is deliberately not repeated automatically.
            return s
        s = dict(
            id=identity,
            owner=self.owner,
            weight=20,
            exercise="Dumbbell bench press",
            details=False,
            saved=False,
            revision=0,
            message=None,
            rich=True,
            status="sending",
        )
        self.store(s)
        values, text = self.render(s)
        try:
            result = self.api.call("sendRichMessage", {"chat_id": self.owner, **values})
        except Exception as error:
            if getattr(error, "code", None) not in (400, 404):
                raise
            s["rich"] = False
            self.store(s)
            result = self.api.call(
                "sendMessage",
                {
                    "chat_id": self.owner,
                    "text": text,
                    "reply_markup": values["reply_markup"],
                },
            )
        s.update(message=result["message_id"], status="sent")
        self.store(s)
        return s

    def callback(self, callback):
        parts = callback.get("data", "").split(":")
        if len(parts) != 4 or parts[0] != "demo":
            return
        s = self.read(parts[1])
        message = callback.get("message", {})
        if (
            not s
            or s["owner"] != self.owner
            or callback.get("from", {}).get("id") != self.owner
            or message.get("chat", {}).get("id") != self.owner
        ):
            return
        if message.get("message_id") != s["message"]:
            return
        if parts[2] == str(s["revision"]):
            action = parts[3]
            if action == "weight":
                s["weight"] = {20: 22.5, 22.5: 25, 25: 20}[s["weight"]]
                s["saved"] = False
            elif action == "exercise":
                s["exercise"] = (
                    "Incline dumbbell press"
                    if s["exercise"] == "Dumbbell bench press"
                    else "Dumbbell bench press"
                )
                s["saved"] = False
            elif action == "details":
                s["details"] = not s["details"]
            elif action == "save":
                s["saved"] = True
            elif action == "reset":
                s.update(
                    weight=20,
                    exercise="Dumbbell bench press",
                    details=False,
                    saved=False,
                )
            else:
                return
            s["revision"] += 1
            self.store(s)
        # A duplicate or retry redraws committed state, without reapplying the edit.
        values, text = self.render(s)
        if not s["rich"]:
            values.pop("rich_message")
            values["text"] = text
        try:
            self.api.call(
                "editMessageText",
                {"chat_id": self.owner, "message_id": s["message"], **values},
            )
        except Exception as error:
            if not getattr(error, "not_modified", False):
                raise
