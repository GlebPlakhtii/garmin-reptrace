"""A single, compact workout sheet rendered directly to PNG."""

from datetime import date
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

COLORS = {
    "bg": "#141720",
    "surface": "#1d2230",
    "alternate": "#191e29",
    "line": "#323a4d",
    "text": "#edf1fa",
    "muted": "#a8b4ca",
    "blue": "#8bbdff",
    "mint": "#7be0c5",
    "gold": "#f0cf8c",
    "pink": "#d9a8ef",
}


def font(size, bold=False):
    base = Path("/usr/share/fonts/truetype/dejavu")
    path = base / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    return (
        ImageFont.truetype(str(path), size)
        if path.exists()
        else ImageFont.load_default(size=size)
    )


def fmt(value):
    return "—" if value is None else f"{value:g}"


def load_label(exercise, value):
    return (
        "BW"
        if exercise.casefold() in ("pull up", "push up", "dip") and value == 0
        else fmt(value) + " kg"
    )


def short_date(value):
    return (
        date.fromisoformat(value).strftime("%d %b %Y").lstrip("0")
        if value
        else "No history yet"
    )


def wrap(text, draw, face, width):
    lines = []
    line = ""
    for word in text.split():
        if line and draw.textlength(line + " " + word, font=face) > width:
            lines.append(line)
            line = word
        else:
            line = (line + " " + word).strip()
    if line:
        lines.append(line)
    return lines


