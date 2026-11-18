import copy
import json
from contextlib import contextmanager
import tempfile
import unittest
from unittest.mock import Mock
import uuid
from zoneinfo import ZoneInfo
from reptrace.garmin.integration import GarminIntegration, exercise_mapping
from reptrace.garmin.creation import Creation, build_session, matches
from reptrace.garmin.operations import OperationJournal
from reptrace.garmin.workouts import GarminAdapter, saved_workout_matches
from reptrace.storage.state import WebState, Conflict, plan_workout, snapshot_rows


def fixture():
    active = {
        "setType": "ACTIVE",
        "repetitionCount": 8,
        "weight": 20000,
        "duration": 30,
        "weightUnit": "POUND",
        "exercises": [
            {
                "category": "BENCH_PRESS",
                "name": "DUMBBELL_BENCH_PRESS",
                "probability": 100,
            }
        ],
        "unknown": {"keep": True},
    }
    remote = {
        "exerciseSets": [
            copy.deepcopy(active),
            {"setType": "REST", "duration": 90, "opaque": "preserve"},
            copy.deepcopy(active),
        ],
        "unknownRoot": 17,
    }
    local = [
        {
            "measurement": "StrengthSet",
            "time": "2026-10-01T09:00:00Z",
            "tags": {
                "ActivityID": "123",
                "SetIndex": str(i),
                "Exercise": "Dumbbell Bench Press",
                "ExerciseCategory": "BENCH_PRESS",
            },
            "fields": {
                "reps": 8,
                "weightKg": 20.0,
                "source": "Garmin",
                "exerciseCode": "DUMBBELL_BENCH_PRESS",
            },
        }
        for i in (0, 2)
    ]
    return local, remote


def session(name="Synthetic A"):
    return {
        "name": name,
        "steps": [
            {
                "kind": "repeat",
                "count": 3,
                "steps": [
                    {
                        "kind": "exercise",
                        "category": "BENCH_PRESS",
                        "exerciseCode": "DUMBBELL_BENCH_PRESS",
                        "reps": 8,
                        "load": None,
                        "restSeconds": None,
                    }
                ],
            }
        ],
    }


