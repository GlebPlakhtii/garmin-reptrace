from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import Mock

from reptrace.storage.reader import DatabaseReader, render_extrema_report
from reptrace.storage.state import WebState


class DatabaseReaderTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.statements = []
        self.rows = []

        def query(q):
            self.statements.append(q)
            if q == "SHOW MEASUREMENTS":
                return [{"name": "HRV_Intraday"}, {"name": "Other"}]
            if q.startswith("SHOW FIELD KEYS"):
                return [
                    {"fieldKey": "hrvValue", "fieldType": "float"},
                    {"fieldKey": "note", "fieldType": "string"},
                ]
            if q.startswith("SHOW TAG KEYS"):
                return [{"tagKey": "Device"}]
            return self.rows

        self.reader = DatabaseReader(lambda: (self.client, query))

    def args(self, **kwargs):
        return dict(table="HRV_Intraday", fields=["hrvValue"], **kwargs)

    def test_schema_lists_any_measurement_and_exact_columns(self):
        self.assertEqual(len(self.reader.call("schema", table=None)["tables"]), 2)
        self.assertEqual(self.reader.call("schema", table="Other")["tags"], ["Device"])
        self.assertEqual(self.client.close.call_count, 2)

    def test_all_time_max_runs_in_database_before_limit_and_preserves_date(self):
        self.rows = [{"time": "2020-01-01T00:00:00Z", "value": 154}]
        result = self.reader.call("query", **self.args(aggregate="max"))
        self.assertEqual(
            self.statements[-1],
            'SELECT MAX("hrvValue") AS "value" FROM "HRV_Intraday" ORDER BY time DESC LIMIT 101',
        )
        self.assertEqual(result["rows"][0]["value"], 154)
        self.assertTrue(result["rows"][0]["time"].startswith("2020"))
        self.assertFalse(result["truncated"])

    def test_pagination_filters_time_and_nonfinite(self):
        self.rows = [{"hrvValue": float("nan")}, {"hrvValue": 20}, {"hrvValue": 30}]
        result = self.reader.call(
            "query",
            **self.args(
                limit=2,
                offset=4,
                order="asc",
                from_time="2020-01-01",
                filters=[{"field": "Device", "operator": "=", "value": "a' OR true"}],
            ),
        )
        self.assertTrue(result["truncated"])
        self.assertEqual(result["nextOffset"], 6)
        self.assertIsNone(result["rows"][0]["hrvValue"])
        json.dumps(result, allow_nan=False)
        self.assertIn("\"Device\" = 'a\\' OR true'", self.statements[-1])
        self.assertIn("time >= '2020-01-01T00:00:00+00:00'", self.statements[-1])
        self.assertTrue(self.statements[-1].endswith("LIMIT 3 OFFSET 4"))

    def test_invalid_queries_never_execute_select(self):
        for overrides in [
            dict(table="HRV_Intraday; DROP DATABASE x"),
            dict(fields=["*"]),
            dict(fields=["hrvValue) INTO x"]),
            dict(aggregate="max) INTO x"),
            dict(limit=201),
            dict(order="desc;DELETE"),
            dict(aggregate="max", fields=["note"]),
            dict(filters=[{"field": "Device", "operator": "= OR true", "value": "x"}]),
            dict(from_time="2026-01-01", to_time="2020-01-01"),
        ]:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.reader.call("query", **(self.args() | overrides))
        self.assertFalse(any(q.startswith("SELECT") for q in self.statements))
        self.assertEqual(self.client.close.call_count, 9)

    def test_empty_data_and_oversized_results(self):
        self.assertEqual(
            self.reader.call("query", **self.args(aggregate="max"))["rows"], []
        )
        self.rows = [{"note": "x" * 100001}]
        with self.assertRaises(ValueError):
            self.reader.call("query", table="Other", fields=["note"])

    def test_bulk_extrema_discovers_fields_aggregates_all_history_and_excludes_bookkeeping(
        self,
    ):
        queries = []

        def query(q):
            queries.append(q)
            if q == "SHOW MEASUREMENTS":
                return [
                    {"name": n}
                    for n in [
                        "HRV_Intraday",
                        "SleepSummary",
                        "StrengthSetWebArchive",
                        "DeviceSync",
                    ]
                ]
            if q.startswith("SHOW FIELD KEYS"):
                return [
                    {"fieldKey": f, "fieldType": t}
                    for f, t in [
                        ("value", "float"),
                        ("Activity_ID", "integer"),
                        ("activityId", "integer"),
                        ("note", "string"),
                    ]
                ]
            return [
                {
                    "time": "1970-01-01T00:00:00Z",
                    "min0": 0,
                    "max0": 175,
                    "count0": 200000,
                }
            ]

        client = Mock()
        result = DatabaseReader(lambda: (client, query)).call("extrema")
        self.assertEqual(result["metricCount"], 2)
        self.assertTrue(result["complete"])
        self.assertEqual(
            result["metrics"][0],
            {
                "table": "HRV_Intraday",
                "field": "value",
                "min": 0,
                "max": 175,
                "count": 200000,
            },
        )
        selects = [q for q in queries if q.startswith("SELECT")]
        self.assertEqual(len(selects), 2)
        self.assertTrue(
            all(
                'MIN("value")' in q and 'MAX("value")' in q and 'COUNT("value")' in q
                for q in selects
            )
        )
        self.assertTrue(
            all(
                "LIMIT" not in q and "WHERE" not in q and "Activity_ID" not in q
                for q in selects
            )
        )
        client.close.assert_called_once()
        html = render_extrema_report(result)
        self.assertIn(b"175", html)
        self.assertIn(b"HRV_Intraday", html)
        self.assertNotIn(b"1970", html)

    def test_bulk_extrema_keeps_partial_failures_and_missing_and_nonfinite_values_explicit(
        self,
    ):
        def query(q):
            if q == "SHOW MEASUREMENTS":
                return [{"name": "broken"}, {"name": "empty"}, {"name": "nonfinite"}]
            if "broken" in q:
                raise RuntimeError("secret connection details")
            if q.startswith("SHOW FIELD KEYS"):
                return [{"fieldKey": "value", "fieldType": "float"}]
            if "nonfinite" in q:
                return [{"min0": float("nan"), "max0": float("inf"), "count0": 1}]
            return []

        result = DatabaseReader(lambda: (Mock(), query)).call(
            "extrema", from_time="2020-01-01", to_time="2026-01-01"
        )
        self.assertFalse(result["complete"])
        self.assertEqual(
            result["failedTables"], [{"table": "broken", "error": "RuntimeError"}]
        )
        self.assertIsNone(result["metrics"][0]["min"])
        self.assertEqual(result["metrics"][0]["count"], 0)
        self.assertIsNone(result["metrics"][1]["max"])
        json.dumps(result, allow_nan=False)
        self.assertNotIn("secret", json.dumps(result))
        with self.assertRaises(ValueError):
            self.reader.call("extrema", from_time="2026-01-01", to_time="2020-01-01")

    def test_app_tables_schema_queries_and_bound_values(self):
        with tempfile.TemporaryDirectory() as directory:
            state = WebState(Path(directory) / "app.sqlite")
            self.reader.state_store = state
            with state.connect() as c:
                c.execute(
                    "INSERT INTO settings VALUES (?,?)", ("equipment", '"barbell"')
                )
                c.execute(
                    "INSERT INTO settings VALUES (?,?)", ("x' OR 1=1 --", '"test"')
                )
            schema = self.reader.call("schema", table="AppSettings")
            self.assertEqual(schema["source"], "app")
            result = self.reader.call(
                "query",
                table="AppSettings",
                fields=["key", "value"],
                filters=[{"field": "key", "operator": "=", "value": "x' OR 1=1 --"}],
            )
            self.assertEqual(len(result["rows"]), 1)
            self.assertEqual(result["rows"][0]["value"], '"test"')
            count = self.reader.call(
                "query", table="AppSettings", fields=["value"], aggregate="count"
            )
            self.assertEqual(count["rows"], [{"value": 2}])


if __name__ == "__main__":
    unittest.main()
