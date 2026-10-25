import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from reptrace.telegram.bot import Bot
from reptrace.coaching.assistant import TrainingTools, INTEGRATION_NAMES


class ReviewedIntegrationTests(unittest.TestCase):
    def test_model_can_stage_but_not_apply_and_confirmation_retries_same_operation(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            api.call.return_value = {"message_id": 1}
            garmin = Mock(
                return_value={
                    "id": "operation-stable",
                    "preview": "Synthetic set: 20 kg → 22.5 kg",
                }
            )
            bot = Bot(api, Mock(), Path(directory) / "state.json", "42", garmin=garmin)
            tools = TrainingTools(
                {}, bot.state, bot.save, request_id="turn", garmin=garmin
            )
            draft = tools.call(
                "propose_garmin_activity_correction",
                {
                    "activity_id": "123",
                    "local_revision": "local",
                    "remote_revision": "remote",
                    "changes_json": json.dumps(
                        [{"setId": "123:2", "load": 22.5, "unit": "kg"}]
                    ),
                },
            )
            self.assertEqual(garmin.call_args.args[0]["operation"], "activity_preview")
            self.assertFalse(any("apply" in name for name in INTEGRATION_NAMES))
            bot.send_edit_preview(draft["draftId"])
            labels = [
                b["text"]
                for row in api.call.call_args.args[1]["reply_markup"]["inline_keyboard"]
                for b in row
            ]
            self.assertIn("Save to RepTrace + Garmin", labels)
            self.assertIn("RepTrace only", labels)
            garmin.side_effect = [
                {
                    "status": "local_pending",
                    "remoteStatus": "saved",
                    "localStatus": "pending",
                },
                {"status": "done", "remoteStatus": "saved", "localStatus": "saved"},
            ]
            with patch(
                "reptrace.telegram.bot.save_action",
                side_effect=AssertionError("Wrong apply handler"),
            ):
                bot.handle_edit("edit:save:" + draft["draftId"])
                bot.handle_edit("edit:save:" + draft["draftId"])
            calls = garmin.call_args_list[-2:]
            self.assertEqual(calls[0].args[0], calls[1].args[0])
            self.assertEqual(calls[0].args[0]["requestId"], "operation-stable")
            self.assertEqual(
                bot.state["pendingEdits"][draft["draftId"]]["status"], "saved"
            )

    def test_cancel_never_applies(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            garmin = Mock(return_value={"id": "op", "preview": "Synthetic"})
            bot = Bot(api, Mock(), Path(directory) / "state.json", "42", garmin=garmin)
            tools = TrainingTools(
                {}, bot.state, bot.save, request_id="turn", garmin=garmin
            )
            draft = tools.call(
                "propose_garmin_activity_correction",
                {
                    "activity_id": "123",
                    "local_revision": "l",
                    "remote_revision": "r",
                    "changes_json": "[]",
                },
            )
            bot.handle_edit("edit:cancel:" + draft["draftId"])
            bot.handle_edit("edit:save:" + draft["draftId"])
            self.assertEqual(
                garmin.call_args.args[0]["operation"], "integration_cancel"
            )
