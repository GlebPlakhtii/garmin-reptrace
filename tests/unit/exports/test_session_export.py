from copy import deepcopy
from datetime import date
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
import json, sys, tempfile, threading, unittest
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from reptrace.exports.sessions import export_sessions, select_sessions, MIME, NS
from reptrace.coaching.assistant import TrainingTools
from reptrace.telegram.bot import Bot, Telegram
from reptrace.web import server as web
from tests.unit.reports.test_training_reports import records, row

N = {"m": NS}


def data():
    result = records()
    for w in result["workouts"]:
        w["source"] = "garmin"
    for r in result["sets"]:
        r["source"] = "garmin"
    result["sets"][-1].update(weight=0, volume=0, reps=8, exercise="Pull Up")
    result["sets"].append(
        row(
            "c",
            "2026-10-20",
            weight=None,
            reps=None,
            id="c:2",
            order=2,
            source="manual",
            note='=HYPERLINK("bad")',
        )
    )
    result["sets"].append(
        row("c", "2026-10-20", id="c:3", exercise="Unknown", source="garmin")
    )
    return result


def cells(body, sheet):
    with ZipFile(BytesIO(body)) as archive:
        root = ET.fromstring(archive.read(f"xl/worksheets/sheet{sheet}.xml"))
    return {c.get("r"): c for c in root.findall("m:sheetData/m:row/m:c", N)}, root


def value(cell):
    if cell.get("t") == "inlineStr":
        return cell.find("m:is/m:t", N).text or ""
    v = cell.find("m:v", N)
    return float(v.text) if v is not None else None


