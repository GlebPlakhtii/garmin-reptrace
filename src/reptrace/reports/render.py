"""Portable HTML reports with inline SVG, plus a Telegram chart preview."""

from datetime import datetime, timezone, date, timedelta
from html import escape
from io import BytesIO
import re
from PIL import Image, ImageDraw

from reptrace.training.metrics import known, total
from reptrace.reports.facts import fmt, signed
from reptrace.exports.plans import font, wrap, load_label

PALETTE = {
    "bg": "#131721",
    "panel": "#1d2433",
    "text": "#eaf0fa",
    "muted": "#adbad0",
    "blue": "#89bbff",
    "purple": "#c7a5ee",
    "mint": "#7cdec4",
    "gold": "#ebcb8d",
    "line": "#344258",
}


def esc(value):
    return escape(str(value if value is not None else ""), quote=True)


def set_label(name, s):
    return load_label(name, s.get("weight")) + " × " + fmt(s.get("reps"), 0)


def volume_comparisons(facts):
    result = []
    for e in facts["exercises"]:
        comparison = e.get("comparisonToPrevious") or {}
        before = (comparison.get("before") or {}).get("volume")
        after = total(s.get("volume") for s in e["sets"])
        result.append({"name": e["exercise"], "before": before, "after": after})
    return result


