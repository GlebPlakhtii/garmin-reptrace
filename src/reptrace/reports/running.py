"""Self-contained running reports shared by Telegram and coach attachments."""

from html import escape
import math
from reptrace.training.running import METRICS, numeric, running_totals, compare_runs


def clock(seconds):
    if numeric(seconds) is None:
        return "—"
    value = int(float(seconds) + 0.5)
    hours, rest = divmod(value, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"


def formatted(value, spec):
    if numeric(value, True) is None:
        return "—"
    if spec["unit"] in ("time", "pace"):
        return clock(value) + (" /km" if spec["unit"] == "pace" else "")
    digits = spec.get("digits", 0)
    return f"{value:,.{digits}f}" + (" " + spec["unit"] if spec["unit"] else "")


def metric(row, key):
    return formatted(row.get(key), next(m for m in METRICS if m["key"] == key))


def running_text(detail):
    run = detail["summary"]
    lines = [
        f"{run['name']} · {run['date']}",
        f"{metric(run, 'distanceKm')} · pace {metric(run, 'averagePace')}",
        f"Timer {metric(run, 'timerSeconds')} · moving {metric(run, 'movingSeconds')}",
    ]
    groups = [
        ("Heart rate", ["averageHR", "maxHR"]),
        ("Cadence / stride", ["cadence", "strideLengthM"]),
        ("Power", ["averagePower", "normalizedPower"]),
        ("Aerobic / anaerobic effect", ["aerobicEffect", "anaerobicEffect"]),
        ("Load", ["trainingLoad"]),
        ("Ascent", ["elevationGain"]),
    ]
    for title, keys in groups:
        if any(run.get(key) is not None for key in keys):
            lines.append(title + ": " + " · ".join(metric(run, key) for key in keys))
    if run.get("primaryBenefit"):
        lines.append("Garmin benefit: " + run["primaryBenefit"])
    if detail.get("warning"):
        lines.append(detail["warning"])
    lines.append(
        f"{len(detail.get('laps', []))} laps · {len(detail.get('samples', []))} returned chart samples. Full report follows."
    )
    return "\n".join(lines)


def history_text(runs, limit=10):
    totals = running_totals(runs)
    lines = [
        f"Running · {totals['count']} recorded runs",
        f"{metric(totals, 'distanceKm')} · moving {metric(totals, 'movingSeconds')}",
        f"Distance-weighted moving pace: {metric(totals, 'movingPace')}",
        "",
    ]
    for run in runs[:limit]:
        lines.append(
            f"{run['date']} · {run['name']}\n{metric(run, 'distanceKm')} · {metric(run, 'averagePace')} · {metric(run, 'averageHR')}"
        )
    if len(runs) > limit:
        lines.append(
            f"Showing newest {limit}; totals cover all {len(runs)} matching runs."
        )
    lines.append(
        "Use /run latest or choose a run below for charts, zones, dynamics and laps."
    )
    return "\n".join(lines)


def chart(samples, key, label, unit):
    rows = [
        r
        for r in samples
        if numeric(r.get(key), True) is not None
        and numeric(r.get("seconds")) is not None
    ]
    if not rows:
        return ""
    lo, hi = min(r[key] for r in rows), max(r[key] for r in rows)
    start, end = min(r["seconds"] for r in rows), max(r["seconds"] for r in rows)
    paths, path, previous = [], [], None
    for row in samples:
        if numeric(row.get(key), True) is None or numeric(row.get("seconds")) is None:
            if path:
                paths.append(" ".join(path))
            path, previous = [], None
            continue
        if previous is not None and row["seconds"] - previous > 60:
            if path:
                paths.append(" ".join(path))
            path = []
        x = 55 + (row["seconds"] - start) / (end - start or 1) * 620
        y = 165 - (row[key] - lo) / (hi - lo or 1) * 125
        path.append(f"{'L' if path else 'M'}{x:.1f},{y:.1f}")
        previous = row["seconds"]
    if path:
        paths.append(" ".join(path))
    label_value = lambda value: clock(value) if key == "pace" else f"{value:.1f}"
    return (
        f'<section><h2>{escape(label)} <small>{escape(unit)}</small></h2><svg viewBox="0 0 720 205" role="img" aria-label="{escape(label)} over timer time"><text x="4" y="40">{label_value(hi)}</text><text x="4" y="165">{label_value(lo)}</text>'
        + "".join(f'<path d="{p}"/>' for p in paths)
        + f'<text x="55" y="195">{clock(start)}</text><text x="615" y="195">{clock(end)}</text></svg></section>'
    )


def render_running_report(detail):
    run = detail["summary"]
    title = escape(f"{run['name']} · {run['date']}")
    groups = list(dict.fromkeys(m["group"] for m in METRICS))
    body = f"<h1>{title}</h1><p>Garmin running report · {escape(run.get('type', 'running').replace('_', ' '))}</p>"
    if detail.get("warning"):
        body += f'<p class="note">{escape(detail["warning"])}</p>'
    for note in detail.get("notes", []):
        body += f'<p class="note">{escape(note)}</p>'
    body += '<div class="grid">'
    for group in groups:
        body += f"<section><h2>{group}</h2><dl>"
        for spec in METRICS:
            if spec["group"] == group:
                body += f"<div><dt>{escape(spec['label'])}</dt><dd>{escape(formatted(run.get(spec['key']), spec))}</dd></div>"
        body += "</dl></section>"
    body += "</div><h2>Heart-rate zones</h2><table><tr><th>Zone</th><th>Lower boundary</th><th>Time</th><th>Share of assigned time</th></tr>"
    total = sum(z["seconds"] for z in detail.get("zones", []))
    for z in detail.get("zones", []):
        body += f"<tr><td>{z['zone']}</td><td>{z['lowBpm'] if z.get('lowBpm') is not None else '—'} bpm</td><td>{clock(z['seconds'])}</td><td>{z['seconds'] / total * 100 if total else 0:.1f}%</td></tr>"
    body += '</table><div class="grid">'
    for key, label, unit in [
        ("pace", "Sample pace", "/km"),
        ("heartRate", "Heart rate", "bpm"),
        ("cadence", "Cadence", "spm"),
        ("power", "Power", "W"),
        ("elevation", "Elevation", "m"),
        ("groundContactMs", "Ground contact time", "ms"),
        ("strideLengthM", "Stride length", "m"),
        ("verticalOscillationCm", "Vertical oscillation", "cm"),
        ("verticalRatio", "Vertical ratio", "%"),
        ("stamina", "Available stamina", "%"),
    ]:
        body += chart(detail.get("samples", []), key, label, unit)
    body += '</div><h2>Laps & intervals</h2><div class="scroll"><table><tr><th>Lap</th>'
    keys = [
        "distanceKm",
        "timerSeconds",
        "averagePace",
        "averageHR",
        "cadence",
        "averagePower",
        "strideLengthM",
        "groundContactMs",
    ]
    specs = [next(m for m in METRICS if m["key"] == key) for key in keys]
    body += "".join(f"<th>{escape(m['label'])}</th>" for m in specs) + "</tr>"
    for lap in detail.get("laps", []):
        body += (
            f"<tr><td>{lap['index']} · {escape(lap.get('intensity', ''))}</td>"
            + "".join(
                f"<td>{escape(formatted(lap.get(m['key']), m))}</td>" for m in specs
            )
            + "</tr>"
        )
    body += '</table></div><p class="note">Garmin estimates are shown as recorded. Missing values are —. Charts use returned Garmin samples and may be reduced in resolution. Timer, moving and elapsed time are different measurements. Pace comparisons do not control for terrain, distance or conditions.</p>'
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'
        + title
        + "</title><style>body{font:15px system-ui;background:#12201d;color:#e3eeea;max-width:1200px;margin:auto;padding:28px}h1{font-size:30px}h2{font-size:18px}p,.note,dt{color:#a9bdb4}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}section{background:#1b2c26;border:1px solid #34463d;border-radius:12px;padding:20px;min-width:0}dl{margin:0}dl div{display:flex;justify-content:space-between;gap:15px;padding:9px 0;border-bottom:1px solid #34463d}dd{margin:0;text-align:right;font-weight:600}small{font-size:12px;color:#a9bdb4}svg{width:100%}svg path{fill:none;stroke:#77d7bc;stroke-width:2}svg text{fill:#a9bdb4;font:11px system-ui}table{border-collapse:collapse;width:100%;font-size:12px}td,th{padding:12px;text-align:left;border-bottom:1px solid #34463d;white-space:nowrap}.scroll{overflow:auto}.note{font-size:12px;line-height:1.7}@media(max-width:700px){body{padding:16px}.grid{grid-template-columns:1fr}}</style><body>"
        + body
        + "</body></html>"
    )
