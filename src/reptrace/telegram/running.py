"""Owner-only running command implementation; called after the bot's access checks."""

from datetime import timedelta
import json
import os
import urllib.request
import urllib.error

from reptrace.reports.running import (
    history_text,
    running_text,
    render_running_report,
    formatted,
)
from reptrace.training.running import compare_runs


def fetch_running(body):
    base = os.getenv("FORM_API_URL", "http://strength-web:3001").rstrip("/")
    request = urllib.request.Request(
        base + "/api/running",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=100) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 400:
            raise ValueError("Choose a recorded run from /runs.") from None
        raise RuntimeError(
            "Running detail is temporarily unavailable. Please retry."
        ) from None
    except (OSError, ValueError):
        raise RuntimeError(
            "Running detail is temporarily unavailable. Please retry."
        ) from None


def handle(bot, command, argument, request_id):
    if not bot.fetch_data:
        bot.api.call(
            "sendMessage",
            {
                "chat_id": bot.owner,
                "text": "Running history is unavailable until the web connection is configured.",
            },
        )
        return
    outbox = bot.state.setdefault("runningOutbox", {})
    if request_id not in outbox:
        data = bot.fetch_data()
        runs = sorted(data.get("runs", []), key=lambda r: r["time"], reverse=True)
        if not runs:
            bot.api.call(
                "sendMessage",
                {
                    "chat_id": bot.owner,
                    "text": "No Garmin runs are collected yet. Save and sync a run, then try /runs.",
                },
            )
            return
        if command in ("/running", "/runs"):
            period = argument or ("30" if command == "/running" else "all")
            if period not in ("7", "30", "90", "all"):
                bot.api.call(
                    "sendMessage",
                    {
                        "chat_id": bot.owner,
                        "text": "Use /running 7, /running 30, /running 90, or /running all. Use /run latest for a detailed report.",
                    },
                )
                return
            if period != "all":
                today = bot.clock().astimezone(bot.zone).date()
                start = (today - timedelta(days=int(period) - 1)).isoformat()
                runs = [r for r in runs if start <= r["date"] <= today.isoformat()]
            keyboard = [
                [
                    {"text": "Last 30 days", "callback_data": "running:30"},
                    {"text": "All runs", "callback_data": "running:all"},
                ]
            ]
            keyboard += [
                [
                    {
                        "text": (r["date"] + " · " + r["name"])[:55],
                        "callback_data": "run:" + r["id"],
                    }
                ]
                for r in runs[:10]
            ]
            bot.api.call(
                "sendMessage",
                {
                    "chat_id": bot.owner,
                    "text": history_text(runs),
                    "reply_markup": {"inline_keyboard": keyboard},
                },
            )
            return
        if command == "/runcompare":
            tokens = (argument or "latest previous").split()
            aliases = {
                "latest": runs[0]["id"],
                "previous": runs[1]["id"] if len(runs) > 1 else "",
            }
            ids = [aliases.get(token, token) for token in tokens]
            if len(ids) != 2 or not all(
                any(r["id"] == identity for r in runs) for identity in ids
            ):
                bot.api.call(
                    "sendMessage",
                    {
                        "chat_id": bot.owner,
                        "text": "Use /runcompare to compare your last two runs, or /runcompare RUN_ID RUN_ID. Ask the coach to compare named dates, or use /runs to browse your history.",
                    },
                )
                return
            left, right = [bot.running({"id": identity}) for identity in ids]
            changes = compare_runs(left["summary"], right["summary"])
            keys = {
                "distanceKm",
                "averagePace",
                "movingSeconds",
                "averageHR",
                "cadence",
                "averagePower",
                "trainingLoad",
                "elevationGain",
                "strideLengthM",
                "groundContactMs",
            }
            lines = [
                f"Run comparison · {left['summary']['date']} → {right['summary']['date']}"
            ]
            for m in changes:
                if m["key"] in keys:
                    lines.append(
                        f"{m['label']}: {formatted(m['left'], m)} → {formatted(m['right'], m)}"
                    )
            lines += [d["warning"] for d in (left, right) if d.get("warning")]
            lines.append(
                "Different distance, terrain and conditions affect comparisons. Lower pace is faster."
            )
            bot.api.call(
                "sendMessage", {"chat_id": bot.owner, "text": "\n".join(lines)}
            )
            return
        identity = argument or "latest"
        run = (
            runs[0]
            if identity == "latest"
            else next((r for r in runs if r["id"] == identity), None)
        )
        if not run:
            bot.api.call(
                "sendMessage",
                {
                    "chat_id": bot.owner,
                    "text": "Choose a recorded run from /runs, or use /run latest.",
                },
            )
            return
        detail = bot.running({"id": run["id"]})
        outbox[request_id] = {
            "text": running_text(detail),
            "html": render_running_report(detail),
            "next": 0,
        }
        bot.save()
    entry = outbox[request_id]
    if entry["next"] == 0:
        bot.api.call("sendMessage", {"chat_id": bot.owner, "text": entry["text"]})
        entry["next"] = 1
        bot.save()
    if entry["next"] == 1:
        bot.api.call(
            "sendDocument",
            {
                "chat_id": bot.owner,
                "caption": "Running report · charts, zones, dynamics and laps",
            },
            document=entry["html"].encode(),
            filename="running-report.html",
        )
        entry["next"] = 2
        bot.save()
    del outbox[request_id]
    bot.save()
