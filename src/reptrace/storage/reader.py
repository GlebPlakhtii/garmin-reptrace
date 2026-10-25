"""Schema discovery and structured, read-only queries for the private coach."""

from datetime import datetime, timezone
import json
import math
import re
from html import escape

APP_TABLES = {"AppGoals": "goals", "AppSettings": "settings", "AppAudit": "audit"}
AGGREGATES = ("max", "min", "mean", "sum", "count", "first", "last")
OPERATORS = ("=", "!=", ">", ">=", "<", "<=")


def identifier(value):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 256
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError("Invalid table or column name")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def literal(value):
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)) and math.isfinite(value):
        return str(value)
    if (
        isinstance(value, str)
        and len(value) <= 2000
        and not any(ord(c) < 32 for c in value)
    ):
        return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
    raise ValueError("Filter values must be finite numbers, booleans or short strings")


def timestamp(value):
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def clean(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


class DatabaseReader:
    def __init__(self, factory, state_store=None):
        self.factory = factory
        self.state_store = state_store

    def schema(self, query, table):
        tables = [r["name"] for r in query("SHOW MEASUREMENTS")]
        if self.state_store:
            tables += list(APP_TABLES)
        if table is None:
            return {
                "tables": [
                    {
                        "name": name,
                        "source": "app" if name in APP_TABLES else "influxdb",
                    }
                    for name in sorted(set(tables))
                ]
            }
        if table not in tables:
            raise ValueError("Unknown table; discover tables first")
        if table in APP_TABLES:
            with self.state_store.lock, self.state_store.connect() as connection:
                columns = [
                    {"name": r["name"], "type": r["type"]}
                    for r in connection.execute(
                        "PRAGMA table_info(" + APP_TABLES[table] + ")"
                    )
                ]
            return {
                "table": table,
                "source": "app",
                "fields": columns,
                "tags": [],
                "timeColumn": "created" if table == "AppAudit" else None,
            }
        quoted = identifier(table)
        return {
            "table": table,
            "source": "influxdb",
            "fields": [
                {"name": r["fieldKey"], "type": r["fieldType"]}
                for r in query("SHOW FIELD KEYS FROM " + quoted)
            ],
            "tags": [r["tagKey"] for r in query("SHOW TAG KEYS FROM " + quoted)],
            "timeColumn": "time",
        }

    def call(self, operation, **args):
        client, query = self.factory()
        try:
            if operation == "schema":
                return self.schema(query, args.get("table"))
            if operation == "extrema":
                return self.extrema(query, **args)
            if operation != "query":
                raise ValueError("Unknown database operation")
            return self.read(query, **args)
        finally:
            client.close()

    def extrema(self, query, from_time=None, to_time=None):
        """One aggregate scan per measurement, instead of two model turns per field."""
        start, end = timestamp(from_time), timestamp(to_time)
        if start and end and start > end:
            raise ValueError("Start time must precede end time")
        names = sorted({r["name"] for r in query("SHOW MEASUREMENTS")})
        metrics, excluded, failures = [], [], []
        for table in names:
            if re.search(
                r"archive|^DeviceSync$|^DemoPoint$|^StrengthManual", table, re.I
            ):
                excluded.append(table)
                continue
            try:
                fields = sorted(
                    {
                        r["fieldKey"]
                        for r in query("SHOW FIELD KEYS FROM " + identifier(table))
                        if r["fieldType"] in ("float", "integer", "unsigned")
                    }
                )
                fields = [
                    f
                    for f in fields
                    if not re.search(
                        r"(^|_)(id|index|sport|latitude|longitude)$|Id$|ID$|^set(Number|Order|Count)$|^sourceRow$|^SleepStageLevel$",
                        f,
                        re.I,
                    )
                ]
                if not fields:
                    excluded.append(table)
                    continue
                selections = []
                for i, field in enumerate(fields):
                    selections.extend(
                        function
                        + "("
                        + identifier(field)
                        + ') AS "'
                        + alias
                        + str(i)
                        + '"'
                        for function, alias in (
                            ("MIN", "min"),
                            ("MAX", "max"),
                            ("COUNT", "count"),
                        )
                    )
                statement = (
                    "SELECT " + ", ".join(selections) + " FROM " + identifier(table)
                )
                conditions = []
                if start:
                    conditions.append("time >= " + literal(start))
                if end:
                    conditions.append("time <= " + literal(end))
                if conditions:
                    statement += " WHERE " + " AND ".join(conditions)
                rows = query(statement)
                values = rows[0] if rows else {}
                for i, field in enumerate(fields):
                    metrics.append(
                        {
                            "table": table,
                            "field": field,
                            "min": values.get("min" + str(i)),
                            "max": values.get("max" + str(i)),
                            "count": values.get("count" + str(i), 0),
                        }
                    )
            except Exception as error:
                # Do not leak query text or connection details into the chat.
                failures.append({"table": table, "error": type(error).__name__})
        return clean(
            {
                "metrics": metrics,
                "metricCount": len(metrics),
                "fromTime": start,
                "toTime": end,
                "excludedTables": excluded,
                "failedTables": failures,
                "complete": not failures,
                "notes": "All stored history unless time bounds supplied. Numeric health/activity/training fields; excludes archives, IDs, coordinates, categorical codes and import bookkeeping. Raw source units (BodyComposition.weight is grams; sleep durations are seconds); no dashboard overrides. Zeros and negative readings are retained, including possible sensor sentinels. Null means missing, not zero. Different sampling intervals and activity/exercise types are separate contexts; per-set load extrema mix exercises. No event dates: combined aggregates do not preserve individual extreme timestamps. Use a single-field min/max query for an event date.",
            }
        )

    def read(
        self,
        query,
        table,
        fields,
        aggregate=None,
        from_time=None,
        to_time=None,
        filters=None,
        order="desc",
        limit=100,
        offset=0,
    ):
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 200
        ):
            raise ValueError("Limit must be 1–200")
        if (
            not isinstance(offset, int)
            or isinstance(offset, bool)
            or not 0 <= offset <= 1000000
        ):
            raise ValueError("Offset must be 0–1000000")
        if order not in ("asc", "desc") or aggregate not in (None, *AGGREGATES):
            raise ValueError("Unsupported ordering or aggregate")
        if (
            not isinstance(fields, list)
            or not 1 <= len(fields) <= 20
            or not all(isinstance(f, str) for f in fields)
        ):
            raise ValueError("Select 1–20 column names from the schema")
        if aggregate and (len(fields) != 1 or offset):
            raise ValueError("Aggregates require exactly one field and offset 0")
        filters = [] if filters is None else filters
        if not isinstance(filters, list) or len(filters) > 12:
            raise ValueError("Use at most 12 filters")
        start, end = timestamp(from_time), timestamp(to_time)
        if start and end and start > end:
            raise ValueError("Start time must precede end time")
        schema = self.schema(query, table)
        columns = {r["name"] for r in schema["fields"]} | set(schema["tags"])
        if schema["timeColumn"]:
            columns.add(schema["timeColumn"])
        for field in fields:
            if field not in columns:
                raise ValueError("Unknown column: " + field)
        for f in filters:
            if (
                not isinstance(f, dict)
                or f.get("field") not in columns
                or f.get("operator") not in OPERATORS
            ):
                raise ValueError("Invalid filter column or operator")
            literal(f.get("value"))
        if aggregate and fields[0] not in {r["name"] for r in schema["fields"]}:
            raise ValueError("Aggregate requires a field, not a tag or timestamp")
        if aggregate in ("min", "max", "mean", "sum"):
            types = {
                r["type"].lower() for r in schema["fields"] if r["name"] == fields[0]
            }
            if not types & {"float", "integer", "unsigned", "real", "int"}:
                raise ValueError("This aggregate requires a numeric field")
        if schema["source"] == "app":
            rows = self.read_app(
                schema, fields, aggregate, start, end, filters, order, limit, offset
            )
        else:
            selected = ", ".join(identifier(f) for f in fields)
            if aggregate:
                selected = (
                    aggregate.upper() + "(" + identifier(fields[0]) + ') AS "value"'
                )
            clauses = [
                identifier(f["field"]) + " " + f["operator"] + " " + literal(f["value"])
                for f in filters
            ]
            if start:
                clauses.append("time >= " + literal(start))
            if end:
                clauses.append("time <= " + literal(end))
            statement = "SELECT " + selected + " FROM " + identifier(table)
            if clauses:
                statement += " WHERE " + " AND ".join(clauses)
            # No GROUP BY: aggregates scan every matching point before LIMIT.
            statement += " ORDER BY time " + order.upper() + " LIMIT " + str(limit + 1)
            if offset:
                statement += " OFFSET " + str(offset)
            rows = query(statement)
        result = {
            "table": table,
            "fields": fields,
            "aggregate": aggregate,
            "fromTime": start,
            "toTime": end,
            "rows": clean(rows[:limit]),
            "returnedRows": min(len(rows), limit),
            "truncated": len(rows) > limit,
            "nextOffset": offset + limit if len(rows) > limit else None,
            "scope": "All matching stored records; raw source values, without dashboard overrides.",
            "timestampMeaning": "Original record time for raw rows and min/max/first/last; aggregate time otherwise is not a record date.",
        }
        if len(json.dumps(result, default=str)) > 100000:
            raise ValueError(
                "Result exceeds 100 KB; select fewer columns or a smaller limit"
            )
        return result

    def read_app(
        self, schema, fields, aggregate, start, end, filters, order, limit, offset
    ):
        # Names are schema-validated; all values use SQLite bound parameters.
        quote = lambda s: '"' + s.replace('"', '""') + '"'
        time_column = schema["timeColumn"]
        if (start or end) and not time_column:
            raise ValueError("This app table has no time column")
        selected = ", ".join(quote(f) for f in fields)
        ordering = time_column or ("id" if schema["table"] != "AppSettings" else "key")
        if aggregate in ("first", "last"):
            raise ValueError(
                "For app tables, use raw rows ordered asc/desc with limit 1"
            )
        if aggregate:
            selected = (
                ("AVG" if aggregate == "mean" else aggregate.upper())
                + "("
                + quote(fields[0])
                + ') AS "value"'
            )
        clauses = [quote(f["field"]) + " " + f["operator"] + " ?" for f in filters]
        values = [f["value"] for f in filters]
        for bound, operator in ((start, ">="), (end, "<=")):
            if bound:
                clauses.append(
                    "julianday("
                    + quote(time_column)
                    + ") "
                    + operator
                    + " julianday(?)"
                )
                values.append(bound)
        statement = "SELECT " + selected + " FROM " + APP_TABLES[schema["table"]]
        if clauses:
            statement += " WHERE " + " AND ".join(clauses)
        if not aggregate:
            statement += " ORDER BY " + quote(ordering) + " " + order.upper()
        statement += " LIMIT ? OFFSET ?"
        with self.state_store.lock, self.state_store.connect() as connection:
            return [
                dict(r)
                for r in connection.execute(statement, [*values, limit + 1, offset])
            ]


