"""Filtered Excel snapshots using the packaged, styled workbook template."""

from collections import defaultdict
from datetime import date, datetime, timezone
from io import BytesIO
import math
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

from reptrace.training.planning import TYPES, workout_type
from reptrace.training.muscles import DEFAULT_MUSCLES

MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TEMPLATE = Path(__file__).with_name("templates") / "sessions.xlsx"
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
ET.register_namespace("", NS)


def tag(name):
    return "{" + NS + "}" + name


def known(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def total(values):
    values = [v for v in values if known(v)]
    return sum(values) if values else None


def select_sessions(
    data,
    from_date=None,
    to_date=None,
    source="all",
    session_id=None,
    workout_kind=None,
    search="",
    include_unknown=False,
):
    for value in (from_date, to_date):
        if value:
            date.fromisoformat(value)
    if from_date and to_date and from_date > to_date:
        raise ValueError("Start date must be before end date")
    if source not in ("all", "garmin", "manual"):
        raise ValueError("Invalid record source")
    if workout_kind and workout_kind not in TYPES:
        raise ValueError("Use upper1, upper2, lower1 or lower2")
    if session_id == "latest":
        latest = max(
            data.get("workouts", []),
            key=lambda w: (w["date"], w.get("time", "")),
            default=None,
        )
        if not latest:
            raise ValueError("No recorded sessions to export")
        session_id = latest["id"]
    if session_id and not any(w["id"] == session_id for w in data.get("workouts", [])):
        raise ValueError("Session not found")
    within = lambda day: (not from_date or day >= from_date) and (
        not to_date or day <= to_date
    )
    sets = [
        r
        for r in data.get("sets", [])
        if (include_unknown or r["exercise"].strip().casefold() != "unknown")
        and within(r["date"])
        and (source == "all" or r["source"] == source)
    ]
    ids = {r["sessionId"] for r in sets}
    workouts = sorted(
        (
            w
            for w in data.get("workouts", [])
            if within(w["date"])
            and (source == "all" or w["id"] in ids)
            and (not session_id or w["id"] == session_id)
            and (not workout_kind or workout_type(w["name"]) == workout_kind)
            and search.casefold() in w["name"].casefold()
        ),
        key=lambda w: (w["date"], w.get("time", ""), w["id"]),
    )
    ids = {w["id"] for w in workouts}
    sets = [r for r in sets if r["sessionId"] in ids]
    if not workouts:
        raise ValueError("No sessions match these filters")
    return workouts, sets


def col(index):
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def cell(address, value, style=None):
    attributes = {"r": address}
    if style is not None:
        attributes["s"] = style
    element = ET.Element(tag("c"), attributes)
    if value is None:
        return element
    if isinstance(value, bool):
        element.set("t", "b")
        ET.SubElement(element, tag("v")).text = "1" if value else "0"
        return element
    if isinstance(value, date):
        value = (value - date(1899, 12, 30)).days
    if known(value):
        ET.SubElement(element, tag("v")).text = str(value)
    else:
        # Explicit inline strings prevent notes/names from becoming Excel formulas.
        element.set("t", "inlineStr")
        node = ET.SubElement(ET.SubElement(element, tag("is")), tag("t"))
        node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        node.text = re.sub(
            r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff]", "", str(value)
        )[:32767]
    return element


def populate_sheet(content, rows, context, last):
    root = ET.fromstring(content)
    sheet = root.find(tag("sheetData"))
    example = sheet.find(tag("row") + '[@r="7"]')
    styles = (
        {re.sub(r"\d", "", c.get("r")): c.get("s") for c in example}
        if example is not None
        else {}
    )
    for row in list(sheet):
        if int(row.get("r")) >= 7:
            sheet.remove(row)
        elif row.get("r") == "3":
            for c in list(row):
                row.remove(c)
            row.append(cell("A3", context, styles.get("B")))
    for index, values in enumerate(rows, 7):
        row = ET.SubElement(
            sheet, tag("row"), {"r": str(index), "ht": "25", "customHeight": "1"}
        )
        for j, value in enumerate(values, 1):
            row.append(cell(f"{col(j)}{index}", value, styles.get(col(j))))
    bottom = max(7, 6 + len(rows))
    area = f"A6:{last}{bottom}"
    dimension = root.find(tag("dimension"))
    if dimension is not None:
        dimension.set("ref", f"A1:{last}{bottom}")
    auto = root.find(tag("autoFilter"))
    if auto is not None:
        auto.set("ref", area)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), area