def creation_readback(payload):
    """Synthetic response with the defaults Garmin adds to a new template."""
    actual = dict(copy.deepcopy(payload), workoutId=42)
    actual["sportType"]["displayOrder"] = 3
    for segment in actual["workoutSegments"]:
        segment["sportType"]["displayOrder"] = 3
        for key in ("description", "avgTrainingSpeed", "estimateType", "estimatedDistanceInMeters", "estimatedDistanceUnit", "estimatedDurationInSecs", "poolLength", "poolLengthUnit"):
            segment[key] = None
        def fill(steps):
            for step in steps:
                if step["type"] == "RepeatGroupDTO":
                    step.update(endCondition={"conditionTypeId":7, "conditionTypeKey":"iterations", "displayOrder":7, "displayable":False}, endConditionValue=float(step["numberOfIterations"]), skipLastRestStep=None)
                    fill(step["workoutSteps"])
                else:
                    step["endCondition"]["displayable"] = True
                    for key in ("category", "exerciseName", "description", "targetType", "weightUnit", "weightValue"):
                        step.setdefault(key, None)
                    step["equipmentType"] = {"equipmentTypeId":0, "equipmentTypeKey":None, "displayOrder":0}
                step["stepId"] = 99
                step["endConditionCompare"] = None
                step["preferredEndConditionUnit"] = None
        fill(segment["workoutSteps"])
    return actual


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.local, self.remote = fixture()
        self.adapter = Mock()
        self.adapter.activity_sets.side_effect = lambda _: copy.deepcopy(self.remote)

        def write(_, payload):
            self.remote = copy.deepcopy(payload)

        self.adapter.update_activity_sets.side_effect = write
        self.state = WebState(self.tmp.name + "/state.sqlite")
        self.state.apply = Mock(return_value={"ok": True})
        self.service = GarminIntegration(
            self.tmp.name + "/ops.sqlite",
            self.state,
            None,
            "test",
            ZoneInfo("UTC"),
            lambda: self.adapter,
        )
        self.service.local = lambda _: copy.deepcopy(self.local)

    def preview(self, changes=None):
        d = self.service.details("123")
        return self.service.preview(
            dict(
                activityId="123",
                requestId=str(uuid.uuid4()),
                localRevision=d["localRevision"],
                remoteRevision=d["remoteRevision"],
                changes=changes
                or [{"setId": "123:2", "load": 22.5, "unit": "kg", "reps": 10}],
            )
        )

    def test_full_payload_preserved_and_duplicate_save(self):
        before = copy.deepcopy(self.remote)
        op = self.preview()
        self.assertEqual(op["proposed"]["exerciseSets"][:2], before["exerciseSets"][:2])
        self.assertEqual(op["proposed"]["exerciseSets"][2]["weight"], 22500)
        self.assertEqual(op["proposed"]["exerciseSets"][2]["weightUnit"], "POUND")
        result = self.service.apply(op["id"])
        self.assertEqual(result["status"], "done")
        self.assertEqual(self.service.apply(op["id"]), result)
        self.adapter.update_activity_sets.assert_called_once()
        self.state.apply.assert_called_once()
        self.assertFalse(self.service.journal.unresolved("123"))

    def test_garmin_connect_squat_code_missing_from_fit_catalog(self):
        self.assertEqual(
            exercise_mapping("SQUAT", "OVERHEAD_BARBELL_SQUAT"),
            ("SQUAT", "OVERHEAD_BARBELL_SQUAT"),
        )
        with self.assertRaises(ValueError):
            exercise_mapping("BENCH_PRESS", "OVERHEAD_BARBELL_SQUAT")

    def test_correction_updates_all_duplicate_garmin_candidates(self):
        candidates = self.remote["exerciseSets"][2]["exercises"]
        candidates.append(dict(candidates[0], probability=75))
        change = {
            "setId": "123:2",
            "category": "LEG_CURL",
            "exerciseCode": "WEIGHTED_LEG_CURL",
        }
        preview = self.preview([change])
        proposed = preview["proposed"]["exerciseSets"][2]
        self.assertEqual(
            proposed["exercises"],
            [
                {"category": "LEG_CURL", "name": "WEIGHTED_LEG_CURL", "probability": p}
                for p in (100, 75)
            ],
        )
        self.assertEqual(proposed["repetitionCount"], 8)
        self.assertEqual(proposed["weight"], 20000)
        candidates[1]["name"] = "BARBELL_BENCH_PRESS"
        with self.assertRaisesRegex(ValueError, "explicit mapping review"):
            self.preview([change])

    def test_unknown_zero_pounds_and_assistance(self):
        op = self.preview(
            [
                {"setId": "123:0", "load": None, "unit": "kg", "reps": 0},
                {"setId": "123:2", "load": 10, "unit": "lb"},
            ]
        )
        self.assertIsNone(op["proposed"]["exerciseSets"][0]["weight"])
        self.assertEqual(op["proposed"]["exerciseSets"][0]["repetitionCount"], 0)
        self.assertAlmostEqual(op["proposed"]["exerciseSets"][2]["weight"], 4535.9237)
        self.remote["exerciseSets"][2]["exercises"] = [
            {"category": "PULL_UP", "name": "ASSISTED_PULL_UP"}
        ]
        self.local[1]["fields"]["exerciseCode"] = "ASSISTED_PULL_UP"
        op = self.preview([{"setId": "123:2", "load": 15, "unit": "kg"}])
        self.assertEqual(op["proposed"]["exerciseSets"][2]["weight"], 15000)

    def test_stale_remote_and_local_rejected(self):
        op = self.preview()
        self.remote["extra"] = "changed"
        with self.assertRaises(Conflict):
            self.service.apply(op["id"])
        self.adapter.update_activity_sets.assert_not_called()
        op = self.preview()
        self.local[0]["fields"]["reps"] = 9
        with self.assertRaises(Conflict):
            self.service.apply(op["id"])

    def test_remote_timeout_reconciles_without_second_write(self):
        op = self.preview()

        def write(_, payload):
            self.remote = copy.deepcopy(payload)
            raise TimeoutError()

        self.adapter.update_activity_sets.side_effect = write
        self.assertEqual(self.service.apply(op["id"])["status"], "done")
        self.service.apply(op["id"])
        self.adapter.update_activity_sets.assert_called_once()

    def test_uncertain_no_readback_match_never_repeats(self):
        op = self.preview()
        self.adapter.update_activity_sets.side_effect = TimeoutError()
        self.assertEqual(self.service.apply(op["id"])["status"], "remote_unresolved")
        self.service.apply(op["id"])
        self.adapter.update_activity_sets.assert_called_once()
        self.state.apply.assert_not_called()
        self.assertTrue(
            OperationJournal(self.tmp.name + "/ops.sqlite").unresolved("123")
        )

    def test_unresolved_correction_blocks_other_previews_and_confirmations(self):
        first = self.preview()
        second = self.preview([{"setId": "123:2", "reps": 12}])
        self.adapter.update_activity_sets.side_effect = TimeoutError()
        self.assertEqual(self.service.apply(first["id"])["status"], "remote_unresolved")
        with self.assertRaisesRegex(Conflict, "unresolved"):
            self.service.apply(second["id"])
        with self.assertRaisesRegex(Conflict, "unresolved"):
            self.preview([{"setId": "123:0", "reps": 10}])
        self.adapter.update_activity_sets.assert_called_once()
        self.state.apply.assert_not_called()
        # The original request can still reconcile its own durable operation.
        self.remote = copy.deepcopy(first["proposed"])
        self.assertEqual(self.service.apply(first["id"])["status"], "done")
        self.adapter.update_activity_sets.assert_called_once()

    def test_partial_save_and_retry_local_only(self):
        op = self.preview()
        self.state.apply.side_effect = RuntimeError("offline")
        result = self.service.apply(op["id"])
        self.assertEqual(result["remoteStatus"], "saved")
        self.assertEqual(result["localStatus"], "pending")
        self.state.apply.side_effect = None
        self.assertEqual(self.service.apply(op["id"])["status"], "done")
        self.adapter.update_activity_sets.assert_called_once()

    def test_intervening_local_edit_stays_pending(self):
        op = self.preview()

        def write(_, payload):
            self.remote = copy.deepcopy(payload)
            self.local[0]["fields"]["reps"] = 12

        self.adapter.update_activity_sets.side_effect = write
        self.assertEqual(self.service.apply(op["id"])["status"], "local_pending")
        self.state.apply.assert_not_called()

    def test_pending_local_retry_checks_remote_again(self):
        op = self.preview()
        self.state.apply.side_effect = RuntimeError("offline")
        self.service.apply(op["id"])
        self.remote["changedAfterSave"] = True
        self.state.apply.reset_mock()
        result = self.service.apply(op["id"])
        self.assertEqual(result["localError"], "remote_revision_conflict")
        self.state.apply.assert_not_called()

    def test_local_only_and_destination_frozen(self):
        op = self.preview()
        self.assertEqual(
            self.service.apply(op["id"], "local")["remoteStatus"], "not_requested"
        )
        self.adapter.update_activity_sets.assert_not_called()
        with self.assertRaises(Conflict):
            self.service.apply(op["id"], "both")

    def test_reject_unsupported_mapping_rest_and_arbitrary_payload(self):
        for c in [
            {"setId": "123:2", "category": "UNKNOWN", "exerciseCode": "invented"},
            {"setId": "123:1", "reps": 10},
            {"setId": "123:2", "exerciseSets": []},
        ]:
            with self.assertRaises(ValueError):
                self.preview([c])

    def test_restart_before_write_rechecks_remote(self):
        op = self.preview()
        op.update(status="intent", destination="both")
        self.service.journal.save(op)
        self.remote["version"] = 2
        with self.assertRaises(Conflict):
            self.service.apply(op["id"])
        self.adapter.update_activity_sets.assert_not_called()

    def test_reversal_restores_exercise_mapping_missing_from_current_catalog(self):
        self.local.append(
            {
                "measurement": "ActivitySummary",
                "time": "2026-10-01T09:00:00Z",
                "tags": {"ActivityID": "123", "ActivitySelector": "start"},
                "fields": {
                    "activityType": "strength_training",
                    "activityName": "Synthetic",
                    "Activity_ID": 123,
                },
            }
        )
        op = self.preview(
            [
                {"setId": f"123:{index}", "category": "PULL_UP", "exerciseCode": None}
                for index in (0, 2)
            ]
        )
        result = self.service.apply(op["id"])
        for point in self.local:
            if point["measurement"] == "StrengthSet":
                point["tags"].update(Exercise="Pull Up", ExerciseCategory="PULL_UP")
                point["fields"]["exerciseCode"] = "PULL_UP"
        with self.state.connect() as db:
            db.execute(
                "INSERT INTO audit (id,after_data,status) VALUES (?,?,'done')",
                (result["localBody"]["requestId"], json.dumps(self.local)),
            )
        reversal = self.service.reversal(
            {"requestId": str(uuid.uuid4()), "originalId": op["id"]}
        )
        body = reversal["localBody"]
        _, restored, _ = plan_workout(
            body,
            self.local,
            {"Pull Up": ("PULL_UP", "PULL_UP")},
            "test",
            ZoneInfo("UTC"),
            body["requestId"],
        )
        for row in snapshot_rows(restored):
            self.assertEqual(row["Exercise"], "Dumbbell Bench Press")
            self.assertEqual(row["ExerciseCategory"], "BENCH_PRESS")
            self.assertEqual(row["exerciseCode"], "DUMBBELL_BENCH_PRESS")