def render_extrema_report(result):
    """Complete deterministic report, so the chat need not squeeze every row into prose."""
    rows = "".join(
        "<tr>"
        + "".join(
            "<td>" + escape(str(value) if value is not None else "—") + "</td>"
            for value in (r["table"], r["field"], r["min"], r["max"], r["count"])
        )
        + "</tr>"
        for r in result["metrics"]
    )
    failed = ", ".join(r["table"] for r in result["failedTables"]) or "None"
    html = (
        '<!doctype html><meta charset="utf-8"><title>Metric minimums and maximums</title>'
        "<style>body{font:16px system-ui;margin:24px;color:#222}table{border-collapse:collapse;width:100%}"
        "th,td{text-align:left;padding:8px;border-bottom:1px solid #ddd}th{background:#eee}p{max-width:1000px}</style>"
        "<h1>Metric minimums and maximums</h1><p>"
        + str(result["metricCount"])
        + " numeric metrics. Period: "
        + escape(result["fromTime"] or "earliest stored record")
        + " to "
        + escape(result["toTime"] or "latest stored record")
        + ".</p><p>"
        + escape(result["notes"])
        + "</p><p>Failed tables: "
        + escape(failed)
        + ".</p><p>Excluded tables: "
        + escape(", ".join(result["excludedTables"]))
        + ".</p><table><thead><tr><th>Table</th><th>Metric (source units)</th><th>Minimum</th><th>Maximum</th><th>Recorded values</th>"
        "</tr></thead><tbody>" + rows + "</tbody></table>"
    )
    return html.encode()
