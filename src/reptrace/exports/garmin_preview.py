"""Render one Garmin workout confirmation image for Telegram."""

from io import BytesIO
from PIL import Image, ImageDraw

from reptrace.exports.plans import font

BG = "#0d1420"
PANEL = "#172432"
LINE = "#334254"
TEXT = "#edf3fa"
MUTED = "#a9bccb"
MINT = "#8ce5c1"
GOLD = "#ffd698"
WIDTH = 1200


def _lines(draw, value, face, max_width):
    result = []
    for paragraph in str(value).splitlines() or [""]:
        line = ""
        for word in paragraph.split(" "):
            candidate = (line + " " + word).strip()
            if draw.textlength(candidate, font=face) <= max_width:
                line = candidate
                continue
            if line:
                result.append(line)
                line = ""
            for char in word:
                if line and draw.textlength(line + char, font=face) > max_width:
                    result.append(line)
                    line = ""
                line += char
        result.append(line)
    return result


def _value(value, unit):
    return ("—" if value is None else str(value)) + " " + unit


def render_garmin_preview_image(preview):
    """Return one PNG with exercise sections and all proposed changes."""
    measure = ImageDraw.Draw(Image.new("RGB", (WIDTH, 1)))
    title_font = font(46, True)
    group_font = font(26, True)
    label_font = font(21, True)
    body_font = font(27)
    value_font = font(29, True)
    small_font = font(21)
    groups = {}
    for change in preview.get("changes", []):
        name = str(change.get("exercise") or "Unknown exercise")
        groups.setdefault(name.casefold(), {"name": name, "changes": []})[
            "changes"
        ].append(change)
    prepared = []
    for group in groups.values():
        name_lines = _lines(measure, group["name"], group_font, 1030)
        header_height = max(59, 24 + len(name_lines) * 34)
        rows = []
        for change in group["changes"]:
            step_lines = _lines(
                measure,
                f"Step {change.get('stepOrder', '—')} · {change.get('sets', '—')} set(s)",
                small_font,
                395,
            )
            rows.append((change, step_lines, max(83, len(step_lines) * 30 + 30)))
        prepared.append((name_lines, header_height, rows))
    notes = []
    for note in preview.get("skipped", []):
        line_text = (
            str(note.get("exercise") or "Workout")
            + ": "
            + str(note.get("reason") or "")
        )
        lines = _lines(measure, line_text, body_font, 1030)
        notes.append((lines, max(64, len(lines) * 38 + 18)))
    workout_lines = _lines(
        measure, preview.get("name") or "Untitled workout", title_font, 1060
    )
    table_top = 195 + len(workout_lines) * 58
    changes_height = (
        79
        + sum(
            header_height + sum(row[2] for row in rows)
            for _, header_height, rows in prepared
        )
        + 37
    )
    notes_height = 86 + sum(row_height for _, row_height in notes) + 25 if notes else 0
    height = table_top + changes_height + (22 + notes_height if notes else 0) + 98
    image = Image.new("RGB", (WIDTH, height), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 400, 7), fill=MINT)
    draw.rectangle((400, 0, 800, 7), fill=GOLD)
    draw.rectangle((800, 0, WIDTH, 7), fill="#8bbdff")
    draw.text((52, 36), "GARMIN WORKOUT · PREVIEW", font=label_font, fill=MINT)
    draw.rounded_rectangle((890, 30, 1148, 77), radius=18, fill="#523c22")
    draw.text((917, 40), "NOT SAVED", font=label_font, fill=GOLD)
    y = 94
    for line in workout_lines:
        draw.text((48, y), line, font=title_font, fill=TEXT)
        y += 58
    draw.text(
        (52, y + 12),
        "Proposed weight and rep changes · grouped by exercise",
        font=small_font,
        fill=MUTED,
    )
    draw.rounded_rectangle(
        (38, table_top, 1162, table_top + changes_height),
        radius=18,
        fill=PANEL,
        outline=LINE,
        width=2,
    )
    draw.text((60, table_top + 24), "GARMIN STEP", font=label_font, fill=MUTED)
    draw.text((520, table_top + 24), "FIELD", font=label_font, fill=MUTED)
    draw.text((695, table_top + 24), "CURRENT", font=label_font, fill=MUTED)
    draw.text((905, table_top + 24), "PROPOSED", font=label_font, fill=MINT)
    y = table_top + 76
    if not prepared:
        draw.text(
            (62, y + 2),
            "Target values stay the same; repeat blocks are regrouped below.",
            font=small_font,
            fill=TEXT,
        )
    for name_lines, header_height, rows in prepared:
        draw.rounded_rectangle(
            (54, y, 1146, y + header_height - 7), radius=9, fill="#253b42"
        )
        text_y = y + 10
        for line in name_lines:
            draw.text((68, text_y), line, font=group_font, fill=MINT)
            text_y += 34
        y += header_height
        for change, step_lines, row_height in rows:
            draw.line((54, y, 1146, y), fill=LINE, width=2)
            text_y = y + 14
            for line in step_lines:
                draw.text((62, text_y), line, font=small_font, fill=TEXT)
                text_y += 30
            field = change.get("field")
            unit = "kg" if field == "weight" else "reps"
            draw.text(
                (520, y + 20), str(field or "").title(), font=body_font, fill=TEXT
            )
            draw.text(
                (695, y + 20),
                _value(change.get("before"), unit),
                font=body_font,
                fill=MUTED,
            )
            draw.text(
                (905, y + 20),
                _value(change.get("after"), unit),
                font=value_font,
                fill=MINT,
            )
            y += row_height
    if notes:
        y = table_top + changes_height + 22
        draw.rounded_rectangle(
            (38, y, 1162, y + notes_height),
            radius=18,
            fill=PANEL,
            outline=LINE,
            width=2,
        )
        draw.text((60, y + 24), "WORKOUT NOTES", font=label_font, fill=MUTED)
        y += 73
        for lines, row_height in notes:
            draw.line((54, y, 1146, y), fill=LINE, width=2)
            text_y = y + 14
            for line in lines:
                draw.text((62, text_y), line, font=body_font, fill=TEXT)
                text_y += 38
            y += row_height
    draw.text(
        (52, height - 64),
        "Review all changes before pressing Save in Telegram · expires in 15 minutes",
        font=small_font,
        fill=MUTED,
    )
    if image.width + image.height > 9900:
        scale = 9900 / (image.width + image.height)
        image = image.resize(
            (int(image.width * scale), int(image.height * scale)),
            Image.Resampling.LANCZOS,
        )
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
