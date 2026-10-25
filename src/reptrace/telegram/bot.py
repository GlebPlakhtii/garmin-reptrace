"""Private Telegram workout images, Monday summaries and post-workout AI reports."""

import hmac
from html import escape
import hashlib
from datetime import datetime, timedelta, time as wall_time, timezone
from zoneinfo import ZoneInfo
import json
import re
import logging
import os
from pathlib import Path
import secrets
import threading
import time
import urllib.error
import urllib.request
import uuid

from reptrace.exports.sessions import export_sessions, MIME
from reptrace.telegram.formatting import format_chat_text, split_rich_text
from reptrace.training.planning import TYPES, workout_type
from reptrace.exports.plans import render_plan
from reptrace.exports.garmin_preview import render_garmin_preview_image
from reptrace.reports.facts import (
    weekly_facts,
    weekly_text,
    session_facts,
    session_text,
    ReportWriter,
    monday,
)
from reptrace.reports.render import render_report_html, render_report_preview
from reptrace.coaching.assistant import TrainingCoach, TrainingTools, quality_review
from reptrace.reports.monthly import (
    monthly_facts,
    render_monthly_html,
    render_monthly_preview,
    render_quality_html,
)
from reptrace.nutrition.estimation import FoodEstimator
from reptrace.training.review import compare_plan

MENU = {
    "inline_keyboard": [
        [
            {"text": "Upper 1", "callback_data": "plan:upper1"},
            {"text": "Upper 2", "callback_data": "plan:upper2"},
        ],
        [
            {"text": "Lower 1", "callback_data": "plan:lower1"},
            {"text": "Lower 2", "callback_data": "plan:lower2"},
        ],
        [{"text": "All four sessions", "callback_data": "plan:all"}],
        [
            {"text": "Weekly progress", "callback_data": "report:weekly"},
            {"text": "Session report & charts", "callback_data": "report:latest"},
        ],
        [
            {"text": "Monthly review", "callback_data": "report:monthly"},
            {"text": "Data quality", "callback_data": "report:quality"},
        ],
        [{"text": "Export Excel", "callback_data": "export:all"}],
        [
            {"text": "Ask coach", "callback_data": "coach:help"},
            {"text": "Adapt workout", "callback_data": "coach:adapt"},
        ],
    ]
}


class TelegramError(RuntimeError):
    def __init__(self, code, retry_after=5):
        super().__init__(f"Telegram request failed (status {code})")
        self.code = code
        self.retry_after = retry_after


class TelegramDraft:
    """Best-effort live preview; durable delivery stays in the chat outbox."""

    def __init__(self, api, chat_id):
        self.api = api
        self.chat_id = chat_id
        self.draft_id = secrets.randbelow(2**31 - 1) + 1
        self.next_update = 0
        self.disabled = False
        self.last_text = None

    def update(self, text):
        now = time.monotonic()
        if self.disabled or now < self.next_update:
            return
        # Keep the newest text visible even for answers longer than one message.
        preview = text.encode("utf-16-le")[-8000:].decode("utf-16-le", errors="ignore")
        if not preview.strip() or preview == self.last_text:
            return
        self.next_update = now + 1.1
        try:
            self.api.call(
                "sendMessageDraft",
                {"chat_id": self.chat_id, "draft_id": self.draft_id, "text": preview},
            )
            self.last_text = preview
        except TelegramError as error:
            if error.code == 429:
                self.next_update = time.monotonic() + max(1.1, error.retry_after)
            else:
                self.disabled = True
            logging.warning(
                "Telegram live preview unavailable (status %s); final delivery retained.",
                error.code,
            )


