from html import unescape
from html.parser import HTMLParser
from pathlib import Path
import sys, tempfile, unittest
from unittest.mock import Mock, patch

from reptrace.telegram.formatting import format_chat_text, split_rich_text
from reptrace.telegram.bot import Bot


class Parsed(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.text = []
        self.tags = []
        self.feed(source)
        assert not self.stack

    def handle_starttag(self, tag, attrs):
        assert tag in ("b", "i", "s", "pre", "code", "blockquote", "a"), tag
        if tag in ("pre", "code"):
            assert not self.stack
        self.stack.append(tag)
        self.tags.append(tag)

    def handle_endtag(self, tag):
        assert self.stack.pop() == tag

    def handle_data(self, text):
        self.text.append(text)

    @property
    def plain(self):
        return "".join(self.text)


class FormattingTests(unittest.TestCase):
    def test_common_markdown_becomes_telegram_html(self):
        source = "## Session progress\n\n- **Bench:** `80 kg × 6`\n- *Keep the load* and ~~old target~~\n> Recovery is context.\n[Report](https://example.com/report?a=1&b=2)"
        result = format_chat_text(source)
        parsed = Parsed(result)
        self.assertIn("<b>Session progress</b>", result)
        self.assertIn("• <b>Bench:</b> <code>80 kg × 6</code>", result)
        self.assertTrue(
            set(("b", "i", "s", "code", "blockquote", "a")).issubset(parsed.tags)
        )
        self.assertIn("a=1&amp;b=2", result)

    def test_raw_html_and_unsafe_links_are_never_executed(self):
        source = "<script>bad()</script> <b>literal</b> [unsafe](javascript:alert) & >"
        result = format_chat_text(source)
        self.assertEqual(Parsed(result).plain, source)
        self.assertNotIn("<script>", result)
        self.assertNotIn("<a ", result)

    def test_code_is_literal_and_unclosed_fence_is_closed(self):
        result = format_chat_text("```text\n**literal** <tag> & _raw_\n")
        self.assertIn("<pre>**literal** &lt;tag&gt; &amp; _raw_\n</pre>", result)
        Parsed(result)
        result = format_chat_text("**Target `80 kg`**")
        self.assertIn("<b>Target 80 kg</b>", result)
        Parsed(result)

    def test_long_messages_keep_balanced_tags_and_all_unicode_text(self):
        for source in [
            "**" + ("Progress 💪 & < > " * 700) + "**",
            "```\n" + ("80 kg × 6\n" * 800) + "```",
            "> " + ("Recovery " * 2000),
            "[**" + ("Link " * 2000) + "**](https://example.com)",
        ]:
            parts = split_rich_text(source)
            self.assertGreater(len(parts), 1)
            self.assertEqual(
                "".join(Parsed(p).plain for p in parts),
                Parsed(format_chat_text(source)).plain,
            )
            self.assertTrue(
                all(
                    len(Parsed(p).plain.encode("utf-16-le")) // 2 <= 3500 for p in parts
                )
            )

    def test_underscores_and_incomplete_markers_are_readable(self):
        source = "body_weight, activity_id, 2 * 3, **unfinished, 80 kg × 6"
        self.assertEqual(Parsed(format_chat_text(source)).plain, source)

    def test_chat_outbox_delivers_rich_chunks_without_double_escaping(self):
        with tempfile.TemporaryDirectory() as directory:
            coach = Mock(configured=True)
            coach.answer.return_value = {
                "text": "**Progress**\n- *Improved* & steady",
                "artifacts": [],
            }
            bot = Bot(
                Mock(),
                lambda: [],
                Path(directory) / "state.json",
                "42",
                fetch_data=lambda: {"sets": [], "workouts": []},
                coach=coach,
            )
            bot.handle_chat("progress?", "1")
            values = bot.api.call.call_args.args[1]
            self.assertEqual(values["parse_mode"], "HTML")
            self.assertIn("<b>Progress</b>", values["text"])
            self.assertIn("<i>Improved</i>", values["text"])
            self.assertNotIn("&amp;amp;", values["text"])

    def test_old_pending_outbox_remains_deliverable(self):
        with tempfile.TemporaryDirectory() as directory:
            bot = Bot(
                Mock(),
                lambda: [],
                Path(directory) / "state.json",
                "42",
                fetch_data=lambda: {},
                coach=Mock(configured=True),
            )
            bot.state["chatOutbox"] = {
                "old": {"parts": ["**Progress**"], "plans": [], "next": 0}
            }
            bot.handle_chat("ignored", "old")
            self.assertEqual(bot.api.call.call_args.args[1]["text"], "<b>Progress</b>")


if __name__ == "__main__":
    unittest.main()