class ExportTests(unittest.TestCase):
    def test_workbook_has_typed_dates_numbers_filters_panes_and_summary_reconciles(
        self,
    ):
        source = data()
        before = deepcopy(source)
        body, filename, counts = export_sessions(source)
        self.assertEqual(source, before)
        self.assertEqual(counts, {"sessions": 3, "sets": 4, "bodyWeightDays": 0})
        self.assertTrue(filename.endswith(".xlsx"))
        summary, root = cells(body, 1)
        details, _ = cells(body, 2)
        self.assertEqual(
            value(summary["A7"]), (date(2026, 10, 11) - date(1899, 12, 30)).days
        )
        self.assertEqual(value(summary["C9"]), 2)
        self.assertEqual(value(summary["D9"]), 8)
        self.assertEqual(value(summary["E9"]), 0)
        self.assertEqual(value(summary["G8"]), 7)
        self.assertEqual(value(summary["H8"]), 50)
        self.assertEqual(
            root.find("m:sheetViews/m:sheetView/m:pane", N).get("state"), "frozen"
        )
        self.assertEqual(value(details["G9"]), 0)
        self.assertIsNone(value(details["G10"]))
        self.assertEqual(value(details["N10"]), '=HYPERLINK("bad")')
        self.assertEqual(details["N10"].get("t"), "inlineStr")
        self.assertFalse(any(c.find("m:f", N) is not None for c in details.values()))
        with ZipFile(BytesIO(body)) as archive:
            tables = [
                ET.fromstring(archive.read(n))
                for n in archive.namelist()
                if n.startswith("xl/tables/") and n.endswith(".xml")
            ]
            self.assertEqual(
                {t.get("ref") for t in tables}, {"A6:R9", "A6:P10", "A6:D7"}
            )
            self.assertTrue(all(t.find("m:autoFilter", N) is not None for t in tables))

    def test_inclusive_dates_sources_types_search_and_latest(self):
        d = data()
        body, _, counts = export_sessions(
            d, from_date="2026-10-20", to_date="2026-10-20", source="manual"
        )
        self.assertEqual(counts, {"sessions": 1, "sets": 1, "bodyWeightDays": 0})
        summary, _ = cells(body, 1)
        self.assertIsNone(value(summary["D7"]))
        self.assertIsNone(value(summary["E7"]))
        self.assertEqual(len(select_sessions(d, session_id="latest")[0]), 1)
        self.assertEqual(select_sessions(d, session_id="latest")[0][0]["id"], "c")
        self.assertEqual(
            len(select_sessions(d, workout_kind="upper1", search="UPPER")[0]), 3
        )
        for args in [
            dict(from_date="bad"),
            dict(from_date="2026-11-01", to_date="2026-10-01"),
            dict(source="oops"),
            dict(session_id="missing"),
            dict(search="absent"),
        ]:
            with self.assertRaises(ValueError):
                select_sessions(d, **args)

    def test_body_weight_sheet_includes_non_training_dates_and_exact_day_session_weight(
        self,
    ):
        d = data()
        d["recovery"] += [
            {
                "date": "2026-10-19",
                "bodyWeightKg": 73.1,
                "bodyWeightSource": "garmin",
                "bodyWeightTime": "2026-10-19T10:00:00Z",
            },
            {"date": "2026-10-20", "bodyWeightKg": 72.9, "bodyWeightSource": "manual"},
        ]
        body, _, counts = export_sessions(d)
        summary, _ = cells(body, 1)
        weights, _ = cells(body, 3)
        self.assertEqual(counts["bodyWeightDays"], 2)
        self.assertEqual(value(summary["R9"]), 72.9)
        self.assertIsNone(value(summary["R8"]))
        self.assertEqual(value(weights["B7"]), 73.1)
        body, _, counts = export_sessions(d, session_id="latest")
        self.assertEqual(counts["bodyWeightDays"], 1)
        self.assertEqual(value(cells(body, 3)[0]["B7"]), 72.9)

    def test_full_export_ignores_filters_and_includes_unknown_and_all_app_sheets(self):
        d = data()
        d["goals"] = [
            {
                "id": "goal-1",
                "exercise": "Pull Up",
                "mode": "reps",
                "weight": None,
                "reps": 12,
                "deadline": "",
            }
        ]
        d["archivedGoals"] = [
            {
                "id": "goal-2",
                "exercise": "Bench",
                "mode": "load_reps",
                "weight": 100,
                "reps": 5,
                "deadline": "2027-01-01",
            }
        ]
        d["progressionRules"] = {
            "Pull Up": {"repMin": 8, "repMax": 12, "weightStep": None}
        }
        d["muscleOverrides"] = {"Pull Up": "Back"}
        raw = {
            "StrengthSet": [
                {
                    "time": "2026-10-20T10:00:00Z",
                    "ActivityID": "c",
                    "SetIndex": "3",
                    "Exercise": "Unknown",
                    "rawWeight": "55:40",
                    "unmappedField": 123,
                }
            ]
        }
        body, filename, counts = export_sessions(
            d,
            full=True,
            from_date="2099-01-01",
            source="manual",
            session_id="missing",
            search="absent",
            source_records=raw,
        )
        self.assertEqual(counts["sets"], len(d["sets"]))
        self.assertIn("all-data", filename)
        details, _ = cells(body, 2)
        self.assertTrue(
            any(
                value(details["C" + str(i)]) == "Unknown"
                for i in range(7, 7 + counts["sets"])
            )
        )
        goals, _ = cells(body, 5)
        self.assertEqual(value(goals["F7"]), "Active")
        self.assertEqual(value(goals["F8"]), "Archived")
        source, _ = cells(body, 7)
        self.assertEqual(json.loads(value(source["G7"])), raw["StrengthSet"][0])
        with ZipFile(BytesIO(body)) as archive:
            names = [
                s.get("name")
                for s in ET.fromstring(archive.read("xl/workbook.xml")).findall(
                    "m:sheets/m:sheet", N
                )
            ]
            self.assertEqual(
                names,
                [
                    "Sessions",
                    "Sets",
                    "Body weight",
                    "Recovery",
                    "Goals",
                    "Settings",
                    "Source records",
                ],
            )

    def test_full_export_retains_orphaned_sets_and_handles_health_only_data(self):
        d = data()
        d["sets"].append(row("orphan", "2026-10-21", exercise="Unknown"))
        body, _, counts = export_sessions(d, full=True)
        self.assertEqual(counts["sets"], len(d["sets"]))
        self.assertEqual(counts["sessions"], 4)
        d["sets"] = []
        d["workouts"] = []
        body, _, counts = export_sessions(d, full=True)
        self.assertEqual(counts["sets"], 0)
        self.assertEqual(
            len(cells(body, 4)[1].findall('m:sheetData/m:row[@r="7"]', N)), 1
        )

    def test_large_raw_records_are_split_without_truncation_or_formula_execution(self):
        raw = {"StrengthSet": [{"note": "=" + "text💪" * 10000}]}
        body, _, _ = export_sessions(data(), full=True, source_records=raw)
        rows, root = cells(body, 7)
        chunks = [
            value(rows["G" + r.get("r")])
            for r in root.findall("m:sheetData/m:row", N)
            if int(r.get("r")) >= 7
        ]
        self.assertGreater(len(chunks), 1)
        self.assertEqual(json.loads("".join(chunks)), raw["StrengthSet"][0])

    def test_empty_set_sheet_has_no_template_sample_data(self):
        d = data()
        d["sets"] = []
        body, _, counts = export_sessions(d)
        _, root = cells(body, 2)
        self.assertEqual(counts["sets"], 0)
        self.assertFalse(root.findall('m:sheetData/m:row[@r="7"]', N))