def volume_svg(facts):
    rows = volume_comparisons(facts)
    height = 70 + len(rows) * 64
    maximum = max(
        [r[k] for r in rows for k in ("before", "after") if known(r[k])] + [1]
    )
    parts = [
        f'<svg class="volume-chart" viewBox="0 0 1000 {height}" role="img" aria-label="Recorded exercise volume, previous and current session"><title>Recorded volume in kg × reps; missing measurements are excluded.</title>'
    ]
    for i, row in enumerate(rows):
        y = 30 + i * 64
        label = row["name"] if len(row["name"]) <= 30 else row["name"][:28] + "…"
        parts.append(
            f'<text x="0" y="{y + 14}" fill="#eaf0fa" font-size="16">{esc(label)}<title>{esc(row["name"])}</title></text>'
        )
        for j, (field, color) in enumerate(
            [("before", PALETTE["purple"]), ("after", PALETTE["mint"])]
        ):
            value = row[field]
            bar = 570 * value / maximum if known(value) else 0
            yy = y + j * 20
            parts.append(
                f'<rect x="320" y="{yy}" width="{bar:.2f}" height="12" rx="4" fill="{color}"><title>{esc(row["name"])}: {"previous" if j == 0 else "current"} {fmt(value)} kg·reps</title></rect><text x="{330 + bar:.2f}" y="{yy + 12}" fill="#adbad0" font-size="14">{fmt(value, 0)}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def trend_svg(points, color, unit, label):
    # A missing reading breaks the path; it is never joined to the next known day.
    valid = [p[1] for p in points if known(p[1])]
    if not valid:
        return '<p class="empty">No recorded values for this chart.</p>'
    low, high = min(valid), max(valid)
    spread = high - low or max(abs(high) * 0.1, 1)

    def xy(i, v):
        return 30 + (i / (len(points) - 1) if len(points) > 1 else 0.5) * 420, 135 - (
            v - low
        ) / spread * 90

    parts = [
        f'<svg viewBox="0 0 480 190" role="img" aria-label="{esc(label)}"><title>{esc(label)}</title>'
    ]
    for y in (45, 90, 135):
        parts.append(
            f'<line x1="30" x2="450" y1="{y}" y2="{y}" stroke="#344258" stroke-dasharray="4 5"/>'
        )
    run = []

    def segment():
        if run:
            parts.append(
                f'<polyline points="{" ".join(run)}" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round"/>'
            )

    for i, (day, value) in enumerate(points):
        if not known(value):
            segment()
            run = []
            continue
        x, y = xy(i, value)
        run.append(f"{x:.2f},{y:.2f}")
    segment()
    for i, (day, value) in enumerate(points):
        if not known(value):
            continue
        x, y = xy(i, value)
        parts.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="{color}"><title>{esc(day)}: {fmt(value)} {esc(unit)}</title></circle><text x="{x:.2f}" y="{y - 12:.2f}" text-anchor="middle" font-size="20" fill="#eaf0fa">{fmt(value)}</text>'
        )
    if points:
        parts.append(
            f'<text x="30" y="175" font-size="16" fill="#adbad0">{esc(points[0][0])}</text><text x="450" y="175" text-anchor="end" font-size="16" fill="#adbad0">{esc(points[-1][0])}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def analysis_html(text, model, status):
    if not text:
        return f'<div class="notice">AI analysis {esc(status or "unavailable")}. Charts and figures below are calculated directly from recorded data.</div>'
    sections = []
    heading = "Session analysis"
    body = []
    for line in text.splitlines():
        cleaned = re.sub(r"^[#*\s]+|[*:\s]+$", "", line)
        if cleaned.casefold() in (
            "progress",
            "recovery & workload",
            "watch-outs",
            "next time",
            "next month",
        ):
            if body:
                sections.append((heading, "\n".join(body)))
            heading = cleaned
            body = []
        elif line.strip():
            body.append(line.strip())
    if body:
        sections.append((heading, "\n".join(body)))
    return (
        '<div class="analysis-grid">'
        + "".join(
            f'<article class="analysis-card"><h3>{esc(title)}</h3>'
            + "".join(f"<p>{esc(line)}</p>" for line in content.splitlines())
            + "</article>"
            for title, content in sections
        )
        + '</div><p class="footnote">Analysis by '
        + esc(model)
        + ". Recorded numbers and chart geometry are calculated independently.</p>"
    )


CSS = """
:root{color-scheme:dark;--bg:#131721;--panel:#1d2433;--ink:#eaf0fa;--muted:#adbad0;--line:#344258;--blue:#89bbff;--mint:#7cdec4;--purple:#c7a5ee;--gold:#ebcb8d}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.65 system-ui,-apple-system,"Segoe UI",sans-serif}.sheet{max-width:1160px;margin:auto;padding:42px 30px 65px}header{border-top:4px solid var(--blue);padding-top:25px}.eyebrow{color:var(--blue);font-size:12px;letter-spacing:2px;text-transform:uppercase}h1{font-size:44px;letter-spacing:-1.2px;line-height:1.2;margin:14px 0}h2{font-size:25px;font-weight:600;margin:0 0 14px}h3{font-size:19px;font-weight:600;margin:0 0 12px}p{margin:8px 0}nav{display:flex;gap:20px;flex-wrap:wrap;margin:25px 0}a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}.meta,.muted,.footnote,.caption{color:var(--muted)}.caption,.footnote{font-size:13px}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin:26px 0}.metric,.panel,.analysis-card,.exercise{border:1px solid var(--line);background:var(--panel);border-radius:14px}.metric{padding:20px}.metric small{display:block;font-size:12px;letter-spacing:.7px;text-transform:uppercase;color:var(--muted)}.metric strong{font-size:32px;font-weight:600;display:block;margin:8px 0;color:var(--blue)}.metric:nth-child(2) strong{color:var(--mint)}.metric:nth-child(3) strong{color:var(--purple)}.metric:nth-child(4) strong{color:var(--gold)}.metric span{font-size:12px;color:var(--muted)}section{margin-top:32px}.panel{padding:25px}.legend{display:flex;gap:20px;flex-wrap:wrap;margin:15px 0;font-size:13px;color:var(--muted)}.legend i{display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:7px}.legend .previous{background:var(--purple)}.legend .current{background:var(--mint)}svg{display:block;width:100%;height:auto;font-family:system-ui,sans-serif}.analysis-grid,.exercise-grid,.recovery-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.analysis-card,.exercise{padding:23px}.analysis-card h3{color:var(--blue)}.analysis-card:nth-child(2) h3{color:var(--purple)}.analysis-card:nth-child(3) h3{color:var(--gold)}.analysis-card:nth-child(4) h3{color:var(--mint)}.exercise .delta{color:var(--mint);font-size:13px}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:10px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}th{font-size:12px;color:var(--muted);font-weight:500}.load{color:var(--blue)}.reps{color:var(--gold)}.notice,.empty{border-left:3px solid var(--gold);padding:13px 18px;background:var(--panel);color:var(--muted);font-size:14px;margin:18px 0}.recovery-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.recovery-grid .panel{padding:20px}.recovery-value{font-size:28px;font-weight:500;color:var(--purple)}.target{margin:15px 0;padding-bottom:14px;border-bottom:1px solid var(--line)}.target strong{display:block;color:var(--blue)}.target span{display:block;color:var(--mint)}footer{margin-top:38px;border-top:1px solid var(--line);padding-top:20px;font-size:13px;color:var(--muted)}@media(max-width:760px){.sheet{padding:25px 17px}h1{font-size:33px}.metrics{grid-template-columns:repeat(2,1fr)}.exercise-grid,.analysis-grid,.recovery-grid{grid-template-columns:1fr}.panel,.exercise,.analysis-card{padding:19px}.volume-chart{min-width:750px}.metric{padding:17px}.metric strong{font-size:27px}}@media print{:root{color-scheme:light}body{background:white;color:#18202c}.panel,.exercise,.metric,.analysis-card{background:white;color:#18202c;border-color:#bbb}h1,h2,h3{color:#18202c}.sheet{max-width:none}nav{display:none}.exercise,.analysis-card{break-inside:avoid}svg{print-color-adjust:exact}}
"""


def plan_review_html(facts):
    review = facts.get("planReview") or {
        "status": "unavailable",
        "reason": "No Garmin plan comparison was captured for this session.",
    }
    if review.get("status") != "available":
        return (
            '<section id="plan-review"><h2>Plan vs completed</h2><p class="notice">'
            + esc(
                review.get("reason") or "No comparable Garmin template was available."
            )
            + "</p></section>"
        )
    counts = review["counts"]
    source = (
        "Saved app template"
        if review.get("source") == "app_snapshot"
        else "Current Garmin template · approximate"
    )
    cells = []
    for row in review["rows"]:
        planned = (
            "—"
            if row["status"] == "extra"
            else esc(
                set_label(
                    row["exercise"],
                    {"weight": row["plannedWeight"], "reps": row["plannedReps"]},
                )
            )
        )
        actual = (
            "—"
            if row["status"] == "missing"
            else esc(
                set_label(
                    row["exercise"],
                    {"weight": row["actualWeight"], "reps": row["actualReps"]},
                )
            )
        )
        cells.append(
            f'<tr><td>{esc(row["exercise"])}</td><td>{row["set"]}</td><td>{planned}</td><td>{actual}</td><td><span class="plan-status {esc(row["status"])}">{esc(row["status"].title())}</span></td></tr>'
        )
    summary = f"{counts['matched']} matched · {counts['changed']} changed · {counts['missing']} missing · {counts['extra']} extra · {counts['unknown']} unknown"
    return (
        '<section id="plan-review"><h2>Plan vs completed</h2><div class="panel"><p><strong>'
        + esc(source)
        + "</strong> · "
        + esc(summary)
        + '</p><p class="caption">'
        + esc(review["note"])
        + '</p><div class="scroll"><table><thead><tr><th>Exercise</th><th>Set</th><th>Planned</th><th>Completed</th><th>Result</th></tr></thead><tbody>'
        + "".join(cells)
        + "</tbody></table></div></div></section>"
    )


def render_report_html(facts, analysis="", model="gpt-6-sol", status="unavailable"):
    w, t = facts["workout"], facts["totals"]
    stamp = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    metrics = [
        ("Recorded sets", fmt(t["sets"], 0), f"{len(facts['exercises'])} exercises"),
        ("Recorded reps", fmt(t["reps"], 0), "Missing reps excluded"),
        (
            "Recorded volume",
            fmt(t["volume"], 0) + " kg·reps",
            f"{t['volumeKnown']}/{t['sets']} sets have load and reps",
        ),
        (
            "Duration",
            fmt(w["duration"] / 60 if known(w.get("duration")) else None) + " min",
            f"HR {fmt(w.get('averageHR'), 0)} avg / {fmt(w.get('maxHR'), 0)} max bpm",
        ),
    ]
    header = (
        f'<header><div class="eyebrow">GARMIN REPTRACE / After-session report</div><h1>{esc(w["name"])}</h1><p class="meta">{esc(w["date"])} · {esc(facts["comparisonScope"])}</p><nav><a href="#analysis">Analysis</a><a href="#plan-review">Plan vs completed</a><a href="#performance">Performance</a><a href="#recovery">Recovery</a><a href="#next">Next time</a></nav></header><div class="metrics">'
        + "".join(
            f'<div class="metric"><small>{esc(label)}</small><strong>{esc(value)}</strong><span>{esc(note)}</span></div>'
            for label, value, note in metrics
        )
        + "</div>"
    )
    performance = (
        '<section id="performance"><h2>Performance, exercise by exercise</h2><div class="panel"><h3>Recorded volume vs previous same-type session</h3><div class="legend"><span><i class="previous"></i>Previous occurrence</span><span><i class="current"></i>This session</span></div><div class="scroll">'
        + volume_svg(facts)
        + '</div><p class="caption">kg·reps = external load × reps. Bodyweight is not added. Missing values are excluded; a larger total is not automatically better.</p></div><div class="exercise-grid" style="margin-top:18px">'
    )
    for e in facts["exercises"]:
        points = [
            (h["date"], total(s.get("reps") for s in h["sets"]))
            for h in reversed(e["priorSameType"])
        ] + [(w["date"], total(s.get("reps") for s in e["sets"]))]
        comparison = e.get("comparisonToPrevious")
        change = (
            f"Reps {signed(comparison['repChange'])} · recorded volume {signed(comparison['volumeChange'])} kg·reps vs {comparison['date']}"
            if comparison
            else "No previous comparable session recorded."
        )
        performance += (
            f'<article class="exercise"><h3>{esc(e["exercise"])}</h3><p class="delta">{esc(change)}</p><p class="caption">Total recorded reps across recent same-type sessions; set counts and loads may differ.</p>'
            + trend_svg(
                points, PALETTE["blue"], "reps", e["exercise"] + " total recorded reps"
            )
            + '<div class="scroll"><table><thead><tr><th>Set</th><th>Load</th><th>Reps</th><th>kg·reps</th><th>Est. 1RM</th><th>Rest</th></tr></thead><tbody>'
        )
        for i, s in enumerate(e["sets"]):
            performance += f'<tr><td>{i + 1}</td><td class="load">{esc(load_label(e["exercise"], s.get("weight")))}</td><td class="reps">{fmt(s.get("reps"), 0)}</td><td>{fmt(s.get("volume"), 0)}</td><td>{fmt(s.get("estimatedMax"))} kg</td><td>{fmt(s.get("rest"))} sec</td></tr>'
        performance += (
            '</tbody></table></div><p class="caption">'
            + esc(e["loadMeaning"])
            + f". Missing load: {e['missingLoad']}; missing reps: {e['missingReps']}.</p></article>"
        )
    performance += "</div></section>"
    recovery = '<section id="recovery"><h2>Recovery context</h2><p class="caption">Readings are observations, not a readiness score or evidence of cause and effect.</p><div class="recovery-grid">'
    for key, label, unit, color in [
        ("sleepHours", "Sleep", "h", PALETTE["purple"]),
        ("hrv", "Overnight HRV", "ms", PALETTE["mint"]),
        ("restingHR", "Resting heart rate", "bpm", PALETTE["gold"]),
        ("bodyWeightKg", "Body weight", "kg", PALETTE["blue"]),
    ]:
        actual = (facts.get("sameDayRecovery") or {}).get(key)
        average = facts["last7DayRecovery"].get(key, {"value": None, "days": 0})
        daily = {r["date"]: r for r in facts.get("recoveryHistory", [])}
        days = [
            (date.fromisoformat(w["date"]) - timedelta(days=6 - i)).isoformat()
            for i in range(7)
        ]
        points = [(day, daily.get(day, {}).get(key)) for day in days]
        recovery += (
            f'<article class="panel"><h3>{label}</h3><strong class="recovery-value">{fmt(actual)} {unit}</strong><p class="caption">Workout day · 7-day average {fmt(average["value"])} {unit}<br>{average["days"]}/7 days recorded</p>'
            + trend_svg(points, color, unit, label + " last seven days")
            + "</article>"
        )
    recovery += (
        '</div><p class="caption">Same-day Body Battery: '
        + fmt((facts.get("sameDayRecovery") or {}).get("bodyBattery"), 0)
        + " · Sleep score: "
        + fmt((facts.get("sameDayRecovery") or {}).get("sleepScore"), 0)
        + "</p></section>"
    )
    targets = '<section id="next"><h2>Next-session targets</h2><div class="panel">'
    for e in facts.get("nextTargets", []):
        targets += f'<div class="target"><strong>{esc(e["name"])}</strong><span>{esc(" · ".join(set_label(e["name"], s) for s in e["proposed"]))}</span><p class="caption">{esc(e["reason"])}</p></div>'
    if not facts.get("nextTargets"):
        targets += '<p class="muted">No current next-session proposal is attached to this workout.</p>'
    targets += "</div></section>"
    workload = f'<p class="caption">Previous 28 days ending on this session: {facts["last28Days"]["workouts"]} sessions · {facts["last28Days"]["sets"]} sets. Effort/RIR: {esc(facts["effortRIR"])}.</p>'
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;; base-uri &#39;none&#39;; form-action &#39;none&#39;"><title>'
        + esc(w["name"] + " · Garmin RepTrace report · " + w["date"])
        + "</title><style>"
        + CSS
        + " .plan-status{display:inline-block;border:1px solid var(--line);border-radius:6px;padding:2px 8px;text-transform:capitalize}.plan-status.matched{color:var(--mint)}.plan-status.changed,.plan-status.missing{color:var(--gold)}.plan-status.extra{color:var(--blue)}.plan-status.unknown{color:var(--muted)}"
        + '</style></head><body><main class="sheet">'
        + header
        + '<section id="analysis"><h2>Session analysis</h2>'
        + analysis_html(analysis, model, status)
        + workload
        + "</section>"
        + plan_review_html(facts)
        + performance
        + recovery
        + targets
        + f"<footer>Prepared {esc(stamp)}. Standalone report: charts are embedded, with no external scripts, fonts or tracking. BW means bodyweight only. Estimated 1RM is an estimate, not a measured max. Recorded loads are not converted between equipment. Calorie estimate: {fmt(w.get('calories'), 0)} kcal.</footer></main></body></html>"
    )
    return html.encode("utf-8")


