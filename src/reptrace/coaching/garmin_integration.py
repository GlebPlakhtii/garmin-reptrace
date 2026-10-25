"""Read/stage tools; no model-accessible confirmation handler."""

import json
import uuid
from reptrace.coaching.edits import stage


def definitions(function, string):
    return [
        function(
            "list_garmin_integration_operations",
            "Discover unfinished operations after a restart plus recent previews/results. Use IDs to inspect status or request a reviewed reversal.",
            {},
        ),
        function(
            "propose_garmin_correction_reversal",
            "Stage a NEW conflict-checked reversal of a completed combined correction using archived originals. Current local and remote state must still match the saved result. Owner must review and press Save again.",
            {"original_request_id": string()},
        ),
        function(
            "list_garmin_delivery_devices",
            "Read matching fēnix 7 Pro devices and saved selection. If multiple matches and no saved choice, ask the owner which one; never choose last-active device.",
            {},
        ),
        function(
            "propose_garmin_workout_creation",
            "Stage NEW saved workouts from text or supplied program images. sessions_json is an array of {name, description, steps}. A step is {kind:exercise, category, exerciseCode, reps:number|null, seconds:number|null, load:number|null, unit:kg|lb|null, convention:total|per-dumbbell|per-side|machine-stack|bodyweight|assistance|null, restSeconds:number|null, notes:string}. A repeat/superset is {kind:repeat,count:integer,steps:[...]} with ordered exercises. Null load means no target; null rest means open/manual rest; zero rest means none. Preserve equipment and all measurements. Use catalog mappings; ask about unreadable values/unresolved mappings. Missing reps AND seconds is an explicit open exercise target, never an invented value. Each session is reviewed before Save and send. device_id null reuses selection or only matching device. No calendar/schedule/start operations.",
            {"sessions_json": string(), "device_id": string(True)},
        ),
        function(
            "get_editable_garmin_activity_sets",
            "Read exact local source identities and the complete remote completed strength set payload. Resolve activity ID from workout history first. Repeated exercises are distinct sets. Remote weight is grams; local weightKg is kg. Use these revisions in a proposal.",
            {"activity_id": string()},
        ),
        function(
            "propose_garmin_activity_correction",
            "Stage existing-set corrections. Never add/remove sets. changes_json is an array of objects with setId and only changed fields: reps number/null; load number/null plus unit kg|lb; category and exerciseCode from the Garmin catalog. Unknown is null, zero is real. Keep assistance/load convention explicit. Ask about ambiguous quantities. The owner chooses Save to RepTrace + Garmin (default), RepTrace only, or Cancel.",
            {
                "activity_id": string(),
                "local_revision": string(),
                "remote_revision": string(),
                "changes_json": string(),
            },
        ),
        function(
            "get_garmin_integration_status",
            "Read remote/local or creation/delivery outcomes of a staged operation. Never applies changes.",
            {"request_id": string()},
        ),
    ]


def call(tools, name, a):
    if name == "list_garmin_integration_operations":
        return tools.garmin({"operation": "integration_list"})
    if name == "propose_garmin_correction_reversal":
        body = {
            "operation": "activity_reverse_preview",
            "originalId": a["original_request_id"],
        }
        body["requestId"] = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL, tools.request_id + json.dumps(body, sort_keys=True)
            )
        )
        result = tools.garmin(body)
        return stage(
            tools,
            {"action": "garmin_activity_correction", "operationId": result["id"]},
            [result["preview"]],
        )
    if name == "list_garmin_delivery_devices":
        return tools.garmin({"operation": "device_list"})
    if name == "propose_garmin_workout_creation":
        body = dict(
            operation="creation_preview",
            sessions=json.loads(a["sessions_json"]),
            deviceId=a.get("device_id"),
        )
        body["requestId"] = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL, tools.request_id + json.dumps(body, sort_keys=True)
            )
        )
        result = tools.garmin(body)
        draft = stage(
            tools,
            {"action": "garmin_workout_creation", "operationId": result["id"]},
            [result["preview"]],
        )
        tools.state["pendingEdits"][draft["draftId"]]["sessions"] = [
            i["payload"]["workoutName"] for i in result["items"]
        ]
        tools.save()
        return draft
    if name == "get_editable_garmin_activity_sets":
        return tools.garmin(
            {"operation": "activity_details", "activityId": a["activity_id"]}
        )
    if name == "get_garmin_integration_status":
        return tools.garmin(
            {"operation": "integration_status", "requestId": a["request_id"]}
        )
    body = dict(
        operation="activity_preview",
        activityId=a["activity_id"],
        localRevision=a["local_revision"],
        remoteRevision=a["remote_revision"],
        changes=json.loads(a["changes_json"]),
    )
    body["requestId"] = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL, tools.request_id + json.dumps(body, sort_keys=True)
        )
    )
    result = tools.garmin(body)
    draft = stage(
        tools,
        {"action": "garmin_activity_correction", "operationId": result["id"]},
        [result["preview"]],
    )
    return draft
