"""Calendar-month facts and portable monthly reviews."""

from collections import defaultdict
from datetime import date, timedelta
from html import escape

from reptrace.training.metrics import known, total
from reptrace.reports.facts import week_metrics, compare_sessions, fmt, signed
from reptrace.reports.render import (
    CSS,
    analysis_html,
    volume_svg,
    trend_svg,
    render_report_preview,
)


def month_start(day):
    return day.replace(day=1)


def month_end(day):
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def monthly_facts(data, today=None, month=None):
    today = (
        date.fromisoformat(today) if isinstance(today, str) else today or date.today()
    )
    if month:
        if len(month) != 7:
            raise ValueError("Use a month in YYYY-MM format")
        start = date.fromisoformat(month + "-01")
        if start > today:
            raise ValueError("A future month has no completed review")
    else:
        start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    end = min(month_end(start), today)
    previous_end = start - timedelta(days=1)
    previous_start = previous_end.replace(day=1)
    current = week_metrics(data, start.isoformat(), end.isoformat())
    prior = week_metrics(data, previous_start.isoformat(), previous_end.isoformat())
    all_rows = [
        r for r in data.get("sets", []) if r["exercise"].strip().casefold() != "unknown"
    ]
    rows = [r for r in all_rows if start.isoformat() <= r["date"] <= end.isoformat()]
    old = [
        r
        for r in all_rows
        if previous_start.isoformat() <= r["date"] <= previous_end.isoformat()
    ]
    exercises = []
    for name in sorted({r["exercise"] for r in rows}):
        now = [r for r in rows if r["exercise"] == name]
        before = [r for r in old if r["exercise"] == name]
        comparison = compare_sessions(now, before)
        exercises.append(
            {
                "exercise": name,
                "sets": len(now),
                "before": comparison["before"],
                "after": comparison["after"],
                "repChange": comparison["repChange"],
                "volumeChange": comparison["volumeChange"],
                "topLoadChange": comparison["topLoadChange"],
            }
        )
    weekly = defaultdict(list)
    for r in rows:
        d = date.fromisoformat(r["date"])
        weekly[(d - timedelta(days=d.weekday())).isoformat()].append(r)
    weeks = []
    d = start - timedelta(days=start.weekday())
    while d <= end:
        items = weekly[d.isoformat()]
        weeks.append(
            {
                "week": d.isoformat(),
                "sets": len(items),
                "reps": total(r.get("reps") for r in items) if items else 0,
                "volume": total(r.get("volume") for r in items) if items else 0,
                "partial": d < start or d + timedelta(days=6) > end,
            }
        )
        d += timedelta(days=7)
    records = []
    for e in exercises:
        earlier = [
            r
            for r in all_rows
            if r["exercise"] == e["exercise"]
            and r["date"] < start.isoformat()
            and known(r.get("weight"))
            and r["weight"] > 0
        ]
        latest = [
            r
            for r in rows
            if r["exercise"] == e["exercise"]
            and known(r.get("weight"))
            and r["weight"] > 0
        ]
        if (
            earlier
            and latest
            and max(r["weight"] for r in latest) > max(r["weight"] for r in earlier)
        ):
            records.append(
                {
                    "exercise": e["exercise"],
                    "before": max(r["weight"] for r in earlier),
                    "after": max(r["weight"] for r in latest),
                }
            )
    return {
        "month": start.strftime("%Y-%m"),
        "from": start.isoformat(),
        "to": end.isoformat(),
        "priorFrom": previous_start.isoformat(),
        "priorTo": previous_end.isoformat(),
        "partial": end < month_end(start),
        "current": current,
        "prior": prior,
        "exercises": exercises,
        "weeks": weeks,
        "loadRecords": records,
        "dataQuality": {
            "currentZeroWeightedLoads": sum(
                r.get("weight") == 0
                and r["exercise"].casefold()
                not in ("pull up", "push up", "dip", "sit up", "leg raise")
                for r in rows
            ),
            "priorZeroWeightedLoads": sum(
                r.get("weight") == 0
                and r["exercise"].casefold()
                not in ("pull up", "push up", "dip", "sit up", "leg raise")
                for r in old
            ),
        },
        "goals": data.get("goals", []),
        "note": "Calendar periods. External kg*reps only; missing measurements excluded; bodyweight is not added. More volume is not automatically better.",
    }


def monthly_preview_facts(facts):
    current = facts["current"]
    return {
        "workout": {
            "name": "Monthly review · " + facts["month"],
            "date": facts["from"] + " → " + facts["to"],
        },
        "totals": current,
        "sameDayRecovery": {k: v["value"] for k, v in current["recovery"].items()},
        "exercises": [
            {
                "exercise": e["exercise"],
                "sets": [{"volume": e["after"]["volume"]}],
                "comparisonToPrevious": {"before": {"volume": e["before"]["volume"]}},
            }
            for e in facts["exercises"]
        ],
    }


def render_monthly_preview(facts, model, available):
    return render_report_preview(
        monthly_preview_facts(facts),
        model,
        available,
        banner="MONTHLY REVIEW",
        previous_label="Previous month",
        recovery_label="Month averages · ",
        current_label="Selected month",
    )


