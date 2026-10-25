import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock

from reptrace.telegram.bot import Bot
from reptrace.telegram.conversation import Inbox, Runtime


def message(n, text="hello", reply=None):
    m = {
        "message_id": n,
        "from": {"id": 42},
        "chat": {"id": 42, "type": "private"},
        "text": text,
    }
    if reply is not None:
        m["reply_to_message"] = {"message_id": reply, "text": "old answer"}
    return {"update_id": n, "message": m}


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 100.0
        self.store = Inbox(str(Path(self.tmp.name) / "inbox.db"), lambda: self.now)
        self.addCleanup(self.store.db.close)

    def tearDown(self):
        self.tmp.cleanup()

    def test_silence_and_maximum_boundaries_order_and_duplicates(self):
        identity = self.store.ingest(message(1))
        for n in range(2, 5):
            self.now += 1.5
            self.assertEqual(self.store.ingest(message(n)), identity)
        self.assertIsNone(self.store.next())
        self.now = 106
        self.assertEqual(self.store.next()[0], identity)
        self.assertEqual(
            [u["update_id"] for u in self.store.payload(identity)], [1, 2, 3, 4]
        )
        self.assertIsNone(self.store.ingest(message(2)))
        self.assertEqual(self.store.offset(), 5)
        self.assertNotEqual(self.store.ingest(message(5)), identity)

    def test_exact_silence_boundary_starts_new_group(self):
        first = self.store.ingest(message(1))
        self.now += 2
        self.assertNotEqual(self.store.ingest(message(2)), first)

    def test_reply_commands_callbacks_and_albums_are_separate(self):
        updates = [
            message(1, reply=10),
            message(2, reply=11),
            message(3, "/menu"),
            message(4),
        ]
        updates.append({"update_id": 5, "callback_query": {"id": "a"}})
        album = message(6)
        album["message"]["media_group_id"] = "album"
        album["message"]["photo"] = [{"file_id": "x"}]
        updates.extend([album, message(7)])
        ids = [self.store.ingest(u) for u in updates]
        self.assertEqual(len(set(ids)), len(ids))

    def test_restart_active_retryable_and_queued_retained(self):
        first = self.store.ingest(message(1, "/menu"))
        self.store.next()
        second = self.store.ingest(message(2))
        restored = Inbox(str(Path(self.tmp.name) / "inbox.db"), lambda: 103)
        self.addCleanup(restored.db.close)
        self.assertEqual(
            restored.db.execute(
                "SELECT status FROM requests WHERE id=?", (first,)
            ).fetchone()[0],
            "retryable",
        )
        self.assertEqual(restored.next()[0], second)
        self.assertEqual(restored.offset(), 3)

    def runtime(self):
        api = Mock()
        count = iter(range(100, 200))
        api.call.side_effect = lambda *a, **kw: {"message_id": next(count)}
        coach = Mock(configured=True)
        bot = Bot(
            api,
            Mock(),
            Path(self.tmp.name) / "state.json",
            42,
            coach=coach,
            fetch_data=lambda: {},
        )
        runtime = Runtime(bot, lambda: self.now)
        self.addCleanup(runtime.store.db.close)
        return runtime, api

    def test_reply_mapping_multipart_and_explicit_context_excludes_recent_images(self):
        r, api = self.runtime()
        r.active = "earlier"
        r.bot.reference_context = {"workoutPreviewId": "preview-a"}
        for text in ("first part", "second part"):
            r.bot.api.call("sendMessage", {"chat_id": 42, "text": text})
        self.assertEqual(r.store.reference(42, 101)["text"], "second part")
        r.bot.state["coachHistory"] = [
            {"role": "user", "content": "other", "imageSources": [{"file_id": "wrong"}]}
        ]
        r.bot.download_images = Mock(return_value=[])
        r.bot.coach.answer.return_value = {"text": "answer", "artifacts": []}
        r.bot.handle_chat(
            "question", "next", source_messages=[message(9, reply=100)["message"]]
        )
        prompt = r.bot.coach.answer.call_args.args[0]
        self.assertIn("first part", prompt)
        self.assertIn("preview-a", prompt)
        self.assertNotIn("second part", prompt)
        self.assertEqual(r.bot.download_images.call_args.args[0], [])

    def test_uncertain_write_requires_explicit_retry_with_same_identity(self):
        r, api = self.runtime()
        r.bot.handle = Mock(side_effect=TimeoutError())
        identity = r.store.ingest(message(1, "/food synthetic"))
        r.execute(*r.store.next())
        self.assertIsNone(r.store.next())
        callback = {
            "update_id": 2,
            "callback_query": {
                "id": "retry",
                "from": {"id": 42},
                "message": {"chat": {"id": 42, "type": "private"}},
                "data": "retry:" + identity,
            },
        }
        r.receive(callback)
        self.assertEqual(r.store.next()[0], identity)

    def test_photo_and_text_share_reply_target_group_without_merging_albums(self):
        photo = message(1, "", reply=50)
        photo["message"]["photo"] = [{"file_id": "synthetic"}]
        identity = self.store.ingest(photo)
        self.now += 1
        self.assertEqual(
            self.store.ingest(message(2, "extra detail", reply=50)), identity
        )
        self.now += 2
        self.assertEqual(len(self.store.next()[1]), 2)

    def test_corrections_queue_without_interrupting_answer(self):
        r, api = self.runtime()
        entered, release = threading.Event(), threading.Event()

        def answer(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(2))
            kwargs["on_text"]("original answer")
            return {"text": "original answer", "artifacts": []}

        r.bot.coach.answer.side_effect = answer
        r.store.ingest(message(1, "/ask explain"))
        thread = threading.Thread(target=r.execute, args=r.store.next())
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            r.receive(message(2, "Actually, make it shorter"))
            self.now += 2
            r.receive(message(3, "another question"))
            self.assertTrue(thread.is_alive())
        finally:
            release.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        r.bot.coach.classify_intent.assert_not_called()
        self.assertEqual(r.bot.state["coachHistory"][-1]["content"], "original answer")
        self.assertEqual(r.store.next()[1][0]["update_id"], 2)
        self.now += 2
        self.assertEqual(r.store.next()[1][0]["update_id"], 3)
        for call in api.call.call_args_list:
            self.assertNotIn("reply_markup", call.args[1])

    def test_legacy_buttons_do_not_cancel_or_redirect(self):
        r, api = self.runtime()
        r.active = "current"
        for index, command in enumerate(("stop:current", "instead:old")):
            r.receive(
                {
                    "update_id": index + 1,
                    "callback_query": {
                        "id": str(index),
                        "from": {"id": 42},
                        "message": {"chat": {"id": 42, "type": "private"}},
                        "data": command,
                    },
                }
            )
        self.assertEqual(r.active, "current")
        self.assertIsNone(r.store.next())
        self.assertEqual(api.call.call_count, 2)
        self.assertTrue(
            all(c.args[0] == "answerCallbackQuery" for c in api.call.call_args_list)
        )

    def test_old_classification_queue_recovers_as_ordinary_work(self):
        identity = self.store.ingest(message(1))
        self.store.status(identity, "classifying")
        restored = Inbox(str(Path(self.tmp.name) / "inbox.db"), lambda: 103)
        self.addCleanup(restored.db.close)
        self.assertEqual(restored.next()[0], identity)