class Telegram:
    def __init__(self, token):
        self.base = "https://api.telegram.org/bot" + token + "/"
        self.last_send = {}

    def call(self, method, values, photo=None, document=None, filename="report.html"):
        if method in ("sendPhoto", "sendMessage", "sendDocument"):
            elapsed = time.monotonic() - self.last_send.get(values["chat_id"], 0)
            if elapsed < 1.1:
                time.sleep(1.1 - elapsed)
        if photo is not None and document is not None:
            raise ValueError("Upload one file at a time")
        if photo is None and document is None:
            body = json.dumps(values).encode()
            content_type = "application/json"
        else:
            boundary = "form-" + uuid.uuid4().hex
            parts = []
            for key, value in values.items():
                value = (
                    json.dumps(value) if isinstance(value, (dict, list)) else str(value)
                )
                parts.append(
                    f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
                )
            field = "photo" if photo is not None else "document"
            media_type = (
                "image/png"
                if photo is not None
                else MIME
                if filename.lower().endswith(".xlsx")
                else "text/html; charset=utf-8"
            )
            filename = "next-session.png" if photo is not None else Path(filename).name
            if any(c in filename for c in ('"', "\r", "\n")):
                raise ValueError("Invalid document filename")
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\nContent-Type: {media_type}\r\n\r\n'.encode()
                + (photo if photo is not None else document)
                + b"\r\n"
            )
            parts.append(f"--{boundary}--\r\n".encode())
            body = b"".join(parts)
            content_type = "multipart/form-data; boundary=" + boundary
        request = urllib.request.Request(
            self.base + method, data=body, headers={"Content-Type": content_type}
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            try:
                details = json.loads(error.read())
            except (ValueError, OSError):
                details = {}
            raise TelegramError(
                error.code, details.get("parameters", {}).get("retry_after", 5)
            ) from None
        except (OSError, ValueError):
            raise TelegramError("network") from None
        if not result.get("ok"):
            raise TelegramError(result.get("error_code", "unknown"))
        if method in ("sendPhoto", "sendMessage", "sendDocument"):
            self.last_send[values["chat_id"]] = time.monotonic()
        return result["result"]

    def download_photo(self, file_id):
        info = self.call("getFile", {"file_id": file_id})
        path = info.get("file_path", "")
        if not re.fullmatch(r"[A-Za-z0-9_./-]{1,300}", path) or ".." in path:
            raise ValueError("Invalid Telegram photo path")
        try:
            with urllib.request.urlopen(
                self.base.replace("/bot", "/file/bot", 1) + path, timeout=45
            ) as response:
                image = response.read(12_000_001)
        except OSError:
            raise RuntimeError("Could not download the image.") from None
        if not image or len(image) > 12_000_000:
            raise ValueError("Image is empty or too large.")
        return image, "image/png" if path.lower().endswith(
            ".png"
        ) else "image/webp" if path.lower().endswith(".webp") else "image/jpeg"


class Bot:
    def __init__(
        self,
        api,
        fetch_plans,
        path,
        allowed_user=None,
        pairing_code=None,
        fetch_data=None,
        reporter=None,
        report_timezone="Europe/Kyiv",
        weekly_time="09:00",
        weekly_enabled=True,
        post_enabled=True,
        settle_seconds=300,
        clock=None,
        coach=None,
        monthly_enabled=False,
        fetch_export=None,
        database=None,
        garmin=None,
        food_estimator=None,
        food_action=None,
        garmin_review=None,
    ):
        self.database = database
        self.garmin = garmin or fetch_garmin
        self.garmin_review = garmin_review
        self.food_estimator = food_estimator or FoodEstimator()
        self.food_action = food_action or fetch_food
        self.api = api
        self.fetch_plans = fetch_plans
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state = (
            json.loads(self.path.read_text()) if self.path.exists() else {"offset": 0}
        )
        self.owner = int(allowed_user) if allowed_user else self.state.get("owner")
        if self.owner is not None and self.owner <= 0:
            raise ValueError("Telegram owner must be a positive user ID")
        self.pairing_code = (
            pairing_code or self.state.get("pairingCode") or secrets.token_urlsafe(12)
        )
        self.fetch_data = fetch_data
        self.fetch_export = fetch_export
        self.reporter = reporter
        self.coach = coach
        self.monthly_enabled = monthly_enabled
        self.zone = ZoneInfo(report_timezone)
        self.weekly_time = wall_time.fromisoformat(weekly_time)
        if self.weekly_time.tzinfo:
            raise ValueError("Weekly time must be local HH:MM")
        self.weekly_enabled = weekly_enabled
        self.post_enabled = post_enabled
        self.settle_seconds = max(0, int(settle_seconds))
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.last_report_check = 0
        self.state.setdefault("reportsStartedAt", self.clock().isoformat())
        self.state.update(owner=self.owner, pairingCode=self.pairing_code)
        self.save()

    def save(self):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state))
        temporary.chmod(0o600)
        temporary.replace(self.path)

    def handle(self, update):
        callback = update.get("callback_query")
        message = callback.get("message", {}) if callback else update.get("message", {})
        sender = (callback or message).get("from", {}).get("id")
        chat = message.get("chat", {})
        if chat.get("type") != "private" or not sender or sender != chat.get("id"):
            return
        text = (message.get("text") or "").strip()
        if not self.owner:
            parts = text.split(maxsplit=1)
            if not (
                len(parts) == 2
                and parts[0].split("@")[0] == "/start"
                and hmac.compare_digest(parts[1], self.pairing_code)
            ):
                return
            self.owner = sender
            self.state["owner"] = sender
            self.save()
        if sender != self.owner:
            return
        chat_id = chat["id"]
        if callback:
            self.api.call("answerCallbackQuery", {"callback_query_id": callback["id"]})
            command = callback.get("data", "")
            if command.startswith("food:save:") or command.startswith("food:cancel:"):
                self.handle_food_review(command)
                return
            if command.startswith("food:delete:"):
                identity = command.removeprefix("food:delete:")
                try:
                    self.food_action({"action": "delete", "id": identity})
                    self.api.call(
                        "sendMessage",
                        {"chat_id": chat_id, "text": "Food entry deleted."},
                    )
                except (ValueError, RuntimeError) as error:
                    self.api.call(
                        "sendMessage", {"chat_id": chat_id, "text": str(error)}
                    )
                return
            if command == "export:all":
                try:
                    self.send_excel({"full": True})
                except ValueError as error:
                    self.api.call(
                        "sendMessage", {"chat_id": chat_id, "text": str(error)}
                    )
                return
            if command.startswith("garmin:"):
                try:
                    tools = TrainingTools(
                        {},
                        self.state,
                        self.save,
                        request_id=str(update["update_id"]),
                        garmin=self.garmin,
                    )
                    result = tools.call(
                        "propose_garmin_workout_update",
                        {
                            "workout_id": int(command[7:]),
                            "use_suggestions": True,
                            "targets": [],
                        },
                    )
                    if result.get("draftId"):
                        self.send_edit_preview(result["draftId"])
                    else:
                        self.api.call(
                            "sendMessage",
                            {
                                "chat_id": chat_id,
                                "text": result.get("message", "No changes to save."),
                            },
                        )
                except (ValueError, RuntimeError) as error:
                    self.api.call(
                        "sendMessage", {"chat_id": chat_id, "text": str(error)}
                    )
                return
            if command.startswith("edit:"):
                self.handle_edit(command)
                return
            if command.startswith("coach:"):
                text = "Send a question about your training history, for example: Why has my bench press stalled? Use /adapt Upper 1, 40 minutes, no cable machine to draft an adjusted workout. /memory shows saved preferences; /remember saves a lasting preference; /reset clears the conversation. You can also ask to add, edit or delete workouts, sets, goals, muscle mappings, progression rules or recovery overrides; review the preview and press Save."
                self.api.call("sendMessage", {"chat_id": chat_id, "text": text})
                return
            if command.startswith("report:"):
                self.handle_report(command[7:], str(update["update_id"]))
                return
            if not command.startswith("plan:"):
                return
            kind = command[5:]
        else:
            food_reply = self.food_reply_target(message)
            if food_reply and text and not text.startswith("/"):
                if self.coach and self.coach.configured:
                    self.handle_chat(
                        text,
                        str(update["update_id"]),
                        source_messages=[message],
                        revision_of=food_reply,
                    )
                else:
                    self.handle_food(
                        text, str(update["update_id"]), message, revision_of=food_reply
                    )
                return
            if message.get("photo") or str(
                message.get("document", {}).get("mime_type", "")
            ).startswith("image/"):
                if message.get("media_group_id"):
                    self.queue_food_album(message, str(update["update_id"]))
                    return
                self.handle_images(
                    message.get("caption", ""),
                    str(update["update_id"]),
                    [message],
                    revision_of=food_reply,
                )
                return
            parts = text.split(maxsplit=1)
            command = parts[0].split("@")[0].lower() if parts else ""
            if command == "/food":
                if len(parts) == 1:
                    self.api.call(
                        "sendMessage",
                        {
                            "chat_id": chat_id,
                            "text": "Send a food photo, or select up to 10 food and product-label photos and send them together as one album. Add a caption with amounts eaten; your hand may be in frame for scale. You will get one estimate to review and Save. You can also type /food 3 bananas.",
                        },
                    )
                else:
                    self.handle_food(parts[1], str(update["update_id"]), message)
                return
            if command == "/foodlog":
                entries = (
                    self.fetch_data().get("foodLog", []) if self.fetch_data else []
                )
                today = self.clock().astimezone(self.zone).date().isoformat()
                todays = [
                    e
                    for e in entries
                    if datetime.fromisoformat(e["time"])
                    .astimezone(self.zone)
                    .date()
                    .isoformat()
                    == today
                ]
                totals = {
                    key: sum(e[key] for e in todays)
                    for key in ("calories", "protein_g", "carbs_g", "fat_g")
                }
                lines = [
                    f"Food today · {today}",
                    f"{totals['calories']:g} kcal · P {totals['protein_g']:g} g · C {totals['carbs_g']:g} g · F {totals['fat_g']:g} g",
                ]
                lines += [f"• {e['name']}: {e['calories']:g} kcal" for e in todays[:15]]
                if not todays:
                    lines.append("No food logged yet. Send a photo or /food 3 bananas.")
                self.api.call(
                    "sendMessage", {"chat_id": chat_id, "text": "\n".join(lines)}
                )
                return
            if command == "/garmin":
                try:
                    workouts = self.garmin({"operation": "list"})["workouts"]
                    buttons = {
                        "inline_keyboard": [
                            [
                                {
                                    "text": "Preview " + w["name"],
                                    "callback_data": "garmin:" + str(w["id"]),
                                }
                            ]
                            for w in workouts
                        ]
                    }
                    self.api.call(
                        "sendMessage",
                        {
                            "chat_id": chat_id,
                            "text": "Choose a Garmin workout to preview suggested weights/reps. For manual changes, send a message such as: Set Upper 1 bench press to 80 kg and 8 reps.",
                            "reply_markup": buttons,
                        },
                    )
                except (ValueError, RuntimeError) as error:
                    self.api.call(
                        "sendMessage", {"chat_id": chat_id, "text": str(error)}
                    )
                return
            if command == "/menu":
                self.api.call(
                    "sendMessage",
                    {
                        "chat_id": chat_id,
                        "text": "Choose an action:",
                        "reply_markup": MENU,
                    },
                )
                return
            if command in ("/memory", "/preferences"):
                profile = self.state.get("coachPreferences", {})
                memory = self.state.get("coachMemory", [])
                lines = ["Saved training preferences"] + [
                    f"• {key}: {value}" for key, value in profile.items()
                ]
                if not profile:
                    lines.append("None saved yet.")
                lines += ["\nTraining memory"] + [
                    f"• [{item['id']}] {item['text'][:220]}" for item in memory
                ]
                if not memory:
                    lines.append("None saved yet.")
                lines += [
                    "\nConversation summary",
                    self.state.get("coachSummary")
                    or "No older conversation summarized yet.",
                ]
                lines.append(
                    "\nUse /remember to save a lasting preference, or /forget <key or memory ID>. /forget all clears both."
                )
                for part in split_text("\n".join(lines)):
                    self.api.call("sendMessage", {"chat_id": chat_id, "text": part})
                return
            if command in ("/export", "/excel"):
                try:
                    options = {}
                    argument = parts[1].strip() if len(parts) > 1 else ""
                    if argument in ("", "all"):
                        options["full"] = True
                    if argument == "latest":
                        options["session_id"] = "latest"
                    elif argument in TYPES:
                        options["workout_kind"] = argument
                    elif argument and argument != "all":
                        dates = argument.split()
                        if len(dates) != 2:
                            raise ValueError(
                                "Use /export, /export latest, /export upper1, or /export YYYY-MM-DD YYYY-MM-DD"
                            )
                        options.update(from_date=dates[0], to_date=dates[1])
                    self.send_excel(options)
                except (ValueError, RuntimeError) as error:
                    self.api.call(
                        "sendMessage", {"chat_id": chat_id, "text": str(error)}
                    )
                return
            if command == "/reset":
                self.state["coachHistory"] = []
                self.state.pop("coachSummary", None)
                self.save()
                self.api.call(
                    "sendMessage",
                    {
                        "chat_id": chat_id,
                        "text": "Conversation and summary cleared. Saved training preferences and memory are retained.",
                    },
                )
                return
            if command in (
                "/ask",
                "/chat",
                "/adapt",
                "/remember",
                "/forget",
            ) or not text.startswith("/"):
                message = (
                    parts[1]
                    if command in ("/ask", "/chat") and len(parts) > 1
                    else text
                )
                if (
                    not (self.coach and self.coach.configured)
                    and not text.startswith("/")
                    and text
                ):
                    if self.handle_food(
                        message,
                        str(update["update_id"]),
                        update["message"],
                        allow_not_food=True,
                    ):
                        return
                self.handle_chat(
                    message,
                    str(update["update_id"]),
                    source_messages=[update["message"]],
                )
                return
            if command in ("/monthly", "/quality"):
                try:
                    self.handle_report(
                        "monthly" if command == "/monthly" else "quality",
                        str(update["update_id"]),
                        parts[1] if len(parts) > 1 else None,
                    )
                except ValueError as error:
                    self.api.call(
                        "sendMessage", {"chat_id": chat_id, "text": str(error)}
                    )
                return
            if command in ("/weekly", "/report", "/status"):
                self.handle_report(
                    {"/weekly": "weekly", "/report": "latest", "/status": "status"}[
                        command
                    ],
                    str(update["update_id"]),
                )
                return
            if command in ("/start", "/help", "/next", "/plan") and len(parts) == 1:
                self.api.call(
                    "sendMessage",
                    {
                        "chat_id": chat_id,
                        "text": "Use /menu to show the action buttons. Choose the next session proposal. Targets use your latest named workouts. /weekly shows last week; /report analyzes your latest session. Weekly, monthly and post-workout reports are automatic when enabled. Use /export for an Excel workbook, or /export latest for the last session. You can also send a normal question to the coach.",
                    },
                )
                return
            kind = workout_type(
                parts[1]
                if command in ("/next", "/plan") and len(parts) > 1
                else command.lstrip("/")
            )
            if command == "/all":
                kind = "all"
            if not kind:
                self.api.call(
                    "sendMessage",
                    {
                        "chat_id": chat_id,
                        "text": "Use /menu for buttons, or /upper1, /upper2, /lower1, /lower2, /all, /weekly, /report, or /status.",
                    },
                )
                return
        if kind not in (*TYPES, "all"):
            return
        plans = self.fetch_plans()
        selected = [p for p in plans if kind == "all" or p["type"] == kind]
        if not selected:
            raise RuntimeError("No proposal data returned")
        for plan in selected:
            caption = f"{plan['name']} · complete workout · based on {plan['baselineDate'] or 'no recorded session'}. Proposed targets, not completed sets."
            values = {"chat_id": chat_id, "caption": caption}
            self.api.call("sendPhoto", values, photo=render_plan(plan))

    def food_reply_target(self, message):
        reply = message.get("reply_to_message", {})
        message_id = reply.get("message_id")
        if not message_id:
            return None
        for identity, pending in self.state.get("pendingFood", {}).items():
            if pending.get("preview_message_id") == message_id:
                return identity
        # Existing previews from before reply tracking still carry their draft ID.
        if reply.get("from", {}).get("is_bot"):
            for row in reply.get("reply_markup", {}).get("inline_keyboard", []):
                for button in row:
                    data = button.get("callback_data", "")
                    if data.startswith("food:save:"):
                        identity = data.removeprefix("food:save:")
                        if identity in self.state.get("pendingFood", {}):
                            return identity
        return None

    def current_food_draft(self, identity):
        pending = self.state.get("pendingFood", {})
        visited = set()
        while identity in pending and identity not in visited:
            visited.add(identity)
            draft = pending[identity]
            if draft.get("status") != "superseded":
                return identity, draft
            identity = draft.get("replacement")
        raise ValueError(
            "This food preview is no longer available. Send the food again for a new estimate."
        )

    def queue_food_album(self, message, update_id):
        key = str(message["chat"]["id"]) + ":" + str(message["media_group_id"])
        album = self.state.setdefault("foodAlbums", {}).setdefault(
            key, {"messages": {}, "command_id": "album:" + key}
        )
        target = self.food_reply_target(message)
        if target:
            album["revision_of"] = target
        identity = str(message.get("message_id", update_id))
        # Store file references, never image bytes; resume incomplete albums after restart.
        album["messages"][identity] = {
            k: message[k]
            for k in ("photo", "document", "caption", "date", "message_id")
            if k in message
        }
        album["ready_at"] = (self.clock() + timedelta(seconds=2)).isoformat()
        self.save()

    def flush_food_albums(self):
        albums = self.state.setdefault("foodAlbums", {})
        for key, album in list(albums.items()):
            if datetime.fromisoformat(album["ready_at"]) > self.clock():
                continue
            messages = sorted(
                album["messages"].values(), key=lambda m: m.get("message_id", 0)
            )
            description = "\n".join(
                dict.fromkeys(
                    m["caption"].strip()
                    for m in messages
                    if m.get("caption", "").strip()
                )
            )
            self.handle_images(
                description,
                album["command_id"],
                messages,
                revision_of=album.get("revision_of"),
            )
            albums.pop(key)
            self.save()

    def image_sources(self, messages):
        sources = []
        for message in messages:
            photo = message.get("photo") or []
            document = message.get("document") or {}
            if photo:
                source = {"photo": [{"file_id": photo[-1]["file_id"]}]}
            elif document.get("file_id"):
                source = {
                    "document": {
                        "file_id": document["file_id"],
                        "mime_type": document.get("mime_type", ""),
                    }
                }
            else:
                continue
            if source not in sources:
                sources.append(source)
        return sources

    def download_images(self, sources):
        if len(sources) > 10:
            raise ValueError("Send at most 10 images in one album.")
        images = []
        total = 0
        for source in sources:
            photo = source.get("photo") or []
            document = source.get("document") or {}
            image, mime = self.api.download_photo(
                photo[-1]["file_id"] if photo else document["file_id"]
            )
            mime = document.get("mime_type") or mime
            if (
                mime not in ("image/jpeg", "image/png", "image/webp")
                or not image
                or len(image) > 12_000_000
            ):
                raise ValueError("Use JPEG, PNG or WebP images under 12 MB each.")
            total += len(image)
            if total > 30_000_000:
                raise ValueError("The image album is too large (30 MB total max).")
            images.append((image, mime))
        return images

    def handle_images(self, description, command_id, messages, revision_of=None):
        command = (
            description.split(maxsplit=1)[0].split("@")[0].lower()
            if description.strip()
            else ""
        )
        if command == "/food" or (
            revision_of and not (self.coach and self.coach.configured)
        ):
            self.handle_food(
                description,
                command_id,
                messages[0],
                attachments=messages if len(messages) > 1 else None,
                revision_of=revision_of,
            )
            return
        if command_id in self.state.get("chatOutbox", {}):
            self.handle_chat(description, command_id)
            return
        sources = self.image_sources(messages)
        try:
            images = self.download_images(sources)
        except (ValueError, RuntimeError) as error:
            self.api.call("sendMessage", {"chat_id": self.owner, "text": str(error)})
            return
        if not (self.coach and self.coach.configured):
            if self.handle_food(
                description,
                command_id,
                messages[0],
                allow_not_food=True,
                attachments=messages if len(messages) > 1 else None,
                downloaded_images=images,
            ):
                return
        self.handle_chat(
            description
            or "[Images attached without a caption. Infer the request from the images and conversation.]",
            command_id,
            images=images,
            image_sources=sources,
            source_messages=messages,
            revision_of=revision_of,
        )

    def handle_food(
        self,
        description,
        command_id,
        message,
        allow_not_food=False,
        attachments=None,
        revision_of=None,
        downloaded_images=None,
        defer_preview=False,
    ):
        try:
            identity = str(
                uuid.uuid5(uuid.NAMESPACE_URL, "telegram-food:" + command_id)
            )
            existing = self.state.get("pendingFood", {}).get(identity)
            if existing:
                if defer_preview:
                    return {
                        "draftId": identity,
                        "status": existing["status"],
                        "estimate": existing["body"],
                        "saved": existing["status"] == "saved",
                    }
                if existing["status"] == "pending":
                    self.send_food_preview(identity)
                return True
            prior = None
            if revision_of:
                revision_of, prior = self.current_food_draft(revision_of)
                if (
                    prior["status"] != "pending"
                    or datetime.fromisoformat(prior["expires"]) < self.clock()
                ):
                    raise ValueError(
                        "Only an unsaved, active estimate can be revised. This preview was saved, cancelled or expired. Send the food again for a new estimate."
                    )
            sources = list(prior.get("sources", [])) if prior else []
            for attachment in attachments if attachments is not None else [message]:
                photo = attachment.get("photo") or []
                document = attachment.get("document") or {}
                if photo:
                    source = {"photo": [{"file_id": photo[-1]["file_id"]}]}
                elif document.get("file_id"):
                    source = {
                        "document": {
                            "file_id": document["file_id"],
                            "mime_type": document.get("mime_type", ""),
                        }
                    }
                else:
                    continue
                if source not in sources:
                    sources.append(source)
            if len(sources) > 10:
                raise ValueError(
                    "An estimate can use at most 10 food and label images. Send a smaller selection for a new estimate."
                )
            if attachments is not None and len(attachments) > 10:
                raise ValueError("Send at most 10 food and label images in one album.")
            images = (
                downloaded_images
                if downloaded_images is not None
                else self.download_images(sources)
            )
            if prior:
                estimate = self.food_estimator.estimate(
                    description, images=images, previous=prior["body"]
                )
            elif attachments is not None:
                estimate = self.food_estimator.estimate(description, images=images)
            else:
                image, mime = images[0] if images else (None, "image/jpeg")
                estimate = self.food_estimator.estimate(description, image, mime)
            if estimate is None:
                if defer_preview:
                    raise ValueError(
                        "Food or amount was not identifiable. Ask for clarification; no preview was created."
                    )
                if allow_not_food:
                    return False
                self.api.call(
                    "sendMessage",
                    {
                        "chat_id": self.owner,
                        "text": "I could not identify food. Try another photo or add a short description of the portion.",
                    },
                )
                return True
            stamp = (
                datetime.fromtimestamp(message["date"], timezone.utc)
                if message.get("date")
                else self.clock()
            )
            if prior:
                stamp = datetime.fromisoformat(prior["body"]["time"])
            pending = self.state.setdefault("pendingFood", {})
            for key, value in list(pending.items()):
                if datetime.fromisoformat(value["expires"]) < self.clock() - timedelta(
                    days=1
                ):
                    pending.pop(key)
            saved_description = description
            if prior:
                saved_description = (
                    prior["body"]["description"] + "\nCorrection: " + description
                )[-2000:]
            pending[identity] = {
                "body": {
                    "action": "add",
                    "id": identity,
                    "time": stamp.isoformat(),
                    "description": saved_description,
                    **estimate,
                },
                "expires": (self.clock() + timedelta(hours=24)).isoformat(),
                "status": "pending",
                "sources": sources,
            }
            if prior:
                prior.update(status="superseded", replacement=identity)
                prior.pop("sources", None)
            self.save()
            if defer_preview:
                return {
                    "draftId": identity,
                    "status": "pending",
                    "estimate": pending[identity]["body"],
                    "saved": False,
                    "message": "Food estimate queued for Save/Cancel review. Not saved.",
                }
            self.send_food_preview(identity)
            return True
        except TelegramError:
            raise
        except (ValueError, RuntimeError) as error:
            if defer_preview:
                raise
            if allow_not_food:
                return False
            self.api.call("sendMessage", {"chat_id": self.owner, "text": str(error)})
            return True

    def send_food_preview(self, identity):
        pending = self.state["pendingFood"][identity]
        estimate = pending["body"]
        portions = ", ".join(
            i["name"] + " (" + i["portion"] + ")" for i in estimate["items"]
        )
        body = f"🍽 ESTIMATE · NOT SAVED\n{estimate['name']}\n{estimate['calories']:g} kcal · Protein {estimate['protein_g']:g} g · Carbs {estimate['carbs_g']:g} g · Fat {estimate['fat_g']:g} g"
        if portions:
            body += "\n" + portions
        if estimate["note"]:
            body += "\nUncertainty: " + estimate["note"]
        body += "\nReply to this preview with a correction or extra food/label photos to revise it. Press Save or Cancel. Preview expires in 24 hours."
        sent = self.api.call(
            "sendMessage",
            {
                "chat_id": self.owner,
                "text": body,
                "reply_markup": {
                    "inline_keyboard": [
                        [
                            {
                                "text": "Save food entry",
                                "callback_data": "food:save:" + identity,
                            },
                            {
                                "text": "Cancel",
                                "callback_data": "food:cancel:" + identity,
                            },
                        ]
                    ]
                },
            },
        )
        if isinstance(sent, dict) and isinstance(sent.get("message_id"), int):
            pending["preview_message_id"] = sent["message_id"]
            self.save()

    def handle_food_review(self, command):
        _, action, identity = command.split(":", 2)
        pending = self.state.get("pendingFood", {}).get(identity)
        if not pending:
            self.api.call(
                "sendMessage",
                {
                    "chat_id": self.owner,
                    "text": "This food preview is no longer available. Send the food again for a new estimate.",
                },
            )
            return
        if pending["status"] == "superseded":
            self.api.call(
                "sendMessage",
                {
                    "chat_id": self.owner,
                    "text": "This estimate was replaced. Review and use Save or Cancel on the newest food preview.",
                },
            )
            return
        if action == "cancel":
            if pending["status"] == "pending":
                pending["status"] = "cancelled"
                pending.pop("sources", None)
                self.save()
            message = (
                "Food estimate cancelled. Nothing was saved."
                if pending["status"] == "cancelled"
                else "This food entry was already saved."
                if pending["status"] == "saved"
                else "This food preview expired. Nothing was saved."
            )
            self.api.call("sendMessage", {"chat_id": self.owner, "text": message})
            return
        if pending["status"] in ("cancelled", "expired"):
            self.api.call(
                "sendMessage",
                {
                    "chat_id": self.owner,
                    "text": "This estimate was cancelled or expired. Send the food again for a new preview.",
                },
            )
            return
        if pending["status"] == "pending":
            if datetime.fromisoformat(pending["expires"]) < self.clock():
                pending["status"] = "expired"
                pending.pop("sources", None)
                self.save()
                self.api.call(
                    "sendMessage",
                    {
                        "chat_id": self.owner,
                        "text": "Food preview expired. Send the food again for a new estimate.",
                    },
                )
                return
            try:
                self.food_action(pending["body"])
            except (ValueError, RuntimeError) as error:
                self.api.call(
                    "sendMessage",
                    {
                        "chat_id": self.owner,
                        "text": "Could not save food: " + str(error),
                    },
                )
                return
            pending["status"] = "saved"
            pending.pop("sources", None)
            self.save()
        if pending["status"] == "saved":
            self.api.call(
                "sendMessage",
                {
                    "chat_id": self.owner,
                    "text": "Food entry saved. Use /foodlog for today’s total.",
                    "reply_markup": {
                        "inline_keyboard": [
                            [
                                {
                                    "text": "Delete entry",
                                    "callback_data": "food:delete:" + identity,
                                }
                            ]
                        ]
                    },
                },
            )

    def deliver(self, key, text=None):
        outbox = self.state.setdefault("reportOutbox", {})
        if key not in outbox:
            if text is None:
                raise ValueError("Report text is unavailable")
            outbox[key] = {"parts": split_text(text), "next": 0}
            self.save()
        entry = outbox[key]
        if entry.get("format") == "html":
            self.deliver_report(key)
            return
        while entry["next"] < len(entry["parts"]):
            self.api.call(
                "sendMessage",
                {"chat_id": self.owner, "text": entry["parts"][entry["next"]]},
            )
            entry["next"] += 1
            self.save()

    def deliver_report(
        self,
        key,
        facts=None,
        analysis="",
        model=None,
        status="unavailable",
        report_type="session",
    ):
        outbox = self.state.setdefault("reportOutbox", {})
        if key not in outbox:
            if facts is None:
                raise ValueError("Report facts are unavailable")
            outbox[key] = {
                "format": "html",
                "reportType": report_type,
                "facts": facts,
                "analysis": analysis,
                "model": model
                or (self.reporter.model if self.reporter else "not configured"),
                "status": status,
                "next": 0,
            }
            self.save()
        entry = outbox[key]
        if entry.get("format") != "html":
            self.deliver(key)
            return
        facts = entry["facts"]
        monthly = entry.get("reportType") == "monthly"
        workout = (
            {"name": "Monthly review " + facts["month"], "date": facts["to"]}
            if monthly
            else facts["workout"]
        )
        if entry["next"] == 0:
            image = (
                render_monthly_preview(facts, entry["model"], bool(entry["analysis"]))
                if monthly
                else render_report_preview(
                    facts, entry["model"], bool(entry["analysis"])
                )
            )
            self.api.call(
                "sendPhoto",
                {
                    "chat_id": self.owner,
                    "caption": f"{workout['name']} · {workout['date']} · Chart preview. Full HTML report follows.",
                },
                photo=image,
            )
            entry["next"] = 1
            self.save()
        if entry["next"] == 1:
            html = (
                render_monthly_html(
                    facts, entry["analysis"], entry["model"], entry["status"]
                )
                if monthly
                else render_report_html(
                    facts, entry["analysis"], entry["model"], entry["status"]
                )
            )
            caption = (
                f"{workout['name']} · {workout['date']}. Open the HTML file for graphs, comparisons, recovery and "
                + (
                    "AI analysis by " + entry["model"]
                    if entry["analysis"]
                    else "calculated results (AI unavailable)"
                )
                + "."
            )
            self.api.call(
                "sendDocument",
                {"chat_id": self.owner, "caption": caption},
                document=html,
                filename=(
                    "form-monthly-" + facts["month"]
                    if monthly
                    else "form-session-" + workout["date"]
                )
                + ".html",
            )
            entry["next"] = 2
            self.save()

    def finish_report(self, key):
        self.state.setdefault("reportOutbox", {}).pop(key, None)
        self.save()

    def handle_report(self, kind, command_id, month=None):
        if kind == "status":
            now = self.clock().astimezone(self.zone)
            due = datetime.combine(monday(now.date()), self.weekly_time, self.zone)
            if now >= due:
                due += timedelta(days=7)
            text = f"Weekly summary: {'enabled' if self.weekly_enabled else 'disabled'}, Monday {self.weekly_time.strftime('%H:%M')} ({self.zone.key}). Next scheduled: {due.strftime('%d %b %Y %H:%M')}.\nPost-workout reports: {'enabled' if self.post_enabled else 'disabled'}. OpenAI: {self.reporter.model if self.reporter and self.reporter.configured else 'not configured'}. Monthly review: {'enabled' if self.monthly_enabled else 'disabled'}, first day of month at the configured report time. Format: HTML report + chart preview."
            self.api.call("sendMessage", {"chat_id": self.owner, "text": text})
            return
        if kind == "quality" and self.fetch_data:
            review = quality_review(self.fetch_data())
            document = render_quality_html(review)
            self.api.call(
                "sendDocument",
                {
                    "chat_id": self.owner,
                    "caption": f"Data-quality review · {review['issueGroups']} issue groups. Review only; no recorded data changed.",
                },
                document=document,
                filename="form-data-quality.html",
            )
            return
        if kind not in ("weekly", "latest", "monthly") or not self.fetch_data:
            return
        key = "manual:" + command_id + ":" + kind
        if key not in self.state.get("reportOutbox", {}):
            data = self.fetch_data()
            today = self.clock().astimezone(self.zone).date()
            if kind == "weekly":
                self.deliver(key, weekly_text(weekly_facts(data, today)))
            elif kind == "monthly":
                facts = monthly_facts(data, today, month)
                analysis = ""
                status = "not configured"
                if self.reporter and self.reporter.configured:
                    try:
                        analysis = self.reporter.write_monthly(facts)
                        status = "generated"
                    except Exception:
                        status = "temporarily unavailable"
                self.deliver_report(
                    key, facts, analysis, status=status, report_type="monthly"
                )
            else:
                workouts = sorted(
                    (w for w in data["workouts"] if w["date"] <= today.isoformat()),
                    key=lambda w: (w["date"], w.get("time", "")),
                    reverse=True,
                )
                if not workouts:
                    self.deliver(key, "No completed strength session is available yet.")
                else:
                    facts = self.session_report_facts(data, workouts[0]["id"])
                    analysis = ""
                    status = "not configured"
                    if self.reporter and self.reporter.configured:
                        try:
                            analysis = self.reporter.write(facts)
                            status = "generated"
                        except Exception:
                            status = "temporarily unavailable"
                    self.deliver_report(key, facts, analysis, status=status)
        else:
            self.deliver(key)
        self.finish_report(key)

    def run_reports(self, force=False):
        if not self.owner or not self.fetch_data:
            return
        now = self.clock()
        stamp = now.timestamp()
        if not force and stamp - self.last_report_check < 60:
            return
        self.last_report_check = stamp
        data = self.fetch_data()
        local = now.astimezone(self.zone)
        if self.weekly_enabled:
            due = datetime.combine(monday(local.date()), self.weekly_time, self.zone)
            started = datetime.fromisoformat(self.state["reportsStartedAt"])
            period = (due.date() - timedelta(days=1)).isoformat()
            if (
                now >= due
                and due >= started
                and self.state.get("weeklyLastSent", "") < period
            ):
                key = "weekly:" + period
                if key in self.state.get("reportOutbox", {}):
                    self.deliver(key)
                else:
                    self.deliver(key, weekly_text(weekly_facts(data, local.date())))
                self.state["weeklyLastSent"] = period
                self.finish_report(key)
        if self.monthly_enabled:
            due = datetime.combine(
                local.date().replace(day=1), self.weekly_time, self.zone
            )
            period = (due.date() - timedelta(days=1)).strftime("%Y-%m")
            started = datetime.fromisoformat(self.state["reportsStartedAt"])
            if (
                now >= due
                and due >= started
                and self.state.get("monthlyLastSent", "") < period
            ):
                key = "monthly:" + period
                if key in self.state.get("reportOutbox", {}):
                    self.deliver(key)
                else:
                    facts = monthly_facts(data, local.date(), period)
                    analysis = (
                        self.reporter.write_monthly(facts)
                        if self.reporter and self.reporter.configured
                        else ""
                    )
                    self.deliver_report(
                        key,
                        facts,
                        analysis,
                        status="generated" if analysis else "not configured",
                        report_type="monthly",
                    )
                self.state["monthlyLastSent"] = period
                self.finish_report(key)
        if not self.post_enabled:
            return
        ids = {w["id"] for w in data["workouts"]}
        if "seenWorkouts" not in self.state:
            self.state["seenWorkouts"] = sorted(ids)
            self.save()
            return
        seen = set(self.state["seenWorkouts"])
        pending = self.state.setdefault("pendingWorkoutReports", {})
        for w in data["workouts"]:
            if w["id"] in seen:
                continue
            seen.add(w["id"])
            if w.get("dateOnly") or not w.get("time"):
                continue
            try:
                start = datetime.fromisoformat(w["time"].replace("Z", "+00:00"))
                if start.tzinfo is None:
                    start = start.replace(tzinfo=self.zone)
                end = start + timedelta(seconds=w.get("duration") or 0)
            except (ValueError, TypeError):
                continue
            if 0 <= (now - end).total_seconds() <= 48 * 3600:
                pending[w["id"]] = {
                    "firstSeen": stamp,
                    "changed": stamp,
                    "fingerprint": "",
                    "retryAfter": 0,
                }
        self.state["seenWorkouts"] = sorted(seen)
        current = {w["id"]: w for w in data["workouts"]}
        for identity, entry in list(pending.items()):
            if identity not in current:
                pending.pop(identity)
                continue
            rows = sorted(
                (
                    r
                    for r in data["sets"]
                    if r["sessionId"] == identity
                    and r["exercise"].strip().casefold() != "unknown"
                ),
                key=lambda r: r["id"],
            )
            digest = hashlib.sha256(
                json.dumps(
                    {"workout": current[identity], "sets": rows}, sort_keys=True
                ).encode()
            ).hexdigest()
            if digest != entry["fingerprint"]:
                entry.update(fingerprint=digest, changed=stamp)
            if (
                not rows
                or stamp - entry["changed"] < self.settle_seconds
                or stamp < entry.get("retryAfter", 0)
            ):
                continue
            if not self.reporter or not self.reporter.configured:
                continue
            key = "workout:" + identity
            try:
                if key in self.state.get("reportOutbox", {}):
                    self.deliver(key)
                else:
                    facts = self.session_report_facts(data, identity)
                    analysis = self.reporter.write(facts)
                    self.deliver_report(key, facts, analysis, status="generated")
                pending.pop(identity)
                self.state.setdefault("workoutReportsSent", []).append(identity)
                self.finish_report(key)
            except Exception as error:
                entry["retryAfter"] = stamp + 600
                logging.warning(
                    "Post-workout report deferred (%s).", type(error).__name__
                )
        self.save()

    def session_report_facts(self, data, identity):
        facts = session_facts(data, identity)
        if self.garmin_review:
            workout = next(w for w in data["workouts"] if w["id"] == identity)
            if workout.get("source") == "garmin" and workout.get("time"):
                try:
                    template = self.garmin_review(
                        {
                            "operation": "review",
                            "workoutName": workout["name"],
                            "sessionTime": workout["time"],
                        }
                    )
                    facts["planReview"] = compare_plan(facts, template)
                except (ValueError, RuntimeError):
                    facts["planReview"] = {
                        "status": "unavailable",
                        "reason": "Garmin template could not be read for this review.",
                    }
        facts["trainingPreferences"] = self.state.get("coachPreferences", {})
        facts["userTrainingMemory"] = self.state.get("coachMemory", [])
        return facts

    def handle_chat(
        self,
        message,
        command_id,
        images=None,
        image_sources=None,
        source_messages=None,
        revision_of=None,
    ):
        if not self.coach or not self.coach.configured or not self.fetch_data:
            self.api.call(
                "sendMessage",
                {
                    "chat_id": self.owner,
                    "text": "Training chat needs OPENAI_API_KEY. The existing workout buttons remain available.",
                },
            )
            return
        outbox = self.state.setdefault("chatOutbox", {})
        if command_id not in outbox:
            allow_memory = bool(
                re.search(
                    r"\b(remember|forget|save|preference|preferences|set|configure|update)\b|пам.?ят|забу|збереж",
                    message,
                    re.I,
                )
            )
            data = self.fetch_data()
            tools = TrainingTools(
                data,
                self.state,
                self.save,
                save_action,
                self.clock().astimezone(self.zone).date(),
                command_id,
                allow_memory,
                database=self.database,
                garmin=self.garmin,
            )
            current_images = images

            def food_preview(description, revision_id):
                sources = source_messages or image_sources or [{}]
                # One food draft per turn, just as one album represents one meal.
                return self.handle_food(
                    description,
                    command_id,
                    sources[0],
                    attachments=sources if len(sources) > 1 else None,
                    revision_of=revision_id,
                    downloaded_images=current_images if not revision_id else None,
                    defer_preview=True,
                )

            tools.food_preview = food_preview
            draft = TelegramDraft(self.api, self.owner)
            try:
                prompt = message
                if revision_of:
                    prompt += (
                        "\n[This message replies to food preview "
                        + revision_of
                        + ". Determine whether it is a correction or a question.]"
                    )
                if images is None:
                    # Reuse the most recent visual context for text follow-ups, including after restart.
                    previous = next(
                        (
                            r
                            for r in reversed(self.state.get("coachHistory", [])[-8:])
                            if r.get("imageSources")
                        ),
                        None,
                    )
                    if previous:
                        images = self.download_images(previous["imageSources"])
                        prompt = (
                            "Images from the earlier message: "
                            + previous["content"]
                            + "\nCurrent request: "
                            + message
                        )
                options = {"images": images} if images else {}
                result = self.coach.answer(
                    prompt,
                    tools,
                    self.state.get("coachHistory", []),
                    on_text=draft.update,
                    **options,
                )
            except (RuntimeError, ValueError) as error:
                logging.warning("Coach request failed (%s).", type(error).__name__)
                self.api.call(
                    "sendMessage",
                    {
                        "chat_id": self.owner,
                        "text": "The coach could not finish this request. Please try again or ask a narrower question. Any proposed data changes still need Save; saved preferences are available through /memory.",
                    },
                )
                for key, value in self.state.get("pendingEdits", {}).items():
                    if value.get("turn") == command_id and value["status"] == "pending":
                        self.send_edit_preview(key)
                for artifact in tools.artifacts:
                    if artifact.get("kind") == "food_preview":
                        self.send_food_preview(artifact["draftId"])
                return
            user_turn = {"role": "user", "content": message[:6000]}
            if image_sources:
                user_turn["imageSources"] = image_sources
            history = self.state.setdefault("coachHistory", [])
            history.extend(
                [user_turn, {"role": "assistant", "content": result["text"]}]
            )
            logging.info(
                "Coach reply queued (%d attachments).", len(result["artifacts"])
            )
            outbox[command_id] = {
                "parts": split_rich_text(result["text"]),
                "rich": True,
                "plans": result["artifacts"],
                "drafts": [
                    key
                    for key, value in self.state.get("pendingEdits", {}).items()
                    if value.get("turn") == command_id
                ],
                "next": 0,
            }
            self.save()
        entry = outbox[command_id]
        parts = entry["parts"]
        count = len(parts) + len(entry["plans"]) + len(entry.get("drafts", []))
        while entry["next"] < count:
            index = entry["next"]
            if index < len(parts):
                self.api.call(
                    "sendMessage",
                    {
                        "chat_id": self.owner,
                        "text": parts[index]
                        if entry.get("rich")
                        else format_chat_text(parts[index]),
                        "parse_mode": "HTML",
                    },
                )
            elif index < len(parts) + len(entry["plans"]):
                plan = entry["plans"][index - len(parts)]
                if plan.get("kind") == "html_report":
                    self.api.call(
                        "sendDocument",
                        {"chat_id": self.owner, "caption": plan["title"]},
                        document=plan["html"].encode(),
                        filename=plan["filename"],
                    )
                    logging.info("Custom HTML report delivered.")
                elif plan.get("kind") == "food_preview":
                    self.send_food_preview(plan["draftId"])
                elif plan.get("kind") == "database_extrema":
                    from reptrace.storage.reader import render_extrema_report

                    self.api.call(
                        "sendDocument",
                        {
                            "chat_id": self.owner,
                            "caption": str(plan["report"]["metricCount"])
                            + " numeric metrics · full minimum/maximum table in source units.",
                        },
                        document=render_extrema_report(plan["report"]),
                        filename="metric-min-max.html",
                    )
                elif plan.get("kind") == "xlsx":
                    self.send_excel(plan["options"])
                else:
                    self.api.call(
                        "sendPhoto",
                        {
                            "chat_id": self.owner,
                            "caption": plan["name"]
                            + " · adapted proposal; original history unchanged.",
                        },
                        photo=render_plan(plan),
                    )
            else:
                self.send_edit_preview(
                    entry["drafts"][index - len(parts) - len(entry["plans"])]
                )
            entry["next"] += 1
            self.save()
        outbox.pop(command_id, None)
        self.save()

    def send_excel(self, options):
        if not self.fetch_data:
            raise ValueError("Training export is unavailable")
        if options.get("full") and self.fetch_export:
            body, filename, counts = self.fetch_export()
        else:
            body, filename, counts = export_sessions(self.fetch_data(), **options)
        self.api.call(
            "sendDocument",
            {
                "chat_id": self.owner,
                "caption": (
                    "Full export, including Unknown · "
                    if options.get("full")
                    else "Excel export · "
                )
                + f" {counts['sessions']} sessions · {counts['sets']} sets. Missing measurements are blank.",
            },
            document=body,
            filename=filename,
        )

    def send_edit_preview(self, identity):
        draft = self.state.get("pendingEdits", {}).get(identity)
        if not draft:
            return
        buttons = {
            "inline_keyboard": [
                [
                    {"text": "Save", "callback_data": "edit:save:" + identity},
                    {"text": "Cancel", "callback_data": "edit:cancel:" + identity},
                ]
            ]
        }
        if (
            draft.get("body", {}).get("action") == "garmin_workout_update"
            and draft.get("garminPreview")
            and not draft["garminPreview"].get("fullEdit")
        ):
            photo = render_garmin_preview_image(draft["garminPreview"])
            self.api.call(
                "sendPhoto",
                {
                    "chat_id": self.owner,
                    "caption": "Garmin workout preview · not saved",
                    "reply_markup": buttons,
                },
                photo=photo,
            )
            return
        preview = "PROPOSED CHANGE — not saved\n" + draft["preview"]
        if len(preview) > 6000:
            document = (
                '<!doctype html><meta charset="utf-8"><title>Proposed change</title><style>body{background:#181b24;color:#eee;font:18px system-ui;padding:32px}pre{white-space:pre-wrap}</style><h1>Proposed change — not saved</h1><pre>'
                + escape(draft["preview"])
                + "</pre>"
            ).encode()
            self.api.call(
                "sendDocument",
                {
                    "chat_id": self.owner,
                    "caption": "Full change preview. Review before pressing Save.",
                },
                document=document,
                filename="proposed-change.html",
            )
            preview = (
                "PROPOSED CHANGE — not saved\n"
                + draft["preview"].split("\n")[0]
                + "\nFull details are in the attached preview. Save applies every change listed there."
            )
        parts = split_text(preview)
        for index, part in enumerate(parts):
            values = {"chat_id": self.owner, "text": part}
            if index == len(parts) - 1:
                values["reply_markup"] = buttons
            self.api.call("sendMessage", values)

    def handle_edit(self, command):
        parts = command.split(":")
        if len(parts) != 3:
            return
        _, action, identity = parts
        draft = self.state.get("pendingEdits", {}).get(identity)
        if not draft:
            self.api.call(
                "sendMessage",
                {
                    "chat_id": self.owner,
                    "text": "This preview is no longer available. Ask for a new one.",
                },
            )
            return
        status = draft["status"]
        if action == "cancel":
            if status == "pending":
                draft["status"] = "cancelled"
                self.save()
            self.api.call(
                "sendMessage",
                {
                    "chat_id": self.owner,
                    "text": "Change cancelled."
                    if draft["status"] == "cancelled"
                    else "This change was already processed.",
                },
            )
            return
        try:
            if action == "save":
                if status == "cancelled" or status == "undone":
                    raise ValueError(
                        "This preview was cancelled or undone. Ask for a new one."
                    )
                if status != "saved":
                    if datetime.fromisoformat(draft["expires"]) < self.clock():
                        raise ValueError("Preview expired. Ask for a fresh one.")
                    result = (
                        self.garmin(
                            {
                                "operation": "apply",
                                "previewId": draft["body"]["previewId"],
                            }
                        )
                        if draft["body"]["action"] == "garmin_workout_update"
                        else save_action(draft["body"])
                    )
                    draft.update(status="saved", result=result)
                    self.state["coachHistory"] = []
                    self.state.pop("coachSummary", None)
                    self.save()
                text = "Saved. Your dashboard and future reports will use the updated data."
                buttons = {
                    "inline_keyboard": [
                        [
                            {
                                "text": "Undo this change",
                                "callback_data": "edit:undo:" + identity,
                            }
                        ]
                    ]
                }
                if draft["body"]["action"] == "garmin_workout_update":
                    text = (
                        "Garmin workout updated and verified, including the reviewed exercise additions."
                        if draft.get("garminPreview", {}).get("fullEdit")
                        else "Garmin workout weights and reps updated and verified. Exercise order and rest steps were preserved."
                    )
                    buttons = None
            elif action == "undo":
                if draft["body"]["action"] == "garmin_workout_update":
                    raise ValueError(
                        "To change this Garmin workout again, request a new preview."
                    )
                if status not in ("saved", "undone"):
                    raise ValueError("Only saved changes can be undone.")
                if status != "undone":
                    kind = (
                        "undo_workout"
                        if draft["body"]["action"].startswith("workout_")
                        else "undo_metadata"
                    )
                    save_action(
                        {
                            "action": kind,
                            "id": identity,
                            "requestId": str(
                                uuid.uuid5(uuid.NAMESPACE_URL, "undo:" + identity)
                            ),
                        }
                    )
                    draft["status"] = "undone"
                    self.state["coachHistory"] = []
                    self.state.pop("coachSummary", None)
                    self.save()
                text = "Undone. Previous data restored."
                buttons = None
            else:
                return
        except (ValueError, RuntimeError) as error:
            self.api.call(
                "sendMessage",
                {
                    "chat_id": self.owner,
                    "text": "Could not apply change: " + str(error),
                },
            )
            return
        values = {"chat_id": self.owner, "text": text}
        if buttons:
            values["reply_markup"] = buttons
        self.api.call("sendMessage", values)

    def poll_once(self):
        updates = self.api.call(
            "getUpdates",
            {
                "offset": self.state.get("offset", 0),
                "timeout": 1 if self.state.get("foodAlbums") else 30,
                "allowed_updates": ["message", "callback_query"],
            },
        )
        for update in updates:
            if update["update_id"] < self.state.get("offset", 0):
                continue
            self.handle(update)
            self.state["offset"] = update["update_id"] + 1
            self.save()
        self.flush_food_albums()