def render_report_preview(
    facts,
    model="gpt-6-sol",
    ai_available=True,
    banner="AFTER SESSION",
    previous_label="Previous occurrence",
    recovery_label="",
    current_label="This session",
):
    w, t = facts["workout"], facts["totals"]
    rows = volume_comparisons(facts)
    height = 540 + len(rows) * 88 + 245
    image = Image.new("RGB", (1200, height), PALETTE["bg"])
    draw = ImageDraw.Draw(image)
    small = font(23)
    tiny = font(20)
    heading = font(52, True)
    body = font(25)
    value = font(36, True)
    draw.rectangle((0, 0, 400, 5), fill=PALETTE["blue"])
    draw.rectangle((400, 0, 800, 5), fill=PALETTE["mint"])
    draw.rectangle((800, 0, 1200, 5), fill=PALETTE["purple"])
    draw.text((48, 34), "GARMIN REPTRACE / " + banner, font=small, fill=PALETTE["blue"])
    # Workout titles can be long; use one fitted line to keep chart geometry stable.
    face = heading
    while draw.textlength(w["name"], font=face) > 1100 and face.size > 22:
        face = font(face.size - 2, True)
    draw.text((45, 85), w["name"], font=face, fill=PALETTE["text"])
    draw.text(
        (48, 160),
        w["date"]
        + " · "
        + ("AI " + model if ai_available else "Calculated report · AI unavailable"),
        font=small,
        fill=PALETTE["muted"],
    )
    metrics = [
        ("SETS", fmt(t["sets"], 0), "blue"),
        ("REPS", fmt(t["reps"], 0), "mint"),
        ("KG·REPS", fmt(t["volume"], 0), "purple"),
    ]
    for i, (label, number, color) in enumerate(metrics):
        x = 48 + i * 372
        draw.rounded_rectangle((x, 220, x + 350, 323), radius=14, fill=PALETTE["panel"])
        draw.text((x + 20, 236), label, font=tiny, fill=PALETTE["muted"])
        draw.text((x + 20, 270), number, font=value, fill=PALETTE[color])
    draw.text((48, 368), "EXERCISE VOLUME", font=small, fill=PALETTE["text"])
    draw.text((48, 410), previous_label, font=tiny, fill=PALETTE["purple"])
    draw.text((345, 410), current_label, font=tiny, fill=PALETTE["mint"])
    draw.text((910, 410), "kg × reps", font=tiny, fill=PALETTE["muted"])
    maximum = max(
        [r[k] for r in rows for k in ("before", "after") if known(r[k])] + [1]
    )
    y = 465
    for row in rows:
        names = wrap(row["name"], draw, body, 365)
        for j, line in enumerate(names[:2]):
            draw.text((48, y + j * 29), line, font=body, fill=PALETTE["text"])
        for j, (key, color) in enumerate([("before", "purple"), ("after", "mint")]):
            v = row[key]
            bar = 545 * v / maximum if known(v) else 0
            yy = y + j * 27
            if bar > 0:
                draw.rounded_rectangle(
                    (450, yy + 3, 450 + bar, yy + 19), radius=5, fill=PALETTE[color]
                )
            draw.text(
                (max(460 + bar, 465), yy - 3),
                fmt(v, 0),
                font=tiny,
                fill=PALETTE["muted"],
            )
        y += 88
    y += 25
    draw.line((48, y, 1150, y), fill=PALETTE["line"])
    y += 25
    same = facts.get("sameDayRecovery") or {}
    draw.text(
        (48, y),
        recovery_label
        + f"Sleep  {fmt(same.get('sleepHours'))} h    ·    HRV  {fmt(same.get('hrv'), 0)} ms    ·    RHR  {fmt(same.get('restingHR'), 0)} bpm",
        font=small,
        fill=PALETTE["purple"],
    )
    draw.text(
        (48, y + 52), "OPEN THE HTML ATTACHMENT", font=small, fill=PALETTE["blue"]
    )
    draw.text(
        (48, y + 88),
        "Month comparisons, exercise changes, recovery and priorities."
        if banner == "MONTHLY REVIEW"
        else "Full analysis, exercise trends, recovery charts and next-session targets.",
        font=tiny,
        fill=PALETTE["muted"],
    )
    review = facts.get("planReview") or {}
    if banner != "MONTHLY REVIEW" and review.get("status") == "available":
        counts = review["counts"]
        line = f"PLAN vs DONE  {counts['matched']} match · {counts['changed']} changed · {counts['missing']} missing · {counts['extra']} extra"
        draw.text((48, y + 126), line, font=tiny, fill=PALETTE["mint"])
    if image.width + image.height > 9900:
        scale = 9900 / (image.width + image.height)
        image = image.resize(
            (int(image.width * scale), int(image.height * scale)),
            Image.Resampling.LANCZOS,
        )
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
