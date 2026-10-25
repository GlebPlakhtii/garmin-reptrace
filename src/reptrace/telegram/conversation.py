"""Durable Telegram ingress and serialized execution."""

import copy
import json
import os
import sqlite3
import threading
import time
import uuid


def ordinary(update):
    m = update.get("message", {})
    text = m.get("text", m.get("caption", ""))
    image = m.get("photo") or str(
        m.get("document", {}).get("mime_type", "")
    ).startswith("image/")
    return bool(
        (text or image) and not text.startswith("/") and not m.get("media_group_id")
    )


def target(update):
    return update.get("message", {}).get("reply_to_message", {}).get("message_id")


class Inbox:
    def __init__(self, path, clock=time.time):
        self.clock = clock
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        try:
            os.chmod(path, 0o600)
            self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS inbox (id INTEGER PRIMARY KEY, request TEXT, payload TEXT, received REAL);
            CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, status TEXT, first REAL, ready REAL, payload TEXT);
            CREATE TABLE IF NOT EXISTS refs (chat INTEGER, message INTEGER, request TEXT, context TEXT, PRIMARY KEY(chat,message));
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value INTEGER);
            """)
            self.db.execute("UPDATE requests SET status='retryable' WHERE status='active'")
            self.db.execute(
                "UPDATE requests SET status='queued' WHERE status='classifying'"
            )
            self.db.commit()
        except BaseException:
            self.db.close()
            raise

    def ingest(self, update):
        now = self.clock()
        command = update.get("callback_query", {}).get("data", "")
        # Consume old interruption buttons without reactivating the removed feature.
        control = command.startswith(("stop:", "instead:", "retry:"))
        with self.lock, self.db:
            if self.db.execute(
                "SELECT 1 FROM inbox WHERE id=?", (update["update_id"],)
            ).fetchone():
                return None
            last = self.db.execute(
                "SELECT id,first,ready,payload FROM requests ORDER BY first DESC,rowid DESC LIMIT 1"
            ).fetchone()
            group = False
            if last and ordinary(update) and not control:
                old = json.loads(last[3])
                status = self.db.execute(
                    "SELECT status FROM requests WHERE id=?", (last[0],)
                ).fetchone()[0]
                group = (
                    status in ("queued", "classifying")
                    and ordinary(old[-1])
                    and target(old[-1]) == target(update)
                    and old[-1].get("message", {}).get("chat")
                    == update.get("message", {}).get("chat")
                    and old[-1].get("message", {}).get("from")
                    == update.get("message", {}).get("from")
                    and now < last[2]
                    and now < last[1] + 6
                )
            if group:
                identity = last[0]
                old.append(update)
                self.db.execute(
                    "UPDATE requests SET payload=?,ready=? WHERE id=?",
                    (json.dumps(old), min(now + 2, last[1] + 6), identity),
                )
            else:
                identity = uuid.uuid4().hex
                self.db.execute(
                    "INSERT INTO requests VALUES (?,?,?,?,?)",
                    (
                        identity,
                        "control" if control else "queued",
                        now,
                        now + 2 if ordinary(update) else now,
                        json.dumps([update]),
                    ),
                )
            self.db.execute(
                "INSERT INTO inbox VALUES (?,?,?,?)",
                (update["update_id"], identity, json.dumps(update), now),
            )
            self.db.execute(
                "INSERT INTO meta VALUES ('offset',?) ON CONFLICT(key) DO UPDATE SET value=max(value,excluded.value)",
                (update["update_id"] + 1,),
            )
            return identity

    def offset(self, fallback=0):
        with self.lock:
            row = self.db.execute(
                "SELECT value FROM meta WHERE key='offset'"
            ).fetchone()
            return max(fallback, row[0] if row else 0)

    def status(self, identity, status):
        with self.lock, self.db:
            self.db.execute(
                "UPDATE requests SET status=? WHERE id=?", (status, identity)
            )

    def payload(self, identity):
        with self.lock:
            row = self.db.execute(
                "SELECT payload FROM requests WHERE id=?", (identity,)
            ).fetchone()
            return json.loads(row[0]) if row else []

    def next(self):
        with self.lock, self.db:
            row = self.db.execute(
                "SELECT id,ready,payload,status FROM requests WHERE status IN ('queued','classifying') ORDER BY first,rowid LIMIT 1"
            ).fetchone()
            if not row or row[1] > self.clock() or row[3] == "classifying":
                return None
            self.status(row[0], "active")
            return row[0], json.loads(row[2])

    def reference(self, chat, message, request=None, context=None):
        with self.lock, self.db:
            if context is not None:
                self.db.execute(
                    "INSERT OR REPLACE INTO refs VALUES (?,?,?,?)",
                    (chat, message, request, json.dumps(context)),
                )
            row = self.db.execute(
                "SELECT context FROM refs WHERE chat=? AND message=?", (chat, message)
            ).fetchone()
            return json.loads(row[0]) if row else None


class Delivery:
    def __init__(self, runtime, api):
        self.runtime, self.api = runtime, api

    def __getattr__(self, name):
        return getattr(self.api, name)

    def call(self, method, values, **kwargs):
        r = self.runtime
        r.check()
        result = self.api.call(method, values, **kwargs)
        if (
            method in ("sendMessage", "sendPhoto", "sendDocument")
            and isinstance(result, dict)
            and result.get("message_id")
        ):
            context = {
                "text": values.get("text", values.get("caption", "")),
                "attachment": kwargs.get("filename"),
                "buttons": values.get("reply_markup"),
                "sources": r.sources,
                "artifacts": [
                    {
                        k: v
                        for k, v in a.items()
                        if k
                        in (
                            "kind",
                            "draftId",
                            "id",
                            "name",
                            "type",
                            "baselineDate",
                            "filename",
                            "title",
                        )
                    }
                    for a in r.bot.state.get("chatOutbox", {})
                    .get(r.active, {})
                    .get("plans", [])
                ],
                "identity": getattr(r.bot, "reference_context", {}),
                "drafts": r.bot.state.get("chatOutbox", {})
                .get(r.active, {})
                .get("drafts", []),
            }
            r.store.reference(
                values["chat_id"], result["message_id"], r.active, context
            )
        r.check()
        return result


class Runtime:
    def __init__(self, bot, clock=time.time):
        self.bot = bot
        self.raw = bot.api
        self.store = Inbox(str(bot.path) + ".inbox.sqlite3", clock)
        self.active = None
        self.album_keys = []
        self.sources = []
        self.guard = threading.RLock()
        self.wake = threading.Event()
        bot.api = Delivery(self, self.raw)
        bot.runtime = self

    def check(self):
        if threading.current_thread().name == "telegram-execution":
            self.bot.path.with_suffix(".worker-health").touch()

    def control(self, text, buttons=None):
        values = {"chat_id": self.bot.owner, "text": text}
        if buttons:
            values["reply_markup"] = {"inline_keyboard": [buttons]}
        try:
            return self.raw.call("sendMessage", values)
        except Exception:
            return {}

    def receive(self, update):
        cb = update.get("callback_query", {})
        m = cb.get("message", {}) if cb else update.get("message", {})
        sender = (cb or m).get("from", {}).get("id")
        identity = self.store.ingest(update)
        if not identity:
            return
        if (
            m.get("chat", {}).get("type") != "private"
            or sender != m.get("chat", {}).get("id")
            or (self.bot.owner and sender != self.bot.owner)
        ):
            self.store.status(identity, "completed")
            return
        command = cb.get("data", "")
        if command.startswith(("stop:", "instead:")):
            self.store.status(identity, "completed")
            self.raw.call(
                "answerCallbackQuery",
                {
                    "callback_query_id": cb["id"],
                    "text": "Interruption was removed. Messages now queue until the answer finishes.",
                },
            )
            return
        if command.startswith("retry:"):
            self.store.status(identity, "completed")
            retry = command[6:]
            with self.store.lock, self.store.db:
                self.store.db.execute(
                    "UPDATE requests SET status='queued',ready=0 WHERE id=? AND status='retryable'",
                    (retry,),
                )
            self.raw.call("answerCallbackQuery", {"callback_query_id": cb["id"]})
            self.wake.set()
            return
        self.wake.set()

    def execute(self, identity, updates):
        with self.guard:
            self.active = identity
        self.album_keys = []
        self.bot.reference_context = {}
        self.sources = [u.get("message", {}) for u in updates]
        if updates[0].get("_task") == "albums":
            for key in updates[0].get("albumKeys", []):
                album = self.bot.state.get("pausedFoodAlbums", {}).pop(key, None)
                if album:
                    self.bot.state.setdefault("foodAlbums", {})[key] = album
            self.bot.save()
        try:
            if updates[0].get("_task") == "albums":
                self.bot.flush_food_albums()
            elif updates[0].get("_task") == "reports":
                self.bot.run_reports()
            elif all("message" in u for u in updates) and (
                len(updates) > 1 or ordinary(updates[0])
            ):
                update = copy.deepcopy(updates[-1])
                update["message"]["text"] = "\n\n".join(
                    u["message"].get("text", u["message"].get("caption", ""))
                    for u in updates
                )
                update["update_id"] = identity
                photos = [
                    u["message"]
                    for u in updates
                    if u["message"].get("photo") or u["message"].get("document")
                ]
                if photos:
                    self.bot.handle_images(
                        update["message"]["text"],
                        identity,
                        photos,
                        revision_of=self.bot.food_reply_target(update["message"]),
                    )
                elif len(updates) > 1 and any(not ordinary(u) for u in updates):
                    # Preserve previously queued, combined command/correction requests
                    # from the older runtime without creating new redirections.
                    self.bot.handle_chat(
                        update["message"]["text"],
                        identity,
                        source_messages=self.sources,
                    )
                else:
                    self.bot.handle(update)
            else:
                for update in updates:
                    update = copy.deepcopy(update)
                    update["update_id"] = identity
                    self.bot.handle(update)
            self.check()
            self.store.status(identity, "completed")
        except Exception as error:
            from reptrace.telegram.voice import VoiceError
            for key in self.album_keys:
                album = self.bot.state.get("foodAlbums", {}).pop(key, None)
                if album:
                    self.bot.state.setdefault("pausedFoodAlbums", {})[key] = album
            self.bot.save()
            # Includes uncertain confirmed writes: never replay automatically.
            self.store.status(identity, "retryable")
            self.control(
                str(error) if isinstance(error, VoiceError) else "Request interrupted. A confirmed write may already have completed. Check its current state before retrying.",
                [{"text": "Retry same request", "callback_data": "retry:" + identity}],
            )
        finally:
            with self.guard:
                self.active = None

    def worker(self):
        with self.store.lock:
            retries = self.store.db.execute(
                "SELECT id FROM requests WHERE status='retryable'"
            ).fetchall()
        for (identity,) in retries:
            payload = self.store.payload(identity)
            if payload and payload[0].get("_task") == "albums":
                for key in payload[0].get("albumKeys", []):
                    album = self.bot.state.get("foodAlbums", {}).pop(key, None)
                    if album:
                        self.bot.state.setdefault("pausedFoodAlbums", {})[key] = album
                self.bot.save()
            self.control(
                "An earlier request was interrupted. Check current records before retrying a confirmed save.",
                [{"text": "Retry same request", "callback_data": "retry:" + identity}],
            )
        while True:
            self.bot.path.with_suffix(".worker-health").touch()
            item = self.store.next()
            if item:
                self.execute(*item)
            else:
                albums = any(
                    a["ready_at"] <= self.bot.clock().isoformat()
                    for a in self.bot.state.get("foodAlbums", {}).values()
                )
                with self.store.lock:
                    queued = self.store.db.execute(
                        "SELECT 1 FROM requests WHERE status IN ('queued','classifying') LIMIT 1"
                    ).fetchone()
                report_due = (
                    self.bot.owner
                    and self.bot.fetch_data
                    and self.bot.clock().timestamp() - self.bot.last_report_check >= 60
                )
                if not queued and (albums or report_due):
                    identity = uuid.uuid4().hex
                    payload = [
                        {
                            "_task": "albums" if albums else "reports",
                            "albumKeys": (
                                list(self.bot.state.get("foodAlbums", {}))
                                if albums
                                else []
                            ),
                        }
                    ]
                    with self.store.lock, self.store.db:
                        self.store.db.execute(
                            "INSERT INTO requests VALUES (?,?,?,?,?)",
                            (
                                identity,
                                "active",
                                self.store.clock(),
                                0,
                                json.dumps(payload),
                            ),
                        )
                    self.execute(identity, payload)
                self.wake.wait(0.1)
                self.wake.clear()

    def interactive_pending(self):
        self.check()
        with self.store.lock:
            return bool(
                self.store.db.execute(
                    "SELECT 1 FROM requests WHERE status IN ('queued','classifying') LIMIT 1"
                ).fetchone()
            )

    def poll(self):
        updates = self.raw.call(
            "getUpdates",
            {
                "offset": self.store.offset(self.bot.state.get("offset", 0)),
                "timeout": 1,
                "allowed_updates": ["message", "callback_query"],
            },
        )
        for update in updates:
            self.receive(update)