def fetch_data():
    base = os.getenv("FORM_API_URL", "http://strength-web:3001").rstrip("/")
    with urllib.request.urlopen(base + "/api/data?refresh=1", timeout=40) as response:
        payload = json.load(response)
    return payload


def fetch_food(body):
    base = os.getenv("FORM_API_URL", "http://strength-web:3001").rstrip("/")
    request = urllib.request.Request(
        base + "/api/food",
        data=json.dumps(body, allow_nan=False).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code in (400, 409):
            try:
                detail = json.loads(error.read()).get("error", "Invalid food entry")
            except ValueError:
                detail = "Invalid food entry"
            raise ValueError(detail) from None
        raise RuntimeError("Food log is temporarily unavailable.") from None
    except (OSError, ValueError):
        raise RuntimeError("Food log is temporarily unavailable.") from None


def fetch_database(operation, **args):
    base = os.getenv("FORM_API_URL", "http://strength-web:3001").rstrip("/")
    request = urllib.request.Request(
        base + "/api/database",
        data=json.dumps({"operation": operation, **args}, allow_nan=False).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(
            request, timeout=180 if operation == "extrema" else 40
        ) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 400:
            try:
                detail = json.loads(error.read()).get("error", "Invalid database query")
            except ValueError:
                detail = "Invalid database query"
            raise ValueError(detail) from None
        raise RuntimeError("Database reading is temporarily unavailable") from None
    except (OSError, ValueError):
        raise RuntimeError("Database reading is temporarily unavailable") from None


def fetch_full_export():
    base = os.getenv("FORM_API_URL", "http://strength-web:3001").rstrip("/")
    with urllib.request.urlopen(
        base + "/api/sessions.xlsx?full=1", timeout=120
    ) as response:
        body = response.read()
        if len(body) > 49_000_000:
            raise ValueError(
                "This export exceeds the Telegram file limit; download it from the dashboard."
            )
        header = response.headers.get("Content-Disposition", "")
        match = re.search(r'filename="([^"]+)"', header)
        return (
            body,
            match.group(1) if match else "form-all-data.xlsx",
            {
                "sessions": int(response.headers["X-Export-Sessions"]),
                "sets": int(response.headers["X-Export-Sets"]),
            },
        )


def fetch_garmin(body):
    base = os.getenv("FORM_API_URL", "http://strength-web:3001").rstrip("/")
    request = urllib.request.Request(
        base + "/api/garmin-workouts",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code in (400, 409):
            try:
                detail = json.loads(error.read()).get("error", "Invalid Garmin update")
            except ValueError:
                detail = "Invalid Garmin update"
            raise ValueError(detail) from None
        raise RuntimeError(
            "Garmin service is unavailable. If saving, check Garmin before requesting a new preview."
        ) from None
    except (OSError, ValueError):
        raise RuntimeError(
            "Garmin response unavailable. If saving, check Garmin before requesting a new preview."
        ) from None


def save_action(body):
    base = os.getenv("FORM_API_URL", "http://strength-web:3001").rstrip("/")
    request = urllib.request.Request(
        base + "/api/actions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code in (400, 409):
            try:
                detail = json.loads(error.read()).get("error", "Invalid change")
            except ValueError:
                detail = "Invalid change"
            raise ValueError(detail) from None
        raise RuntimeError(
            "The data service is unavailable; retry the same Save button"
        ) from None
    except (OSError, ValueError):
        raise RuntimeError(
            "The data service is unavailable; retry the same Save button"
        ) from None


def fetch_plans():
    return fetch_data()["nextSessions"]


def split_text(text, limit=3500):
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        parts.append(text)
    return parts


def enabled(name, default=True):
    return os.getenv(name, str(default)).lower() not in ("false", "0", "no", "off")


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logging.info(
            "Waiting for TELEGRAM_BOT_TOKEN in .env. After adding it, recreate the telegram-bot service."
        )
        threading.Event().wait()
        return
    try:
        bot = Bot(
            Telegram(token),
            fetch_plans,
            os.getenv("TELEGRAM_STATE_PATH", "/var/lib/form-bot/state.json"),
            os.getenv("TELEGRAM_ALLOWED_USER_ID"),
            os.getenv("TELEGRAM_PAIRING_CODE"),
            fetch_data=fetch_data,
            fetch_export=fetch_full_export,
            database=fetch_database,
            reporter=ReportWriter(),
            report_timezone=os.getenv("REPORT_TIMEZONE", "Europe/Kyiv"),
            weekly_time=os.getenv("WEEKLY_REPORT_TIME", "09:00"),
            weekly_enabled=enabled("WEEKLY_REPORT_ENABLED"),
            post_enabled=enabled("POST_WORKOUT_REPORT_ENABLED"),
            coach=TrainingCoach(),
            monthly_enabled=enabled("MONTHLY_REPORT_ENABLED"),
            settle_seconds=int(os.getenv("REPORT_SETTLE_SECONDS", "300")),
            garmin_review=fetch_garmin,
        )
    except (ValueError, OSError):
        logging.error(
            "Bot configuration or persistent state is invalid. Check the owner user ID and state volume."
        )
        return
    if not bot.owner:
        logging.info("Pair in a private chat with: /start %s", bot.pairing_code)
    else:
        logging.info("Private bot configured; waiting for requests from its owner.")
    commands = [
        {"command": key, "description": f"Image proposal for {name}"}
        for key, name in TYPES.items()
    ] + [
        {"command": "menu", "description": "Show action buttons"},
        {"command": "food", "description": "Log food from a photo or description"},
        {"command": "foodlog", "description": "Show today’s calories and macros"},
        {
            "command": "export",
            "description": "Excel: all data, latest session or date range",
        },
        {"command": "next", "description": "Choose a session"},
        {"command": "all", "description": "Images for all four sessions"},
        {"command": "weekly", "description": "Progress from last Monday to Sunday"},
        {
            "command": "report",
            "description": "HTML graphs and AI analysis of the latest session",
        },
        {"command": "status", "description": "Report schedule and connection status"},
        {"command": "ask", "description": "Ask the coach about your training history"},
        {
            "command": "adapt",
            "description": "Adapt a workout to time or equipment constraints",
        },
        {"command": "memory", "description": "Inspect saved preferences and memory"},
        {"command": "remember", "description": "Save a lasting training preference"},
        {"command": "forget", "description": "Forget a preference or memory"},
        {
            "command": "reset",
            "description": "Reset chat while retaining saved preferences",
        },
        {
            "command": "quality",
            "description": "Review missing values and suspicious records",
        },
        {"command": "monthly", "description": "Monthly HTML review; optional YYYY-MM"},
    ]
    registered = False
    while True:
        try:
            if not registered:
                me = bot.api.call("getMe", {})
                bot.api.call("setMyCommands", {"commands": commands})
                registered = True
                logging.info("Bot @%s is connected.", me.get("username", "configured"))
            bot.run_reports()
            bot.poll_once()
        except TelegramError as error:
            logging.warning(
                "%s; retrying. A 409 means another poller or webhook is active.", error
            )
            time.sleep(max(5, error.retry_after))
        except Exception as error:
            # Never log request URLs, tokens, health data or message content.
            logging.warning(
                "Request could not finish (%s); retrying.", type(error).__name__
            )
            time.sleep(5)


if __name__ == "__main__":
    main()