def render_plan(plan, page=0):
    if page != 0:
        raise ValueError("The complete workout is on one image")
    width = 1200
    measure = ImageDraw.Draw(Image.new("RGB", (width, 1)))
    title = font(64, True)
    namefont = font(29, True)
    body = font(27)
    small = font(22)
    tiny = font(20)
    valuefont = font(32, True)
    rows = []
    for exercise in plan["exercises"]:
        names = wrap(exercise["name"], measure, namefont, 352)
        row_height = max(
            112,
            len(names) * 37 + 62,
            max(len(exercise["previous"]), len(exercise["proposed"])) * 38 + 34,
        )
        rows.append((exercise, names, row_height))
    notes = [
        "Highlighted loads or reps are proposed changes. ADD WEIGHT resets reps to the lower target."
    ]
    if any(
        e["name"].casefold() in ("pull up", "push up", "dip")
        and any(s["weight"] == 0 for s in e["previous"])
        for e in plan["exercises"]
    ):
        notes.append("BW = bodyweight only, with no added load.")
    if any(
        e["name"].casefold() in ("pull up", "push up", "dip")
        and any(s["weight"] and s["weight"] > 0 for s in e["previous"])
        for e in plan["exercises"]
    ):
        notes.append(
            "Review flagged bodyweight loads: added weight and assistance are not interchangeable."
        )
    if plan.get("adaptation"):
        adaptation = plan["adaptation"]
        if adaptation.get("timeBudget"):
            notes.insert(
                0,
                f"Adapted to {adaptation['timeBudget']} min · estimated {adaptation['estimatedMinutes']} min; rest and equipment waits vary.",
            )
        removed = [c for c in adaptation["changes"] if c.startswith("Removed ")]
        if removed:
            notes.append(" · ".join(removed))
    if plan["stale"]:
        notes.append(
            "Older baseline: review historical loads before returning to this workout."
        )
    if not rows:
        notes.append(plan["notice"])
    note_lines = [line for text in notes for line in wrap(text, measure, small, 1080)]
    top = 366
    bottom = sum(row_height for _, _, row_height in rows) + top
    height = bottom + 90 + len(note_lines) * 32 + 62
    image = Image.new("RGB", (width, height), COLORS["bg"])
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 400, 5), fill=COLORS["blue"])
    draw.rectangle((400, 0, 800, 5), fill=COLORS["mint"])
    draw.rectangle((800, 0, 1200, 5), fill=COLORS["pink"])
    draw.text((50, 30), "GARMIN REPTRACE  /  TRAINING PLAN", font=small, fill=COLORS["blue"])
    draw.text((46, 76), plan["name"], font=title, fill=COLORS["text"])
    draw.rounded_rectangle((900, 80, 1150, 125), radius=10, fill=COLORS["surface"])
    draw.text((923, 90), "NEXT SESSION", font=tiny, fill=COLORS["mint"])
    draw.text(
        (50, 164),
        "Last completed  " + short_date(plan["baselineDate"]),
        font=small,
        fill=COLORS["muted"],
    )
    count = sum(len(e["proposed"]) for e in plan["exercises"])
    added = sum(
        max(0, (b["reps"] or 0) - (a["reps"] or 0))
        for e in plan["exercises"]
        for a, b in zip(e["previous"], e["proposed"])
    )
    heavier = sum(
        1
        for e in plan["exercises"]
        for a, b in zip(e["previous"], e["proposed"])
        if a["weight"] is not None
        and b["weight"] is not None
        and b["weight"] > a["weight"]
    )
    stats = [
        ("EXERCISES", str(len(rows)), "blue"),
        ("PLANNED SETS", str(count), "pink"),
        (
            "HEAVIER SETS" if heavier else "EXTRA REP TARGET",
            str(heavier) if heavier else f"+{added:g}",
            "mint",
        ),
    ]
    for i, (label, value, color) in enumerate(stats):
        x = 50 + i * 370
        draw.rounded_rectangle(
            (x, 218, x + 350, 300), radius=12, fill=COLORS["surface"]
        )
        draw.text((x + 18, 233), label, font=tiny, fill=COLORS["muted"])
        draw.text((x + 268, 238), value, font=valuefont, fill=COLORS[color])
    draw.text((50, 327), "EXERCISE", font=tiny, fill=COLORS["muted"])
    draw.text((470, 327), "LAST RESULT", font=tiny, fill=COLORS["muted"])
    draw.text((820, 327), "NEXT TARGET", font=tiny, fill=COLORS["mint"])
    y = top
    status = {
        "weight_progress": ("ADD WEIGHT", "pink"),
        "progress": ("ADD 1 REP", "mint"),
        "repeat": ("REPEAT", "blue"),
        "review": ("REVIEW FIRST", "gold"),
    }
    for i, (exercise, names, row_height) in enumerate(rows):
        draw.rectangle(
            (40, y, 1160, y + row_height),
            fill=COLORS["surface"] if i % 2 == 0 else COLORS["alternate"],
        )
        draw.line((40, y, 1160, y), fill=COLORS["line"])
        cy = y + 18
        for line in names:
            draw.text((58, cy), line, font=namefont, fill=COLORS["text"])
            cy += 37
        label, color = status[exercise["status"]]
        draw.text((60, cy + 9), label, font=tiny, fill=COLORS[color])
        for j, previous in enumerate(exercise["previous"]):
            draw.text(
                (470, y + 18 + j * 38),
                f"{load_label(exercise['name'], previous['weight'])} × {fmt(previous['reps'])}",
                font=body,
                fill=COLORS["muted"],
            )
        for j, proposed in enumerate(exercise["proposed"]):
            cy = y + 18 + j * 38
            load = load_label(exercise["name"], proposed["weight"])
            load_changed = (
                j < len(exercise["previous"])
                and proposed["weight"] != exercise["previous"][j]["weight"]
            )
            draw.text(
                (820, cy),
                load,
                font=body,
                fill=COLORS["gold"] if load_changed else COLORS["blue"],
            )
            x = 820 + draw.textlength(load, font=body)
            draw.text((x, cy), " × ", font=body, fill=COLORS["muted"])
            x += draw.textlength(" × ", font=body)
            changed = (
                j < len(exercise["previous"])
                and proposed["reps"] != exercise["previous"][j]["reps"]
            )
            reps = fmt(proposed["reps"])
            face = font(27, True) if changed else body
            if changed:
                draw.rounded_rectangle(
                    (x - 5, cy - 2, x + draw.textlength(reps, font=face) + 7, cy + 33),
                    radius=6,
                    fill="#354333",
                )
            draw.text(
                (x, cy),
                reps,
                font=face,
                fill=COLORS["gold"] if changed else COLORS["text"],
            )
        y += row_height
    draw.line((40, y, 1160, y), fill=COLORS["line"])
    y += 26
    for line in note_lines:
        draw.text((50, y), line, font=small, fill=COLORS["muted"])
        y += 32
    y += 22
    draw.text(
        (50, y),
        "PROPOSED TARGETS · Record actual results after training",
        font=tiny,
        fill=COLORS["pink"],
    )
    draw.text(
        (50, y + 32),
        "Prepared "
        + short_date(plan["generatedDate"])
        + "  ·  Reasoning & history in Garmin RepTrace → Next session",
        font=tiny,
        fill=COLORS["muted"],
    )
    # Telegram photos allow a sum of width and height up to 10,000 pixels.
    if image.width + image.height > 9900:
        ratio = 9900 / (image.width + image.height)
        image = image.resize(
            (int(image.width * ratio), int(image.height * ratio)),
            Image.Resampling.LANCZOS,
        )
    result = BytesIO()
    image.save(result, format="PNG", optimize=True)
    return result.getvalue()
