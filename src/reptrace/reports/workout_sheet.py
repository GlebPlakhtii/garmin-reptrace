"""One complete image of a recorded workout, without interactive pagination."""

from collections import OrderedDict
from io import BytesIO

from PIL import Image, ImageDraw

from reptrace.exports.plans import COLORS, font, short_date
from reptrace.reports.facts import fmt
from reptrace.reports.volume import adjusted_sets
from reptrace.training.metrics import known, total


def workout_sheet_facts(data, identity):
    workout = next(w for w in data["workouts"] if w["id"] == identity)
    rows = sorted(
        (s for s in adjusted_sets(data) if s["sessionId"] == identity),
        key=lambda s: s.get("order") or 0,
    )
    groups = OrderedDict()
    for row in rows:
        # A complete sheet also shows unidentified exercises; no records disappear.
        name = row.get("exercise") or "Unidentified exercise"
        groups.setdefault(name, []).append(row)
    return {
        "workout": workout,
        "exercises": [
            {"exercise": name, "sets": sets} for name, sets in groups.items()
        ],
        "totals": {
            "sets": len(rows),
            "reps": total(s.get("reps") for s in rows),
            "repsKnown": sum(known(s.get("reps")) for s in rows),
            "volume": total(s.get("volume") for s in rows),
            "volumeKnown": sum(known(s.get("volume")) for s in rows),
            "activeSeconds": total(s.get("duration") for s in rows),
            "restSeconds": total(s.get("rest") for s in rows),
        },
    }


def seconds(value):
    if not known(value):
        return "—"
    minutes, remainder = divmod(round(value), 60)
    return f"{minutes}:{remainder:02d}"


def text_lines(text, draw, face, width):
    """Wrap even long unbroken exercise names without truncating them."""
    lines, line = [], ""
    for word in str(text).split():
        candidate = (line + " " + word).strip()
        if draw.textlength(candidate, font=face) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
        line = ""
        for character in word:
            if line and draw.textlength(line + character, font=face) > width:
                lines.append(line)
                line = ""
            line += character
    return lines + ([line] if line else [])