class CreationTests(unittest.TestCase):
    def test_creation_readback_accepts_defaults_but_rejects_changed_prescriptions(self):
        expected, _ = build_session(session())
        actual = creation_readback(expected)
        before = copy.deepcopy(actual)
        self.assertTrue(matches(expected, actual))
        self.assertEqual(actual, before)
        for target, key, value in (
            ("repeat", "numberOfIterations", 4),
            ("repeat", "endConditionValue", 4),
            ("repeat", "skipLastRestStep", True),
            ("repeat", "smartRepeat", True),
            ("exercise", "exerciseName", "BARBELL_BENCH_PRESS"),
            ("exercise", "description", "Different exercise"),
            ("exercise", "weightValue", 0),
            ("exercise", "endConditionValue", 12),
            ("exercise", "stepOrder", 44),
            ("rest", "endConditionValue", 60),
            ("rest", "targetType", {"workoutTargetTypeId": 1}),
            ("segment", "estimatedDurationInSecs", 600),
            ("sport", "sportTypeId", 1),
        ):
            with self.subTest(target=target, key=key):
                changed = copy.deepcopy(actual)
                segment = changed["workoutSegments"][0]
                group = segment["workoutSteps"][0]
                obj = {"repeat":group, "exercise":group["workoutSteps"][0], "rest":group["workoutSteps"][1], "segment":segment, "sport":changed["sportType"]}[target]
                obj[key] = value
                self.assertFalse(matches(expected, changed))

    def test_template_edit_readback_accepts_omitted_optional_fields(self):
        expected, _ = build_session(session())
        expected["workoutId"] = 42
        group = expected["workoutSegments"][0]["workoutSteps"][0]
        group.pop("smartRepeat")
        group["workoutSteps"][1].pop("endConditionValue")
        for step in group["workoutSteps"]:
            for key in ("targetType", "weightUnit", "weightValue", "description"):
                step.pop(key, None)
        actual = creation_readback(expected)
        actual_group = actual["workoutSegments"][0]["workoutSteps"][0]
        actual_group["smartRepeat"] = False
        actual_group["workoutSteps"][1]["endConditionValue"] = None
        self.assertTrue(saved_workout_matches(expected, actual))
        actual_group["smartRepeat"] = True
        self.assertFalse(saved_workout_matches(expected, actual))

    def test_reconcile_existing_normalized_workouts_never_recreates_them(self):
        op = self.preview([session(), session("Synthetic B")])
        op.update(status="partial", selection=[0, 1])
        for index, item in enumerate(op["items"], start=1):
            item.update(creation="unresolved", beforeIds=[])
            self.library[index] = dict(creation_readback(item["payload"]), workoutId=index)
        self.creation.journal.save(op)
        result = self.creation.apply(self.creation.journal.get(op["id"]), [0, 1])
        self.assertEqual(result["status"], "done")
        self.assertEqual([i["workoutId"] for i in result["items"]], [1, 2])
        self.adapter.create.assert_not_called()
        self.assertEqual(self.adapter.deliver.call_count, 2)
        self.creation.apply(self.creation.journal.get(op["id"]), [0, 1])
        self.assertEqual(self.adapter.deliver.call_count, 2)

    def test_adapter_decodes_http_responses_for_durable_journal(self):
        from requests import Response

        adapter = object.__new__(GarminAdapter)
        adapter.client = Mock()
        response = Response()
        response.status_code = 200
        response._content = b'{"workoutId":42}'
        adapter.client.garth.post.return_value = response
        self.assertEqual(adapter.create({"workoutName":"Synthetic"}), {"workoutId":42})
        response._content = b'[{"messageId":9}]'
        self.assertEqual(json.loads(json.dumps(adapter.deliver(42, 7, "Synthetic"))), [{"messageId":9}])
        response.status_code = 204
        response._content = b''
        self.assertIsNone(adapter.deliver(42, 7, "Synthetic"))

    def test_new_custom_exercise_preserves_name_through_create_readback_and_retry(self):
        routine = {
            "name": "Travel circuit — completely new",
            "steps": [
                {
                    "kind": "repeat",
                    "count": 2,
                    "steps": [
                        {
                            "kind": "exercise",
                            "name": "My cable press variation",
                            "category": "BENCH_PRESS",
                            "exerciseCode": "",
                            "notes": "Single handle, standing",
                            "reps": 12,
                            "load": None,
                            "restSeconds": 45,
                        }
                    ],
                }
            ],
        }
        op = self.preview([routine])
        self.adapter.create.assert_not_called()
        self.assertIn("My cable press variation", op["preview"])
        self.assertIn("no load target", op["preview"])
        result = self.creation.apply(op, None)
        self.assertEqual(result["status"], "done")
        step = result["items"][0]["readback"]["workoutSegments"][0]["workoutSteps"][0][
            "workoutSteps"
        ][0]
        self.assertEqual(step["exerciseName"], "")
        self.assertEqual(
            step["description"], "My cable press variation · Single handle, standing"
        )
        self.assertIsNone(step["weightValue"])
        self.creation.apply(result, None)
        self.adapter.create.assert_called_once()
        self.adapter.deliver.assert_called_once()

    def test_invalid_new_session_and_custom_name_are_rejected(self):
        for routine in (
            [],
            {"name": "New", "steps": [None]},
            {
                "name": "New",
                "steps": [
                    {
                        "kind": "exercise",
                        "category": "CURL",
                        "exerciseCode": "",
                        "name": " ",
                    }
                ],
            },
        ):
            with self.subTest(routine=routine), self.assertRaises(ValueError):
                build_session(routine)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.adapter = Mock()
        self.adapter.devices.return_value = [
            {"deviceId": 7, "productDisplayName": "fēnix 7 Pro"}
        ]
        self.library = {}
        self.adapter.list.side_effect = lambda: list(self.library.values())
        self.adapter.get.side_effect = lambda i: copy.deepcopy(self.library[i])

        def create(p):
            key = len(self.library) + 1
            self.library[key] = dict(copy.deepcopy(p), workoutId=key)
            return {"workoutId": key}

        self.adapter.create.side_effect = create
        self.adapter.deliver.return_value = {"ok": True}
        self.creation = Creation(
            OperationJournal(self.tmp.name + "/ops.sqlite"), lambda: self.adapter
        )

    def preview(self, sessions=None):
        return self.creation.preview(
            {"requestId": str(uuid.uuid4()), "sessions": sessions or [session()]}
        )

    def test_missing_targets_supersets_timed_and_units(self):
        s = session()
        s["steps"][0]["steps"].append(
            {
                "kind": "exercise",
                "category": "PLANK",
                "exerciseCode": "PLANK",
                "seconds": 30,
                "load": 10,
                "unit": "lb",
                "convention": "total",
                "restSeconds": 0,
            }
        )
        payload, preview = build_session(s)
        self.assertIn("open rest", preview)
        self.assertIn("no load target", preview)
        self.assertIn("30.0 s", preview)
        steps = payload["workoutSegments"][0]["workoutSteps"][0]["workoutSteps"]
        self.assertEqual(steps[0]["weightValue"], None)
        self.assertEqual(steps[1]["endCondition"]["conditionTypeKey"], "lap.button")
        self.assertEqual(steps[2]["weightUnit"]["unitKey"], "pound")

    def test_batch_readback_delivery_name_collisions_and_duplicates(self):
        op = self.preview([session(), session("Synthetic B")])
        self.library[99] = dict(op["items"][0]["payload"], workoutId=99)
        result = self.creation.apply(op, None)
        self.assertEqual(result["status"], "done")
        self.assertEqual(self.adapter.create.call_count, 2)
        self.creation.apply(result, None)
        self.assertEqual(self.adapter.create.call_count, 2)
        self.assertIn(99, self.library)
        self.assertEqual(self.creation.devices()["selectedDeviceId"], "7")

    def test_uncertain_creation_reuses_unique_candidate(self):
        original = self.adapter.create.side_effect

        def timeout(p):
            original(p)
            raise TimeoutError()

        self.adapter.create.side_effect = timeout
        self.assertEqual(self.creation.apply(self.preview(), None)["status"], "done")
        self.adapter.create.assert_called_once()

    def test_completed_creation_retry_does_not_reconnect_or_reopen_journal(self):
        op = self.creation.apply(self.preview([session(), session("B")]), [1])
        before = copy.deepcopy(op)
        self.creation.adapter = Mock(side_effect=RuntimeError("Garmin unavailable"))
        self.creation.journal.save = Mock()
        self.assertEqual(self.creation.apply(op, [1]), before)
        self.creation.adapter.assert_not_called()
        self.creation.journal.save.assert_not_called()
        with self.assertRaises(Conflict):
            self.creation.apply(op, None)

    def test_ambiguous_creation_stops_and_partial_batch_continues(self):
        original = self.adapter.create.side_effect

        def create(p):
            if p["workoutName"] == "Synthetic A":
                original(p)
                original(p)
                raise TimeoutError()
            return original(p)

        self.adapter.create.side_effect = create
        op = self.creation.apply(self.preview([session(), session("B")]), None)
        self.assertEqual(op["status"], "partial")
        self.assertEqual(op["items"][0]["creation"], "unresolved")
        self.assertEqual(op["items"][1]["delivery"], "requested")
        self.creation.apply(op, None)
        self.assertEqual(self.adapter.create.call_count, 2)

    def test_delivery_retry_does_not_recreate(self):
        error = RuntimeError()
        error.response = Mock(status_code=429)
        self.adapter.deliver.side_effect = error
        op = self.creation.apply(self.preview(), None)
        self.assertEqual(op["items"][0]["delivery"], "failed")
        self.adapter.deliver.side_effect = None
        self.assertEqual(self.creation.apply(op, None)["status"], "done")
        self.adapter.create.assert_called_once()

    def test_multiple_devices_require_selection(self):
        self.adapter.devices.return_value *= 2
        with self.assertRaises(ValueError):
            self.preview()

    def test_adapter_contracts(self):
        adapter = object.__new__(GarminAdapter)
        adapter.client = Mock()
        payload = {"exerciseSets": []}
        adapter.update_activity_sets(123, payload)
        adapter.client.garth.put.assert_called_once_with(
            "connectapi",
            "/activity-service/activity/123/exerciseSets",
            json=payload,
            api=True,
        )
        adapter.create({"workoutName": "Synthetic"})
        self.assertEqual(
            adapter.client.garth.post.call_args.args[1], "/workout-service/workout"
        )
        adapter.deliver(12, 7, "Synthetic")
        body = adapter.client.garth.post.call_args.kwargs["json"][0]
        self.assertEqual(
            body,
            {
                "deviceId": 7,
                "messageUrl": "workout-service/workout/FIT/12",
                "messageType": "workouts",
                "groupName": None,
                "messageName": "Synthetic",
                "priority": 1,
                "fileType": "FIT",
                "metaDataId": 12,
            },
        )

    def test_readback_mismatch_never_delivers(self):
        self.adapter.get.side_effect = lambda i: dict(
            self.library[i], workoutName="different"
        )
        op = self.creation.apply(self.preview(), None)
        self.assertEqual(op["items"][0]["creation"], "readback_mismatch")
        self.adapter.deliver.assert_not_called()
        self.creation.apply(op, None)
        self.adapter.create.assert_called_once()

    def test_uncertain_delivery_reconciles_queue_without_resending(self):
        self.adapter.deliver.side_effect = TimeoutError()
        self.adapter.device_messages.return_value = [{"deviceId": 7, "metaDataId": 1}]
        op = self.creation.apply(self.preview(), None)
        self.assertEqual(op["status"], "done")
        self.creation.apply(op, None)
        self.adapter.create.assert_called_once()
        self.adapter.deliver.assert_called_once()

    def test_unresolved_delivery_without_evidence_stops(self):
        self.adapter.deliver.side_effect = TimeoutError()
        self.adapter.device_messages.return_value = []
        op = self.creation.apply(self.preview(), None)
        self.assertEqual(op["items"][0]["delivery"], "uncertain")
        self.creation.apply(op, None)
        self.adapter.deliver.assert_called_once()

    def test_selection_and_request_identity_conflicts(self):
        op = self.preview([session(), session("B")])
        self.creation.apply(op, [1])
        self.adapter.create.assert_called_once()
        with self.assertRaises(Conflict):
            self.creation.apply(op, [0])
        with self.assertRaises(Conflict):
            self.creation.journal.stage(op["id"], "creation", {"different": True}, {})