class TelegramExportTests(unittest.TestCase):
    def test_owner_can_export_latest_and_other_users_cannot(self):
        with tempfile.TemporaryDirectory() as directory:
            api = Mock()
            fetch = Mock(return_value=data())
            bot = Bot(
                api, lambda: [], Path(directory) / "state.json", "42", fetch_data=fetch
            )

            def message(sender):
                return {
                    "update_id": 1,
                    "message": {
                        "from": {"id": sender},
                        "chat": {"id": sender, "type": "private"},
                        "text": "/export latest",
                    },
                }

            bot.handle(message(99))
            fetch.assert_not_called()
            bot.handle(message(42))
            call = api.call.call_args
            self.assertEqual(call.args[0], "sendDocument")
            self.assertTrue(call.kwargs["filename"].endswith(".xlsx"))
            self.assertEqual(
                len(
                    cells(call.kwargs["document"], 1)[1].findall(
                        'm:sheetData/m:row[@r="7"]', N
                    )
                ),
                1,
            )

    def test_natural_language_tool_queues_real_excel_artifact(self):
        t = TrainingTools(data(), {})
        result = t.call(
            "export_sessions_excel",
            dict(
                from_date=None,
                to_date=None,
                source="all",
                session_id="latest",
                workout_kind=None,
            ),
        )
        self.assertTrue(result["queued"])
        self.assertEqual(result["sessions"], 1)
        self.assertEqual(t.artifacts[0]["options"]["session_id"], "c")
        with tempfile.TemporaryDirectory() as directory:
            coach = Mock(configured=True)
            coach.answer.return_value = {
                "text": "Your workbook follows.",
                "artifacts": t.artifacts,
            }
            api = Mock()
            b = Bot(
                api,
                lambda: [],
                Path(directory) / "state.json",
                "42",
                fetch_data=data,
                coach=coach,
            )
            b.handle_chat("Export last session", "test")
            self.assertEqual(api.call.call_args.args[0], "sendDocument")
            self.assertTrue(api.call.call_args.kwargs["document"].startswith(b"PK"))

    def test_full_export_uses_shared_server_export_and_llm_can_request_it(self):
        t = TrainingTools(data(), {})
        result = t.call("export_all_data_excel", {})
        self.assertEqual(result["sets"], len(data()["sets"]))
        self.assertTrue(result["includesUnknown"])
        with tempfile.TemporaryDirectory() as directory:
            fetch = Mock(
                return_value=(
                    b"PKfull",
                    "form-all-data.xlsx",
                    {"sessions": 3, "sets": 5},
                )
            )
            api = Mock()
            b = Bot(
                api,
                lambda: [],
                Path(directory) / "state.json",
                "42",
                fetch_data=data,
                fetch_export=fetch,
            )
            b.handle(
                {
                    "update_id": 1,
                    "message": {
                        "from": {"id": 42},
                        "chat": {"id": 42, "type": "private"},
                        "text": "/export all",
                    },
                }
            )
            fetch.assert_called_once()
            self.assertEqual(api.call.call_args.kwargs["document"], b"PKfull")

    def test_upload_uses_excel_mime_type(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"ok":true,"result":{}}'
        with patch("urllib.request.urlopen", return_value=response) as request:
            Telegram("private-token").call(
                "sendDocument",
                {"chat_id": 42},
                document=b"PKxlsx",
                filename="sessions.xlsx",
            )
            self.assertIn(MIME.encode(), request.call_args.args[0].data)


class ExportHTTPTests(unittest.TestCase):
    def test_download_headers_and_bad_filter_error(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(web, "STORE") as store:
                store.get.return_value = (data(), None, None)
                client = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                client.request("GET", "/api/sessions.xlsx?session=latest")
                response = client.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("Content-Type"), MIME)
                self.assertIn("attachment;", response.getheader("Content-Disposition"))
                self.assertTrue(response.read().startswith(b"PK"))
                client.close()
                store.full_export.return_value = (
                    b"PKfull",
                    "all.xlsx",
                    {"sessions": 3, "sets": 5},
                )
                store.get.reset_mock()
                client = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                client.request("GET", "/api/sessions.xlsx?full=1&source=manual")
                response = client.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("X-Export-Sets"), "5")
                self.assertEqual(response.read(), b"PKfull")
                client.close()
                store.get.assert_not_called()
                client = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                client.request("GET", "/api/sessions.xlsx?from=invalid")
                response = client.getresponse()
                self.assertEqual(response.status, 400)
                response.read()
                client.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
