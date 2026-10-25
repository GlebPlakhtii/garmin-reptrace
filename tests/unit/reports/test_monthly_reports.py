from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
import json, sys, tempfile, unittest
from unittest.mock import Mock
from PIL import Image

from reptrace.reports.monthly import (
    monthly_facts,
    render_monthly_html,
    render_monthly_preview,
)
from reptrace.telegram.bot import Bot
from tests.unit.reports.test_training_reports import records, workout, row


class MonthlyTests(unittest.TestCase):
    def test_last_completed_month_and_year_boundary(self):
        facts = monthly_facts(records(), "2027-01-03")
        self.assertEqual((facts["from"], facts["to"]), ("2026-12-01", "2026-12-31"))
        self.assertEqual(facts["priorFrom"], "2026-11-01")

    def test_explicit_current_month_is_partial_and_totals_match_real_sets(self):
        f = monthly_facts(records(), "2026-10-22", "2026-10")
        self.assertTrue(f["partial"])
        self.assertEqual(f["current"]["workouts"], 3)
        self.assertEqual(f["current"]["sets"], 3)
        self.assertEqual(sum(w["sets"] for w in f["weeks"]), 3)
        self.assertEqual(f["loadRecords"], [])
        with self.assertRaises(ValueError):
            monthly_facts(records(), "2026-10-22", "2027-01")

    def test_html_and_single_png_render_without_ai_or_recovery(self):
        f = monthly_facts(records(), "2026-11-02")
        html = render_monthly_html(f).decode()
        self.assertIn("<svg", html)
        self.assertNotIn("<script", html)
        self.assertIn("AI analysis unavailable", html)
        image = Image.open(BytesIO(render_monthly_preview(f, "gpt-6-sol", False)))
        self.assertEqual(image.format, "PNG")

    def test_first_day_schedule_runs_once_and_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [datetime(2026, 10, 22, 12, tzinfo=timezone.utc)]
            api = Mock()
            writer = Mock(configured=True, model="test-model")
            writer.write_monthly.return_value = "Progress\nMonthly context."
            path = Path(directory) / "state.json"
            kwargs = dict(
                fetch_data=records,
                reporter=writer,
                clock=lambda: now[0],
                monthly_enabled=True,
                weekly_enabled=False,
                post_enabled=False,
            )
            bot = Bot(api, lambda: [], path, "42", **kwargs)
            bot.run_reports(force=True)
            api.call.assert_not_called()
            now[0] = datetime(2026, 11, 1, 7, tzinfo=timezone.utc)
            bot.run_reports(force=True)
            self.assertEqual(bot.state["monthlyLastSent"], "2026-10")
            writer.write_monthly.assert_called_once()
            api.reset_mock()
            Bot(api, lambda: [], path, "42", **kwargs).run_reports(force=True)
            api.call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