def export_sessions(
    data,
    from_date=None,
    to_date=None,
    source="all",
    session_id=None,
    workout_kind=None,
    search="",
    full=False,
    source_records=None,
):
    if full:
        from_date = to_date = session_id = workout_kind = None
        source = "all"
        search = ""
        # Retain orphaned sets even if a source workout summary was never stored.
        data = dict(data, workouts=list(data.get("workouts", [])))
        ids = {w["id"] for w in data["workouts"]}
        for row in data.get("sets", []):
            if row["sessionId"] not in ids:
                data["workouts"].append(
                    {
                        "id": row["sessionId"],
                        "date": row["date"],
                        "time": row.get("time", ""),
                        "name": "Session summary unavailable",
                        "source": row.get("source"),
                    }
                )
                ids.add(row["sessionId"])
    if full and not data.get("workouts"):
        workouts, sets = [], []
    else:
        workouts, sets = select_sessions(
            data,
            from_date,
            to_date,
            source,
            session_id,
            workout_kind,
            search,
            include_unknown=full,
        )
    grouped = defaultdict(list)
    for row in sets:
        grouped[row["sessionId"]].append(row)
    recovery = {r["date"]: r for r in data.get("recovery", [])}
    summaries = []
    details = []
    overrides = data.get("muscleOverrides", {})
    for w in workouts:
        rows = sorted(
            grouped[w["id"]],
            key=lambda s: (s.get("order") or 0, s.get("number") or 0, s["id"]),
        )
        r = recovery.get(w["date"], {})
        summaries.append(
            [
                date.fromisoformat(w["date"]),
                w["name"],
                len(rows),
                total(s.get("reps") for s in rows),
                total(s.get("volume") for s in rows),
                w["duration"] / 60 if known(w.get("duration")) else None,
                r.get("sleepHours"),
                r.get("hrv"),
                r.get("restingHR"),
                len({s["exercise"] for s in rows}),
                sum(known(s.get("weight")) for s in rows),
                sum(known(s.get("reps")) for s in rows),
                w.get("calories"),
                w.get("averageHR"),
                w.get("maxHR"),
                w.get("source"),
                w["id"],
                r.get("bodyWeightKg"),
            ]
        )
        for s in rows:
            details.append(
                [
                    date.fromisoformat(s["date"]),
                    w["name"],
                    s["exercise"],
                    overrides.get(
                        s["exercise"], DEFAULT_MUSCLES.get(s["exercise"], "Unassigned")
                    ),
                    s.get("order"),
                    s.get("number"),
                    s.get("weight"),
                    s.get("reps"),
                    s.get("volume"),
                    s.get("estimatedMax"),
                    s.get("rest"),
                    s.get("duration"),
                    s.get("source"),
                    s.get("note"),
                    s["id"],
                    w["id"],
                ]
            )
    workout_dates = {w["date"] for w in workouts}
    weights = [
        [
            date.fromisoformat(r["date"]),
            r["bodyWeightKg"],
            r.get("bodyWeightSource", "garmin"),
            r.get("bodyWeightTime"),
        ]
        for r in sorted(data.get("recovery", []), key=lambda r: r["date"])
        if known(r.get("bodyWeightKg"))
        and (not from_date or r["date"] >= from_date)
        and (not to_date or r["date"] <= to_date)
        and (not session_id or r["date"] in workout_dates)
    ]
    extra_sheets = []
    if full:
        health_keys = [
            "sleepHours",
            "sleepScore",
            "hrv",
            "restingHR",
            "bodyBattery",
            "deepSeconds",
            "lightSeconds",
            "remSeconds",
            "awakeSeconds",
            "bodyWeightKg",
            "bodyWeightTime",
            "bodyWeightSource",
            "manualOverride",
        ]
        health = [
            [date.fromisoformat(r["date"]), *[r.get(k) for k in health_keys]]
            for r in sorted(data.get("recovery", []), key=lambda r: r["date"])
        ]
        goals = [
            [
                g.get("exercise"),
                g.get("mode"),
                g.get("weight"),
                g.get("reps"),
                date.fromisoformat(g["deadline"]) if g.get("deadline") else None,
                status,
                g.get("id"),
            ]
            for status, key in [("Active", "goals"), ("Archived", "archivedGoals")]
            for g in data.get(key, [])
        ]
        settings = [
            ["Time zone", "", data.get("timezone", "Europe/Kyiv"), None, None, None]
        ]
        settings += [
            ["Muscle mapping", k, v, None, None, None]
            for k, v in sorted(data.get("muscleOverrides", {}).items())
        ]
        settings += [
            [
                "Progression",
                k,
                "",
                v.get("repMin"),
                v.get("repMax"),
                v.get("weightStep"),
            ]
            for k, v in sorted(data.get("progressionRules", {}).items())
        ]
        settings += [
            [
                "Recovery override",
                k,
                json.dumps(v, ensure_ascii=True, allow_nan=False),
                None,
                None,
                None,
            ]
            for k, v in sorted(data.get("recoveryOverrides", {}).items())
        ]
        records = []
        for measurement, rows in (source_records or {}).items():
            for r in rows:
                encoded = json.dumps(
                    r, sort_keys=True, ensure_ascii=True, allow_nan=False, default=str
                )
                chunks = [encoded[i : i + 29000] for i in range(0, len(encoded), 29000)]
                for i, chunk in enumerate(chunks):
                    label = str(r.get("source") or "") + (
                        f" · JSON part {i + 1}/{len(chunks)}" if len(chunks) > 1 else ""
                    )
                    records.append(
                        [
                            measurement,
                            str(r.get("time") or r.get("created") or ""),
                            str(r.get("ActivityID") or ""),
                            r.get("Exercise"),
                            str(r.get("SetIndex") or ""),
                            label,
                            chunk,
                        ]
                    )
        extra_sheets = [(health, "N"), (goals, "G"), (settings, "F"), (records, "G")]
    if len(details) > 1_000_000 or any(
        len(rows) > 1_000_000 for rows, _ in extra_sheets
    ):
        raise ValueError("Too many sets; select a smaller date range")
    scope = f"{from_date or 'All history'} to {to_date or 'latest'} · {source} sets · {len(workouts)} sessions · {len(details)} sets"
    if full:
        scope = (
            "FULL EXPORT · "
            + str(len(workouts))
            + " sessions · "
            + str(len(details))
            + " sets · includes Unknown · no filters"
        )
    if workout_kind:
        scope += " · " + workout_kind
    context = (
        scope
        + " · Dates: "
        + data.get("timezone", "Europe/Kyiv")
        + " · Exported "
        + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    )
    output = BytesIO()
    with (
        ZipFile(TEMPLATE.with_name("all-data.xlsx") if full else TEMPLATE) as template,
        ZipFile(output, "w", ZIP_DEFLATED) as target,
    ):
        areas = {}
        sheets = {
            f"xl/worksheets/sheet{i}.xml": (rows, last)
            for i, (rows, last) in enumerate(
                [(summaries, "R"), (details, "P"), (weights, "D"), *extra_sheets], 1
            )
        }
        contents = {name: template.read(name) for name in template.namelist()}
        for name, (rows, last) in sheets.items():
            sheet_context = (
                context
                if name != "xl/worksheets/sheet3.xml"
                else f"{len(weights)} daily weights · {from_date or (weights[0][0] if weights else 'start')} to {to_date or (weights[-1][0] if weights else 'latest')} · "
                + data.get("timezone", "Europe/Kyiv")
            )
            contents[name], areas[name] = populate_sheet(
                contents[name], rows, sheet_context, last
            )
        # Native Excel tables retain styling and filters while growing with the export.
        for name, content in list(contents.items()):
            if re.fullmatch(r"xl/tables/table\d+\.xml", name):
                table = ET.fromstring(content)
                area = areas[
                    {
                        "SessionsTable": "xl/worksheets/sheet1.xml",
                        "SetsTable": "xl/worksheets/sheet2.xml",
                        "BodyweightTable": "xl/worksheets/sheet3.xml",
                        "RecoveryTable": "xl/worksheets/sheet4.xml",
                        "GoalsTable": "xl/worksheets/sheet5.xml",
                        "SettingsTable": "xl/worksheets/sheet6.xml",
                        "SourcerecordsTable": "xl/worksheets/sheet7.xml",
                    }[table.get("name")]
                ]
                table.set("ref", area)
                auto = table.find(tag("autoFilter"))
                if auto is not None:
                    auto.set("ref", area)
                contents[name] = ET.tostring(
                    table, encoding="utf-8", xml_declaration=True
                )
        for name, content in contents.items():
            target.writestr(name, content)
    filename = (
        f"garmin-reptrace-sessions-{workouts[0]['date']}-{workouts[-1]['date']}.xlsx"
        if workouts
        else "garmin-reptrace-data.xlsx"
    )
    if full:
        filename = (
            "garmin-reptrace-all-data-"
            + datetime.now(timezone.utc).date().isoformat()
            + ".xlsx"
        )
    return (
        output.getvalue(),
        filename,
        {
            "sessions": len(workouts),
            "sets": len(details),
            "bodyWeightDays": len(weights),
        },
    )
