"""Web feature parity: bounded reads and owner-confirmed proposals."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess

from reptrace.coaching.edits import stage
from reptrace.storage.state import validate_volume_settings
from reptrace.training.equipment import validate_equipment

VIEWS = ["overview", "exercises", "sets", "workouts", "weekly_volume", "muscle_map",
         "strength", "recovery", "insights", "records", "goals", "compare", "sync", "preferences"]


def definitions(function, string):
    filters = {
        "from_date": string(True), "to_date": string(True),
        "source": {"type": "string", "enum": ["all", "garmin", "manual"]},
        "exercise": string(True),
        "options_json": string(True),
    }
    return [
        function("get_dashboard_view",
                 "Read the same calculations as the web app. Includes records, estimated 1RM (strength, requires one exercise), adjusted weekly volume, muscle involvement, insights, goals and sync. Dates inclusive; null means all. options_json is an optional object: volume_mode recorded|adjusted; grouping muscle|exercise; weekly boolean; reps 1..500; window 3..12; recovery_metric sleepHours|hrv|restingHR|sleepScore|bodyBattery|bodyWeightKg; threshold number/null; left_id/right_id for compare; week YYYY-MM-DD; include_secondary boolean; compare_weeks 1|4; muscle_group primary group; search workout/exercise name. Paginate with offset; never infer complete coverage from truncated results.",
                 {"view": {"type": "string", "enum": VIEWS}, **filters,
                  "offset": {"type": "integer", "minimum": 0, "maximum": 1000000},
                  "limit": {"type": "integer", "minimum": 1, "maximum": 200}}),
        function("export_dashboard_csv", "Queue the same sets or recovery CSV as the web app. Supports the dashboard filters/options, including workout-name search. Unknown sets omitted; use full Excel for all original records.",
                 {"dataset": {"type": "string", "enum": ["sets", "recovery"]}, **filters}),
        function("export_next_workout_image", "Queue the current next-session proposal as a PNG attachment; no saved training changes.",
                 {"workout_type": {"type": "string", "enum": ["upper1", "upper2", "lower1", "lower2"]}}),
        function("propose_settings_change",
                 "Preview a partial patch to shared equipment or volume settings. Read get_editable_records first. changes_json: equipment {profiles:{id:{name,loads:[kg]} or null to remove},assignments:{exercise:profileId or null}}; volume {bodyWeightKg:number or null,exercises:{exercise:{multiplier,bodyweight,loadCopies,assistance,reviewed} or null}}. Omitted settings are preserved. Loads use the recorded convention, including per-dumbbell. Owner must Save; revision checked and undoable.",
                 {"section": {"type": "string", "enum": ["equipment", "volume"]}, "changes_json": string()}),
        function("get_change_history", "List recent shared workout/settings edits and Telegram previews with exact IDs and statuses. Use before undo; browser-local unsaved drafts are not shared.", {}),
        function("propose_undo_change", "Queue Save/Cancel review to undo a returned workout or metadata edit ID. Newer changes can block undo. Never guesses IDs.", {"change_id": string()}),
        function("get_food_entries", "Read saved food entries with exact IDs, quantities, macros and provenance; paginate to find older entries on busy days before correcting or deleting. Dates follow the account timezone.",
                 {"from_date": string(True), "to_date": string(True),
                  "offset": {"type": "integer", "minimum": 0, "maximum": 1000000},
                  "limit": {"type": "integer", "minimum": 1, "maximum": 200}}),
        function("propose_food_delete", "Queue Save/Cancel review to delete one saved food entry. Read its exact ID from nutrition history. Never deletes until Save.", {"entry_id": string()}),
        function("get_garmin_workout_structure", "Read the full editable Garmin template: name, description, revision and segments/steps. Required before full edits; preserve provider fields.", {"workout_id": {"type": "integer"}}),
        function("propose_garmin_structure_change",
                 "Preview full Garmin template editing, matching the web editor: name, description, exercise removal/reordering, sets/repeats, rest/duration, notes and targets. Start with returned segments, preserve unspecified fields and supported codes. segments_json is the complete edited segments array; expected_revision is exactly the read revision. Save applies; does not change completed history.",
                 {"workout_id": {"type": "integer"}, "expected_revision": string(),
                  "name": string(), "description": string(), "segments_json": string()}),
    ]


def parse_object(value, maximum=100000):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError("Provide a bounded JSON object")
    result = json.loads(value, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid number")))
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object")
    return result


def dashboard(tools, a):
    from reptrace.coaching.assistant import check_dates
    check_dates(a.get("from_date"), a.get("to_date"))
    a = dict(a)
    a.setdefault("offset", 0)
    a.setdefault("limit", 100)
    if a.get("source", "all") not in ("all", "garmin", "manual"):
        raise ValueError("Invalid source")
    for key, low, high in (("offset", 0, 1000000), ("limit", 1, 200)):
        if type(a[key]) is not int or not low <= a[key] <= high:
            raise ValueError("Invalid pagination")
    options = parse_object(a.get("options_json") or "{}", 5000)
    allowed = {"volume_mode", "grouping", "weekly", "reps", "window", "recovery_metric",
               "threshold", "left_id", "right_id", "week", "include_secondary", "compare_weeks", "search", "muscle_group"}
    if options.keys() - allowed:
        raise ValueError("Unknown dashboard option")
    for key, choices in {
        "volume_mode": ("recorded", "adjusted"), "grouping": ("muscle", "exercise"),
        "recovery_metric": ("sleepHours", "hrv", "restingHR", "sleepScore", "bodyBattery", "bodyWeightKg"),
    }.items():
        if key in options and options[key] not in choices:
            raise ValueError("Invalid " + key)
    for key, low, high in (("reps", 1, 500), ("window", 3, 12), ("compare_weeks", 1, 4)):
        if key in options and (type(options[key]) is not int or not low <= options[key] <= high):
            raise ValueError("Invalid " + key)
    if options.get("compare_weeks", 1) not in (1, 4):
        raise ValueError("Compare one or four weeks")
    for key in ("weekly", "include_secondary"):
        if key in options and type(options[key]) is not bool:
            raise ValueError("Invalid " + key)
    for key in ("search", "left_id", "right_id", "week", "muscle_group"):
        if key in options and (not isinstance(options[key], str) or len(options[key]) > 200):
            raise ValueError("Invalid " + key)
    if options.get("week"):
        check_dates(options["week"], None)
    if options.get("threshold") is not None and type(options["threshold"]) not in (int, float):
        raise ValueError("Invalid threshold")
    a["options"] = options
    if a.get("exercise"):
        a["exercise"] = tools.resolve(a["exercise"])
    if a.get("view") not in VIEWS + ["csv_sets", "csv_recovery"]:
        raise ValueError("Unknown dashboard view")
    try:
        result = subprocess.run(
            ["node", str(Path(__file__).with_name("dashboard.mjs"))],
            input=json.dumps({"data": tools.data, "args": a, "today": tools.today.isoformat()}, allow_nan=False),
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("Dashboard calculations unavailable; Node.js 22+ is required") from None
    if result.returncode:
        raise ValueError("Dashboard calculation failed. Verify filters and workout IDs.")
    return json.loads(result.stdout)


def call(tools, name, a):
    if name == "get_dashboard_view":
        return dashboard(tools, a)
    if name == "export_dashboard_csv":
        if a["dataset"] not in ("sets", "recovery"):
            raise ValueError("Unknown CSV dataset")
        result = dashboard(tools, dict(a, view="csv_" + a["dataset"]))
        tools.artifacts.append({"kind": "csv", "filename": a["dataset"] + ".csv", "text": result["text"]})
        return {"queued": True, "rows": result["count"], "delivery": "CSV file will follow."}
    if name == "export_next_workout_image":
        plan = tools.call("get_next_workout", a)
        if not plan.get("exercises"):
            raise ValueError("No recorded baseline for this workout type")
        tools.artifacts.append(dict(plan, kind="plan_image"))
        return {"queued": True, "name": plan["name"]}
    if name == "get_change_history":
        return {"workouts": tools.data.get("edits", []),
                "settings": tools.data.get("metadataEdits", []),
                "previews": [{"id": k, "status": v["status"], "preview": v["preview"], "expires": v["expires"]}
                             for k, v in tools.state.get("pendingEdits", {}).items()][-30:]}
    if name == "propose_undo_change":
        identity = a["change_id"]
        for key, action in (("edits", "undo_workout"), ("metadataEdits", "undo_metadata")):
            row = next((r for r in tools.data.get(key, []) if r["id"] == identity and not r["undone"]), None)
            if row:
                return stage(tools, {"action": action, "id": identity},
                             ["UNDO SAVED CHANGE", json.dumps(row, ensure_ascii=False),
                              "Restore the previous values. Newer edits may prevent undo."])
        raise ValueError("Change not available; read change history again")
    if name == "propose_settings_change":
        section = a["section"]
        if section not in ("equipment", "volume"):
            raise ValueError("Unknown settings section")
        patch = parse_object(a["changes_json"])
        field = "equipment" if section == "equipment" else "volumeSettings"
        before = tools.data.get(field) or ({"profiles": {}, "assignments": {}} if section == "equipment" else {"bodyWeightKg": None, "exercises": {}})
        value = deepcopy(before)
        allowed = ("profiles", "assignments") if section == "equipment" else ("bodyWeightKg", "exercises")
        if not patch or patch.keys() - set(allowed):
            raise ValueError("Empty patch or unknown settings key")
        for key, changes in patch.items():
            if key == "bodyWeightKg":
                value[key] = changes
                continue
            if not isinstance(changes, dict):
                raise ValueError("Settings mappings must be objects")
            target = value.setdefault(key, {})
            for identity, item in changes.items():
                if item is None:
                    target.pop(identity, None)
                elif isinstance(item, dict):
                    target[identity] = dict(target.get(identity, {}), **item)
                else:
                    target[identity] = item
        value = validate_equipment(value) if section == "equipment" else validate_volume_settings(value)
        if not tools.data.get("metadataRevision"):
            raise ValueError("Refresh settings before editing")
        return stage(tools, {"action": "metadata_change", "entity": section, "operation": "save",
                            "key": None, "value": value, "metadataRevision": tools.data["metadataRevision"]},
                     ["EDIT " + section.upper(), "Before: " + json.dumps(before, ensure_ascii=False),
                      "After: " + json.dumps(value, ensure_ascii=False), "Undo available after Save."])
    if name == "get_food_entries":
        from reptrace.coaching.assistant import check_dates, between
        from zoneinfo import ZoneInfo
        check_dates(a.get("from_date"), a.get("to_date"))
        offset, limit = a["offset"], a["limit"]
        if type(offset) is not int or not 0 <= offset <= 1000000 or type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("Invalid pagination")
        zone = ZoneInfo(tools.data.get("timezone") or "UTC")
        entries = sorted((entry for entry in tools.data.get("foodLog", [])
                          if between(datetime.fromisoformat(entry["time"].replace("Z", "+00:00")).astimezone(zone).date().isoformat(),
                                     a.get("from_date"), a.get("to_date"))),
                         key=lambda entry: (entry["time"], entry["id"]), reverse=True)
        return {"entries": entries[offset:offset+limit], "matchingEntries": len(entries),
                "offset": offset, "truncated": len(entries) > offset+limit}
    if name == "propose_food_delete":
        entry = next((r for r in tools.data.get("foodLog", []) if r["id"] == a["entry_id"]), None)
        if not entry:
            raise ValueError("Food entry not found; read nutrition history")
        return stage(tools, {"action": "food_delete", "id": entry["id"], "expectedEntry": entry},
                     ["DELETE FOOD ENTRY", json.dumps(entry, ensure_ascii=False),
                      "Removes this entry from daily totals. Save to confirm."])
    if name in ("get_garmin_workout_structure", "propose_garmin_structure_change"):
        if not tools.garmin:
            raise ValueError("Garmin service is unavailable")
        if name == "get_garmin_workout_structure":
            return tools.garmin({"operation": "details", "workoutId": a["workout_id"]})
        if not isinstance(a["expected_revision"], str) or not a["expected_revision"]:
            raise ValueError("Read the current Garmin revision first")
        if not isinstance(a["segments_json"], str) or len(a["segments_json"]) > 300000:
            raise ValueError("Garmin structure is too large")
        segments = json.loads(a["segments_json"])
        preview = tools.garmin({"operation": "edit", "workoutId": a["workout_id"],
                                "expectedRevision": a["expected_revision"], "name": a["name"],
                                "description": a["description"], "segments": segments})
        lines = ["EDIT GARMIN TEMPLATE: " + preview["name"]]
        lines += [str(c["label"]) + ": " + str(c["before"]) + " → " + str(c["after"])
                  for c in preview["changes"]]
        lines.append("Save applies exactly this preview. Completed training is unchanged. Expires in 15 minutes.")
        result = stage(tools, {"action": "garmin_workout_update", "previewId": preview["previewId"]}, lines)
        draft = tools.state["pendingEdits"][result["draftId"]]
        draft.update(garminPreview=preview, expires=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat())
        tools.save()
        return result
    raise ValueError("Unknown parity tool")