def render_workout_sheet(facts):
    width = 1440
    pad = 48
    measure = ImageDraw.Draw(Image.new("RGB", (width, 1)))
    title_font, heading, body, small = (
        font(52, True),
        font(30, True),
        font(27),
        font(21),
    )
    workout, totals = facts["workout"], facts["totals"]
    titles = text_lines(workout["name"], measure, title_font, width - pad * 2)
    meta = (
        f"Duration {seconds(workout.get('duration'))}  ·  {fmt(workout.get('calories'), 0)} kcal  ·  "
        f"Heart rate {fmt(workout.get('averageHR'), 0)} avg / {fmt(workout.get('maxHR'), 0)} max bpm"
    )
    meta_lines = text_lines(meta, measure, body, width - pad * 2)
    top = 170 + 64 * len(titles) + 38 * len(meta_lines) + 190
    columns = [
        (68, 80, "SET"),
        (168, 160, "LOAD kg"),
        (348, 110, "REPS"),
        (478, 200, "ADJ. kg·reps"),
        (698, 170, "EST. 1RM kg"),
        (888, 135, "WORK m:ss"),
        (1043, 135, "REST m:ss"),
        (1198, 170, "SOURCE"),
    ]
    sections = []
    for exercise in facts["exercises"]:
        names = text_lines(exercise["exercise"], measure, heading, width - pad * 2 - 40)
        rows = []
        for index, row in enumerate(exercise["sets"], 1):
            values = [
                str(index),
                fmt(row.get("weight")),
                fmt(row.get("reps"), 0),
                fmt(row.get("volume")),
                fmt(row.get("estimatedMax")),
                seconds(row.get("duration")),
                seconds(row.get("rest")),
                str(row.get("source") or workout.get("source") or "—"),
            ]
            cells = [
                text_lines(value, measure, body, size)
                for value, (_, size, _) in zip(values, columns)
            ]
            rows.append((cells, max(len(cell) for cell in cells) * 36 + 16))
        height = len(names) * 40 + 78 + sum(height for _, height in rows) + 16
        sections.append((names, rows, height))
    notes = [
        "— = not recorded or unavailable. Zero is a recorded value. All recorded sets are shown.",
        "Loads keep their recorded equipment/per-hand conventions. Assistance is not added weight.",
        "Adjusted volume and estimated 1RM are estimates, not measured effort. Missing inputs are excluded.",
    ]
    note_lines = [
        line
        for note in notes
        for line in text_lines(note, measure, small, width - pad * 2)
    ]
    height = (
        top + sum(section[2] + 20 for section in sections) + len(note_lines) * 30 + 90
    )
    if not sections:
        height += 80
    if width * height > 40_000_000:
        raise ValueError(
            "This workout is too large for a single readable image. Use /export latest for all sets."
        )
    image = Image.new("RGB", (width, height), COLORS["bg"])
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 6), fill=COLORS["mint"])
    draw.text(
        (pad, 30),
        "GARMIN REPTRACE  /  COMPLETED WORKOUT",
        font=small,
        fill=COLORS["mint"],
    )
    y = 76
    for line in titles:
        draw.text((pad - 2, y), line, font=title_font, fill=COLORS["text"])
        y += 64
    draw.text(
        (pad, y + 6), short_date(workout["date"]), font=body, fill=COLORS["muted"]
    )
    y += 62
    stats = [
        ("EXERCISES", str(len(sections)), "All recorded exercises"),
        ("SETS", str(totals["sets"]), "Completed records"),
        (
            "REPS",
            fmt(totals["reps"], 0),
            f"{totals['repsKnown']}/{totals['sets']} sets known",
        ),
        (
            "ADJUSTED VOLUME",
            fmt(totals["volume"], 0),
            f"kg·reps · {totals['volumeKnown']}/{totals['sets']} sets known",
        ),
    ]
    for index, (label, value, detail) in enumerate(stats):
        x = pad + index * 342
        draw.rounded_rectangle(
            (x, y, x + 320, y + 124), radius=14, fill=COLORS["surface"]
        )
        draw.text((x + 18, y + 14), label, font=small, fill=COLORS["muted"])
        face = font(38, True)
        if draw.textlength(value, font=face) > 284:
            face = body
        draw.text(
            (x + 18, y + 43),
            value,
            font=face,
            fill=COLORS["mint"] if index == 3 else COLORS["text"],
        )
        draw.text((x + 18, y + 93), detail, font=font(18), fill=COLORS["muted"])
    y += 150
    for line in meta_lines:
        draw.text((pad, y), line, font=body, fill=COLORS["muted"])
        y += 38
    draw.text(
        (pad, y + 4),
        f"Recorded work {seconds(totals['activeSeconds'])}  ·  Recorded rest {seconds(totals['restSeconds'])}",
        font=small,
        fill=COLORS["muted"],
    )
    y = top
    for names, rows, section_height in sections:
        draw.rounded_rectangle(
            (pad, y, width - pad, y + section_height), radius=12, fill=COLORS["surface"]
        )
        cy = y + 16
        for name in names:
            draw.text((pad + 20, cy), name, font=heading, fill=COLORS["blue"])
            cy += 40
        cy += 6
        for x, _, label in columns:
            draw.text((x, cy), label, font=font(18), fill=COLORS["muted"])
        cy += 40
        for index, (cells, row_height) in enumerate(rows):
            if index % 2 == 0:
                draw.rectangle(
                    (pad + 8, cy - 4, width - pad - 8, cy + row_height - 4),
                    fill=COLORS["alternate"],
                )
            for column, ((x, _, _), cell) in enumerate(zip(columns, cells)):
                for line_index, line in enumerate(cell):
                    draw.text(
                        (x, cy + line_index * 36),
                        line,
                        font=body,
                        fill=COLORS["mint"] if column == 3 else COLORS["text"],
                    )
            cy += row_height
        y += section_height + 20
    if not sections:
        draw.text(
            (pad, y + 10),
            "No recorded sets for this workout.",
            font=body,
            fill=COLORS["muted"],
        )
        y += 80
    y += 16
    for line in note_lines:
        draw.text((pad, y), line, font=small, fill=COLORS["muted"])
        y += 30
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def photo_suitable(image):
    with Image.open(BytesIO(image)) as picture:
        width, height = picture.size
    # Keep long sheets at their original resolution instead of relying on a
    # compressed photo preview for small table text.
    return (
        len(image) <= 10_000_000
        and width + height <= 10000
        and max(width, height) <= 2400
        and max(width, height) / min(width, height) <= 20
    )