def render_monthly_html(facts, analysis="", model="gpt-6-sol", status="unavailable"):
    esc = lambda v: escape(str(v), quote=True)
    c, p = facts["current"], facts["prior"]
    metrics = [
        ("Workouts", c["workouts"], signed(c["workouts"] - p["workouts"])),
        ("Recorded sets", c["sets"], signed(c["sets"] - p["sets"])),
        (
            "Recorded reps",
            c["reps"],
            signed(c["reps"] - p["reps"])
            if known(c["reps"]) and known(p["reps"])
            else "—",
        ),
        (
            "kg·reps",
            c["volume"],
            signed(c["volume"] - p["volume"])
            if known(c["volume"]) and known(p["volume"])
            else "—",
        ),
    ]
    body = f'<header><div class="eyebrow">GARMIN REPTRACE / Monthly review</div><h1>{esc(facts["month"])}</h1><p class="meta">{facts["from"]} → {facts["to"]} · compared with {facts["priorFrom"]} → {facts["priorTo"]}</p></header>'
    if facts["partial"]:
        body += '<p class="notice">This month is incomplete. The previous month is complete; differences are not adjusted for elapsed days.</p>'
    if facts.get("dataQuality", {}).get("priorZeroWeightedLoads"):
        body += f'<p class="notice">The previous month contains {facts["dataQuality"]["priorZeroWeightedLoads"]} zero-load sets for weighted exercises. These may reflect unentered watch loads; recorded tonnage differences may reflect recording coverage.</p>'
    body += (
        '<div class="metrics">'
        + "".join(
            f'<div class="metric"><small>{label}</small><strong>{fmt(value, 0)}</strong><span>{change} vs previous month</span></div>'
            for label, value, change in metrics
        )
        + "</div><section><h2>Monthly interpretation</h2>"
        + analysis_html(analysis, model, status)
        + "</section>"
    )
    body += (
        '<section class="panel"><h2>Exercise volume</h2><div class="legend"><span><i class="previous"></i>Previous month</span><span><i class="current"></i>Selected month</span></div><div class="scroll">'
        + volume_svg(monthly_preview_facts(facts))
        + '</div><p class="caption">External kg × reps; bodyweight is not added. Missing volumes are excluded.</p></section>'
    )
    body += (
        '<section class="panel"><h2>Weekly sets within this month</h2>'
        + trend_svg(
            [(w["week"], w["sets"]) for w in facts["weeks"]],
            "#89bbff",
            "sets",
            "Recorded weekly sets within month",
        )
        + '<p class="caption">Weeks start Monday; boundary weeks include only dates inside the selected month.</p></section>'
    )
    body += (
        '<section class="panel"><h2>Exercise changes</h2><div class="scroll"><table><thead><tr><th>Exercise</th><th>Sets</th><th>Reps</th><th>kg·reps</th><th>Rep change</th><th>Volume change</th></tr></thead><tbody>'
        + "".join(
            f"<tr><td>{esc(e['exercise'])}</td><td>{e['sets']}</td><td>{fmt(e['after']['reps'], 0)}</td><td>{fmt(e['after']['volume'], 0)}</td><td>{signed(e['repChange'])}</td><td>{signed(e['volumeChange'])}</td></tr>"
            for e in facts["exercises"]
        )
        + "</tbody></table></div></section>"
    )
    body += '<section><h2>Recovery averages</h2><div class="recovery-grid">'
    for key, label, unit in [
        ("sleepHours", "Sleep", "h"),
        ("hrv", "Overnight HRV", "ms"),
        ("restingHR", "Resting HR", "bpm"),
        ("bodyWeightKg", "Body weight", "kg"),
    ]:
        a, b = c["recovery"][key], p["recovery"][key]
        body += f'<article class="panel"><h3>{label}</h3><strong class="recovery-value">{fmt(a["value"])} {unit}</strong><p class="caption">Previous {fmt(b["value"])} {unit}<br>{a["days"]} recorded days in selected month</p></article>'
    body += '</div></section><section class="panel"><h2>Established-load records</h2>'
    body += (
        "".join(
            f"<p>{esc(r['exercise'])}: {fmt(r['before'])} → {fmt(r['after'])} kg</p>"
            for r in facts["loadRecords"]
        )
        or '<p class="muted">No higher established load record in the selected month.</p>'
    )
    body += (
        "</section><footer>Calendar-month report. Missing values remain missing. First-ever appearances are not claimed as personal records. Watch readings do not establish causation. "
        + esc(facts["note"])
        + "</footer>"
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;; base-uri &#39;none&#39;"><title>Garmin RepTrace monthly review '
        + facts["month"]
        + "</title><style>"
        + CSS
        + '</style></head><body><main class="sheet">'
        + body
        + "</main></body></html>"
    ).encode()


def render_quality_html(review):
    esc = lambda v: escape(str(v), quote=True)
    rows = "".join(
        f'<tr><td>{esc(r["exercise"])}</td><td>{esc(r["kind"].replace("_", " "))}</td><td>{r["sets"]}</td><td style="white-space:normal">{esc(r["detail"])}<br><small>{esc(", ".join(r.get("dates", [])))}</small></td></tr>'
        for r in review["flags"]
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;"><title>Garmin RepTrace data-quality review</title><style>'
        + CSS
        + '</style></head><body><main class="sheet"><header><div class="eyebrow">GARMIN REPTRACE / Data quality</div><h1>Review candidates</h1><p>'
        + str(review["issueGroups"])
        + " issue groups across "
        + str(review["recordedSets"])
        + ' recorded sets.</p></header><p class="notice">'
        + esc(review["note"])
        + '</p><section class="panel scroll"><table><thead><tr><th>Exercise / workout</th><th>Review</th><th>Sets</th><th>Why</th></tr></thead><tbody>'
        + rows
        + "</tbody></table></section><footer>Identical repeated sets inside a workout are not treated as duplicates. Outliers can be legitimate equipment or training changes.</footer></main></body></html>"
    ).encode()
