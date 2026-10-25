from pathlib import Path
from io import BytesIO
from html.parser import HTMLParser
import json, re, sys, tempfile, unittest, xml.etree.ElementTree as ET
from unittest.mock import Mock, patch
from PIL import Image

from reptrace.reports.render import (
    render_report_html,
    render_report_preview,
    trend_svg,
    volume_comparisons,
)
from reptrace.telegram.bot import Bot, Telegram
from reptrace.reports.facts import session_facts, ReportWriter
from tests.unit.reports.test_training_reports import records


class RenderTests(unittest.TestCase):
    def facts(self):
        return session_facts(records(), "c")

    def test_html_is_standalone_with_computed_graphs_and_missing_recovery(self):
        facts = self.facts()
        html = render_report_html(
            facts, "Progress\nA heavier top set, but fewer total reps.", "gpt-6-sol"
        ).decode()
        HTMLParser().feed(html)
        self.assertIn("<svg", html)
        self.assertNotIn("<script", html)
        self.assertNotRegex(html, r'(src|href)="https?://')
        self.assertIn("gpt-6-sol", html)
        self.assertIn("kg·reps", html)
        self.assertIn("No recorded values", html)
        self.assertEqual(volume_comparisons(facts)[0]["before"], 880)
        self.assertEqual(volume_comparisons(facts)[0]["after"], 850)
        for svg in re.findall(r"<svg\b.*?</svg>", html, re.S):
            ET.fromstring(svg)

    def test_names_and_model_output_cannot_inject_html(self):
        facts = self.facts()
        facts["workout"]["name"] = "<script>steal()</script>"
        facts["exercises"][0]["exercise"] = "<img src=x onerror=steal()>"
        html = render_report_html(facts, "<script>bad()</script>", "gpt-6-sol").decode()
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img ", html)
        self.assertIn("&lt;script&gt;", html)

    def test_missing_points_break_chart_lines_and_zero_remains_real(self):
        svg = trend_svg(
            [("day1", 0), ("day2", None), ("day3", 10)], "#89bbff", "reps", "Test"
        )
        self.assertEqual(svg.count("<polyline"), 2)
        self.assertEqual(svg.count("<circle"), 2)
        self.assertNotIn("nan", svg.lower())
        ET.fromstring(svg)

    def test_preview_is_single_png_and_unavailable_ai_is_labelled(self):
        facts = self.facts()
        raw = render_report_preview(facts, "gpt-6-sol")
        image = Image.open(BytesIO(raw))
        self.assertEqual(image.format, "PNG")
        self.assertEqual(image.width, 1200)
        self.assertLess(image.width + image.height, 10000)
        html = render_report_html(facts, status="temporarily unavailable").decode()
        self.assertIn("AI analysis temporarily unavailable", html)
        self.assertNotIn("Analysis by gpt-6-sol", html)

    def test_explicit_luna_uses_requested_model_and_stateless_api(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"status":"completed","output":[{"type":"message","content":[{"type":"output_text","text":"Done"}]}]}'
        with patch("urllib.request.urlopen", return_value=response) as request:
            self.assertEqual(ReportWriter("key", "gpt-6-luna").write({}), "Done")
            body = json.loads(request.call_args.args[0].data)
            self.assertEqual(body["model"], "gpt-6-luna")
            self.assertFalse(body["store"])


class HtmlDeliveryTests(unittest.TestCase):
    def test_failed_html_upload_resumes_without_duplicate_preview_or_model_call(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            writer = Mock(model="gpt-6-sol")
            path = Path(directory) / "state.json"
            bot = Bot(api, lambda: [], path, "42", reporter=writer)
            api.call.side_effect = [{}, RuntimeError("offline")]
            with self.assertRaises(RuntimeError):
                bot.deliver_report(
                    "report",
                    session_facts(records(), "c"),
                    "Progress\nGood context.",
                    "gpt-6-sol",
                )
            self.assertEqual(bot.state["reportOutbox"]["report"]["next"], 1)
            api.call.side_effect = None
            api.reset_mock()
            Bot(api, lambda: [], path, "42", reporter=writer).deliver("report")
            api.call.assert_called_once()
            self.assertEqual(api.call.call_args.args[0], "sendDocument")
            self.assertIn(b"<svg", api.call.call_args.kwargs["document"])
            self.assertEqual(api.call.call_args.args[1]["chat_id"], 42)
            writer.write.assert_not_called()

    def test_html_transport_uploads_file_not_telegram_parse_mode(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"ok":true,"result":{}}'
        with patch("urllib.request.urlopen", return_value=response) as request:
            Telegram("private-token").call(
                "sendDocument",
                {"chat_id": 42},
                document=b"<!doctype html><html></html>",
                filename="report.html",
            )
            body = request.call_args.args[0].data
            self.assertIn(b'name="document"; filename="report.html"', body)
            self.assertIn(b"text/html", body)
            self.assertIn(b"<!doctype html>", body)


if __name__ == "__main__":
    unittest.main()
