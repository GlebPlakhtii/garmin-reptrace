"""Preview and verify Garmin strength workout edits."""

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import re
from pathlib import Path
import sqlite3
import threading
import time
import uuid

from reptrace.training.strength import EXERCISE_NAME_ALIASES
from reptrace.training.planning import workout_type
from reptrace.storage.state import Conflict


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def identity(value):
    if isinstance(value, bool) or not str(value).isdigit() or int(value) <= 0:
        raise ValueError("Invalid Garmin workout ID")
    return int(value)


def exercise_name(step):
    label = (
        (step.get("exerciseName") or step.get("category") or "")
        .replace("_", " ")
        .title()
    )
    return EXERCISE_NAME_ALIASES.get(label, label)


def steps(workout):
    """Yield each physical step and its effective repetition count, in execution order."""

    def walk(items, path, multiplier):
        for index, step in enumerate(items):
            location = path + [index]
            if "workoutSteps" in step:
                count = step.get("numberOfIterations")
                if (
                    isinstance(count, bool)
                    or not isinstance(count, (int, float))
                    or not 1 <= count <= 100
                    or int(count) != count
                ):
                    raise ValueError("Unsupported repeat count in Garmin workout")
                yield from walk(
                    step["workoutSteps"],
                    location + ["workoutSteps"],
                    multiplier * int(count),
                )
            else:
                yield location, step, multiplier

    for index, segment in enumerate(workout.get("workoutSegments", [])):
        yield from walk(
            segment.get("workoutSteps", []),
            ["workoutSegments", index, "workoutSteps"],
            1,
        )


def at_path(value, path):
    for key in path:
        value = value[key]
    return value


def executed_steps(workout):
    """Flatten playback order without changing the stored workout."""
    result = []

    def walk(items, path, ancestors):
        for index, item in enumerate(items):
            item_path = path + [index]
            if "workoutSteps" not in item:
                result.append((item_path, item, ancestors))
                if len(result) > 5000:
                    raise ValueError("Garmin workout contains too many executed steps")
                continue
            count = item.get("numberOfIterations")
            if (
                isinstance(count, bool)
                or not isinstance(count, (int, float))
                or not 1 <= count <= 100
                or int(count) != count
            ):
                raise ValueError("Unsupported repeat count in Garmin workout")
            children = item["workoutSteps"]
            for iteration in range(int(count)):
                part = children
                if (
                    item.get("skipLastRestStep")
                    and iteration == count - 1
                    and children
                    and (children[-1].get("stepType") or {}).get("stepTypeKey")
                    == "rest"
                ):
                    part = children[:-1]
                walk(part, item_path + ["workoutSteps"], ancestors + [item_path])

    for segment_index, segment in enumerate(workout.get("workoutSegments", [])):
        walk(
            segment.get("workoutSteps", []),
            ["workoutSegments", segment_index, "workoutSteps"],
            [],
        )
    return result


def unroll_group(group):
    """Replace a repeat with its exact executable sequence."""
    result = []

    def unpack(item):
        if "workoutSteps" not in item:
            clone = deepcopy(item)
            clone.pop("stepId", None)
            clone["childStepId"] = None
            result.append(clone)
            return
        children = item["workoutSteps"]
        for iteration in range(int(item["numberOfIterations"])):
            part = children
            if (
                item.get("skipLastRestStep")
                and iteration == item["numberOfIterations"] - 1
                and children
                and (children[-1].get("stepType") or {}).get("stepTypeKey") == "rest"
            ):
                part = children[:-1]
            for child in part:
                unpack(child)

    unpack(group)
    return result


def unroll_group_iterations(group):
    """Return the executable leaves for each top-level repeat iteration."""
    result = []
    children = group["workoutSteps"]
    for iteration in range(int(group["numberOfIterations"])):
        part = children
        if (
            group.get("skipLastRestStep")
            and iteration == group["numberOfIterations"] - 1
            and children
            and (children[-1].get("stepType") or {}).get("stepTypeKey") == "rest"
        ):
            part = children[:-1]
        result.append([leaf for child in part for leaf in unroll_group(child)])
    return result


def regroup_iterations(group, items):
    """Keep consecutive iterations with identical targets in a Garmin repeat."""
    shapes = unroll_group_iterations(group)
    lengths = [len(part) for part in shapes]
    if sum(lengths) != len(items):
        raise RuntimeError("Expanded repeat length changed")
    iterations = []
    offset = 0
    for length in lengths:
        iterations.append(items[offset : offset + length])
        offset += length

    def signature(part):
        # The original group may omit only the final rest step on its last pass.
        if (
            group.get("skipLastRestStep")
            and part
            and (part[-1].get("stepType") or {}).get("stepTypeKey") == "rest"
        ):
            part = part[:-1]
        cleaned = []
        for step in part:
            value = deepcopy(step)
            for key in ("stepId", "stepOrder", "childStepId"):
                value.pop(key, None)
            cleaned.append(value)
        return fingerprint(cleaned)

    result = []
    start = 0
    while start < len(iterations):
        end = start + 1
        while end < len(iterations) and signature(iterations[end]) == signature(
            iterations[start]
        ):
            end += 1
        if end - start == 1:
            result.extend(iterations[start])
        else:
            repeat = deepcopy(group)
            repeat.pop("stepId", None)
            repeat["childStepId"] = None
            repeat["numberOfIterations"] = end - start
            if "endConditionValue" in repeat:
                repeat["endConditionValue"] = float(end - start)
            repeat["skipLastRestStep"] = bool(
                group.get("skipLastRestStep") and end == len(iterations)
            )
            repeat["workoutSteps"] = deepcopy(iterations[start])
            result.append(repeat)
        start = end
    return result


def coalesce_repeats(workout):
    """Group already-expanded consecutive identical steps without changing playback."""
    template = next(
        (
            item
            for segment in workout.get("workoutSegments", [])
            for item in segment.get("workoutSteps", [])
            if "workoutSteps" in item
        ),
        None,
    )
    if template is None:
        template = {
            "type": "RepeatGroupDTO",
            "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
            "endCondition": {
                "conditionTypeId": 7,
                "conditionTypeKey": "iterations",
                "displayOrder": 7,
                "displayable": False,
            },
            "preferredEndConditionUnit": None,
            "endConditionCompare": None,
            "smartRepeat": False,
        }

    def signature(item):
        value = deepcopy(item)
        for key in ("stepId", "stepOrder", "childStepId"):
            value.pop(key, None)
        return fingerprint(value)

    changed = False
    for segment in workout.get("workoutSegments", []):
        items = segment.get("workoutSteps", [])
        new = []
        index = 0
        while index < len(items):
            best = None
            if (
                "workoutSteps" not in items[index]
                and (items[index].get("stepType") or {}).get("stepTypeKey")
                == "interval"
            ):
                for width in range(1, min(9, (len(items) - index) // 2 + 1)):
                    pattern = items[index : index + width]
                    if len(pattern) < width or any(
                        "workoutSteps" in step for step in pattern
                    ):
                        continue
                    keys = [signature(step) for step in pattern]
                    count = 1
                    while count < 100 and index + (count + 1) * width <= len(items):
                        block = items[
                            index + count * width : index + (count + 1) * width
                        ]
                        if (
                            any("workoutSteps" in step for step in block)
                            or [signature(step) for step in block] != keys
                        ):
                            break
                        count += 1
                    if count < 2:
                        continue
                    coverage = count * width
                    skip = False
                    if (
                        width > 1
                        and (pattern[-1].get("stepType") or {}).get("stepTypeKey")
                        == "rest"
                        and count < 100
                    ):
                        remainder = items[
                            index + coverage : index + coverage + width - 1
                        ]
                        if (
                            len(remainder) == width - 1
                            and all("workoutSteps" not in step for step in remainder)
                            and [signature(step) for step in remainder] == keys[:-1]
                        ):
                            coverage += width - 1
                            count += 1
                            skip = True
                    candidate = (coverage, -width, count, skip, pattern)
                    if best is None or candidate[:2] > best[:2]:
                        best = candidate
            if best:
                coverage, _, count, skip, pattern = best
                repeat = deepcopy(template)
                repeat.pop("stepId", None)
                repeat["childStepId"] = None
                repeat["numberOfIterations"] = count
                repeat["endConditionValue"] = float(count)
                repeat["skipLastRestStep"] = skip
                repeat["workoutSteps"] = deepcopy(pattern)
                for child in repeat["workoutSteps"]:
                    child.pop("stepId", None)
                    child["childStepId"] = None
                new.append(repeat)
                index += coverage
                changed = True
            else:
                new.append(items[index])
                index += 1
        segment["workoutSteps"] = new
    if changed:
        renumber_steps(workout)
    return changed


def merge_adjacent_repeats(workout):
    """Extend an existing repeat with consecutive identical played iterations."""

    def signature(step):
        value = deepcopy(step)
        for key in ("stepId", "stepOrder", "childStepId"):
            value.pop(key, None)
        return fingerprint(value)

    before = [signature(step) for _, step, _ in executed_steps(workout)]
    changed = False
    for segment in workout.get("workoutSegments", []):
        items = segment.get("workoutSteps", [])
        index = 0
        while index < len(items):
            group = items[index]
            if "workoutSteps" not in group or group.get("skipLastRestStep"):
                index += 1
                continue
            parts = unroll_group_iterations(group)
            pattern = parts[0] if parts else []
            keys = [signature(step) for step in pattern]
            if not keys or any(
                [signature(step) for step in part] != keys for part in parts[1:]
            ):
                index += 1
                continue
            while group["numberOfIterations"] < 100:
                following = items[index + 1 : index + 1 + len(keys)]
                if (
                    len(following) != len(keys)
                    or any("workoutSteps" in step for step in following)
                    or [signature(step) for step in following] != keys
                ):
                    break
                del items[index + 1 : index + 1 + len(keys)]
                group["numberOfIterations"] += 1
                group["endConditionValue"] = float(group["numberOfIterations"])
                changed = True
            index += 1
    if changed:
        renumber_steps(workout)
        if [signature(step) for _, step, _ in executed_steps(workout)] != before:
            raise RuntimeError("Grouping repeat steps would change workout execution")
    return changed


def playback_signature(step):
    item = deepcopy(step)
    for key in ("stepId", "stepOrder", "childStepId"):
        item.pop(key, None)
    if (item.get("endCondition") or {}).get("conditionTypeKey") == "reps":
        item.pop("weightValue", None)
        item.pop("endConditionValue", None)
    return item


def renumber_steps(workout):
    order = 0

    def walk(items):
        nonlocal order
        for item in items:
            order += 1
            item["stepOrder"] = order
            if "workoutSteps" in item:
                walk(item["workoutSteps"])

    for segment in workout.get("workoutSegments", []):
        walk(segment.get("workoutSteps", []))


def field_changes(before, after):
    old = executed_steps(before)
    new = executed_steps(after)
    if len(old) != len(new) or [playback_signature(s) for _, s, _ in old] != [
        playback_signature(s) for _, s, _ in new
    ]:
        raise RuntimeError("Workout exercise or rest sequence changed")
    grouped = {}
    for (_, original, _), (path, updated, _) in zip(old, new):
        if (updated.get("endCondition") or {}).get("conditionTypeKey") != "reps":
            continue
        for field, key in [("weight", "weightValue"), ("reps", "endConditionValue")]:
            if original.get(key) == updated.get(key):
                continue
            group_key = (tuple(path), field)
            if group_key not in grouped:
                grouped[group_key] = {
                    "exercise": exercise_name(updated),
                    "field": field,
                    "before": original.get(key),
                    "after": updated.get(key),
                    "sets": 0,
                    "stepOrder": updated.get("stepOrder"),
                    "path": path + [key],
                }
            elif grouped[group_key]["before"] != original.get(key) or grouped[
                group_key
            ]["after"] != updated.get(key):
                raise RuntimeError("Repeat block contains inconsistent targets")
            grouped[group_key]["sets"] += 1
    return list(grouped.values())


def make_update(workout, plan):
    if (workout.get("sportType") or {}).get("sportTypeKey") != "strength_training":
        raise ValueError("Select a strength workout")
    if not plan or not plan.get("exercises"):
        raise ValueError("No next-session suggestions for this workout type")
    original = executed_steps(workout)
    proposed = {}
    skipped = []
    by_exercise = defaultdict(list)
    for number, (_, step, _) in enumerate(original):
        if (step.get("stepType") or {}).get("stepTypeKey") == "interval" and (
            step.get("endCondition") or {}
        ).get("conditionTypeKey") == "reps":
            by_exercise[exercise_name(step)].append(number)
    plan_names = defaultdict(list)
    for exercise in plan["exercises"]:
        plan_names[exercise["name"].casefold()].append(exercise)
    selected_groups = set()
    for name, indexes in by_exercise.items():
        matches = plan_names.get(name.casefold(), [])

        def skip(reason):
            skipped.append({"exercise": name, "field": None, "reason": reason})

        if len(matches) != 1:
            skip("No unique matching next-session exercise.")
            continue
        suggestion = matches[0]
        if suggestion.get("status") == "review" or plan.get("stale"):
            skip("The suggestion requires review.")
            continue
        targets = suggestion["proposed"]
        if len(targets) != len(indexes):
            # A uniform proposal can safely fill every existing Garmin set even
            # when the logged workout and template have different set counts.
            # Mixed targets have no unambiguous position for the extra sets.
            if targets and all(target == targets[0] for target in targets):
                targets = [targets[0]] * len(indexes)
                skipped.append(
                    {
                        "exercise": name,
                        "field": None,
                        "applied": True,
                        "reason": "The logged and Garmin set counts differ; the same suggested target was applied to every existing Garmin set.",
                    }
                )
            else:
                skip("Garmin and suggested set counts differ, and targets vary by set.")
                continue
        if any(
            not isinstance(t, dict)
            or not all(
                isinstance(t.get(k), (int, float))
                and not isinstance(t[k], bool)
                and math.isfinite(t[k])
                for k in ("weight", "reps")
            )
            or not 0 <= t["weight"] <= 2000
            or not 1 <= t["reps"] <= 500
            or int(t["reps"]) != t["reps"]
            for t in targets
        ):
            skip("A suggested weight or rep count is missing or invalid.")
            continue
        for index, target in zip(indexes, targets):
            step = original[index][1]
            if (step.get("weightUnit") or {}).get("unitKey") != "kilogram" and step.get(
                "weightValue"
            ) != target["weight"]:
                skip(
                    "Existing weight unit is not kilograms; this exercise is unchanged."
                )
                break
        else:
            for index, target in zip(indexes, targets):
                proposed[index] = target
            by_path = defaultdict(list)
            for index in indexes:
                by_path[tuple(original[index][0])].append(index)
            for group_indexes in by_path.values():
                targets_here = [proposed[index] for index in group_indexes]
                if (
                    len(group_indexes) > 1
                    and len({(t["weight"], t["reps"]) for t in targets_here}) > 1
                ):
                    selected_groups.add(tuple(original[group_indexes[0]][2][0]))
    updated = deepcopy(workout)
    expanded_ranges = []
    for segment_index, segment in enumerate(updated.get("workoutSegments", [])):
        old_items = segment.get("workoutSteps", [])
        new_items = []
        for index, item in enumerate(old_items):
            group_path = ("workoutSegments", segment_index, "workoutSteps", index)
            if group_path in selected_groups:
                leaves = unroll_group(item)
                expanded_ranges.append(
                    (segment_index, len(new_items), len(leaves), item)
                )
                new_items.extend(leaves)
                skipped.append(
                    {
                        "exercise": ", ".join(
                            dict.fromkeys(
                                exercise_name(child)
                                for child in item.get("workoutSteps", [])
                                if (child.get("stepType") or {}).get("stepTypeKey")
                                == "interval"
                            )
                        ),
                        "field": None,
                        "applied": True,
                        "reason": "Repeat block split where targets differ; consecutive identical targets stay grouped. Exercise and rest order is preserved.",
                    }
                )
            else:
                new_items.append(item)
        segment["workoutSteps"] = new_items
    if selected_groups:
        renumber_steps(updated)
    after = executed_steps(updated)
    if len(after) != len(original) or [playback_signature(s) for _, s, _ in after] != [
        playback_signature(s) for _, s, _ in original
    ]:
        raise RuntimeError("Expanding repeats would change exercise or rest sequence")
    for index, target in proposed.items():
        step = at_path(updated, after[index][0])
        step["weightValue"] = target["weight"]
        step["endConditionValue"] = target["reps"]
    for segment_index, start, length, group in sorted(
        expanded_ranges, key=lambda item: (item[0], item[1]), reverse=True
    ):
        items = updated["workoutSegments"][segment_index]["workoutSteps"]
        items[start : start + length] = regroup_iterations(
            group, items[start : start + length]
        )
    if expanded_ranges:
        renumber_steps(updated)
    grouped = coalesce_repeats(updated)
    grouped = merge_adjacent_repeats(updated) or grouped
    if grouped:
        skipped.append(
            {
                "exercise": "Workout",
                "field": None,
                "applied": True,
                "reason": "Consecutive sets with identical weight and reps are grouped into Garmin repeat blocks.",
            }
        )
    final = executed_steps(updated)
    if (
        len(final) != len(after)
        or [step.get("weightValue") for _, step, _ in final]
        != [step.get("weightValue") for _, step, _ in after]
        or [step.get("endConditionValue") for _, step, _ in final]
        != [step.get("endConditionValue") for _, step, _ in after]
        or [playback_signature(step) for _, step, _ in final]
        != [playback_signature(step) for _, step, _ in after]
    ):
        raise RuntimeError("Regrouping repeats would change workout execution")
    changes = field_changes(workout, updated)
    return updated, changes, skipped


def editable_steps(workout, suggested=None):
    result = []
    for path, step, count in steps(workout):
        if (step.get("stepType") or {}).get("stepTypeKey") != "interval" or (
            step.get("endCondition") or {}
        ).get("conditionTypeKey") != "reps":
            continue
        target = at_path(suggested, path) if suggested else step
        result.append(
            {
                "index": len(result),
                "exercise": exercise_name(step),
                "stepOrder": step.get("stepOrder"),
                "sets": count,
                "weightEditable": (step.get("weightUnit") or {}).get("unitKey")
                == "kilogram",
                "weight": step.get("weightValue"),
                "reps": step.get("endConditionValue"),
                "suggestedWeight": target.get("weightValue"),
                "suggestedReps": target.get("endConditionValue"),
                "path": path,
            }
        )
    return result


def manual_update(before, base, targets):
    if not isinstance(targets, list) or len(targets) > 500:
        raise ValueError("Invalid manual targets")
    after = deepcopy(base)
    rows = editable_steps(base)
    seen = set()
    for item in targets:
        if not isinstance(item, dict) or set(item) - {"index", "weight", "reps"}:
            raise ValueError("Only weight and reps can be edited")
        index = item.get("index")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 0 <= index < len(rows)
            or index in seen
        ):
            raise ValueError("Invalid or repeated Garmin step")
        seen.add(index)
        row = rows[index]
        step = at_path(after, row["path"])
        for field, key in [("weight", "weightValue"), ("reps", "endConditionValue")]:
            if field not in item or item[field] is None:
                continue
            value = item[field]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not (
                    0 <= value <= 2000
                    if field == "weight"
                    else 1 <= value <= 500 and int(value) == value
                )
            ):
                raise ValueError("Invalid weight or rep value")
            if field == "weight" and not row["weightEditable"]:
                raise ValueError("This weight is not recorded in kilograms")
            step[key] = value
    prior = executed_steps(after)
    coalesce_repeats(after)
    merge_adjacent_repeats(after)
    current = executed_steps(after)
    if (
        len(prior) != len(current)
        or [playback_signature(step) for _, step, _ in prior]
        != [playback_signature(step) for _, step, _ in current]
        or [
            (step.get("weightValue"), step.get("endConditionValue"))
            for _, step, _ in prior
        ]
        != [
            (step.get("weightValue"), step.get("endConditionValue"))
            for _, step, _ in current
        ]
    ):
        raise RuntimeError("Regrouping repeats would change workout execution")
    changes = field_changes(before, after)
    return after, changes


def saved_workout_matches(expected, actual):
    """Garmin renumbers step identifiers on PUT; verify all workout content."""

    def segments(value):
        result = deepcopy(value.get("workoutSegments"))

        def clean(items):
            for step in items:
                step.pop("stepId", None)
                step.pop("childStepId", None)
                # Garmin fills absent optional targets with null and neutral
                # equipment/stroke DTOs. Only these observed defaults are equivalent.
                optional = (
                    "secondaryTargetValueUnit",
                    "targetValueTwo",
                    "secondaryTargetValueTwo",
                    "secondaryTargetType",
                    "secondaryTargetValueOne",
                    "endConditionCompare",
                    "secondaryZoneNumber",
                    "preferredEndConditionUnit",
                    "zoneNumber",
                    "targetValueOne",
                    "providerExerciseSourceId",
                    "workoutProvider",
                    "targetValueUnit",
                    "endConditionZone",
                )
                for key in optional:
                    if step.get(key) is None:
                        step.pop(key, None)
                for key, prefix in (
                    ("equipmentType", "equipmentType"),
                    ("strokeType", "strokeType"),
                ):
                    if step.get(key) is None or step.get(key) == {
                        prefix + "Id": 0,
                        prefix + "Key": None,
                        "displayOrder": 0,
                    }:
                        step.pop(key, None)
                if "workoutSteps" in step:
                    clean(step["workoutSteps"])

        if isinstance(result, list):
            for segment in result:
                clean(segment.get("workoutSteps", []))
        return result

    return all(
        actual.get(key) == expected.get(key)
        for key in ("workoutId", "workoutName", "description", "sportType")
    ) and segments(actual) == segments(expected)


def full_workout_edit(before, body):
    """Apply editable Garmin fields while retaining provider-owned metadata."""
    name = body.get("name")
    description = body.get("description")
    segments = body.get("segments")
    if not isinstance(name, str) or not name.strip() or len(name) > 120:
        raise ValueError("Enter a workout name (up to 120 characters)")
    if description is not None and (
        not isinstance(description, str) or len(description) > 1000
    ):
        raise ValueError("Description is too long")
    if not isinstance(segments, list) or not 1 <= len(segments) <= 20:
        raise ValueError("A workout needs 1–20 segments")
    # The editor starts from a Garmin payload. Validate the editable structure,
    # then preserve every other field exactly as Garmin supplied it.
    total = 0

    def check(items, depth=0):
        nonlocal total
        if depth > 5 or not isinstance(items, list) or len(items) > 500:
            raise ValueError("Invalid workout steps")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Invalid workout step")
            total += 1
            if total > 2000:
                raise ValueError("Too many workout steps")
            kind = (item.get("stepType") or {}).get("stepTypeKey")
            if "workoutSteps" in item:
                count = item.get("numberOfIterations")
                if (
                    kind not in ("repeat", None)
                    or isinstance(count, bool)
                    or not isinstance(count, int)
                    or not 2 <= count <= 100
                ):
                    raise ValueError("Repeat blocks need 2–100 iterations")
                if not item["workoutSteps"]:
                    raise ValueError("Repeat block cannot be empty")
                check(item["workoutSteps"], depth + 1)
                continue
            if kind not in ("interval", "warmup", "cooldown", "rest"):
                raise ValueError("Unsupported step type")
            condition = (item.get("endCondition") or {}).get("conditionTypeKey")
            value = item.get("endConditionValue")
            if condition not in ("reps", "time", "lap.button"):
                raise ValueError("Unsupported step target")
            if condition in ("reps", "time") and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 1 <= value <= (500 if condition == "reps" else 86400)
                or (condition == "reps" and int(value) != value)
            ):
                raise ValueError("Invalid reps or duration")
            if kind != "rest":
                for key in ("category", "exerciseName"):
                    code = item.get(key)
                    # Garmin uses category alone for some library exercises.
                    if key == "exerciseName" and code == "":
                        continue
                    if not isinstance(code, str) or not re.fullmatch(
                        r"[A-Z0-9_]{1,100}", code
                    ):
                        raise ValueError(
                            "Exercise needs a valid Garmin category and code"
                        )
                weight = item.get("weightValue")
                if weight is not None and (
                    isinstance(weight, bool)
                    or not isinstance(weight, (int, float))
                    or not math.isfinite(weight)
                    or not 0 <= weight <= 2000
                ):
                    raise ValueError("Invalid weight")

    for segment in segments:
        if not isinstance(segment, dict) or not isinstance(
            segment.get("workoutSteps"), list
        ):
            raise ValueError("Invalid workout segment")
        check(segment["workoutSteps"])
    after = deepcopy(before)
    after["workoutName"] = name.strip()
    after["description"] = description or None
    after["workoutSegments"] = deepcopy(segments)
    renumber_steps(after)
    merge_adjacent_repeats(after)
    if not executed_steps(after):
        raise ValueError(
            "Workout needs at least one step"
        )  # Also bounds expanded playback.
    return after


def full_edit_summary(before, after):
    changes = []
    for field, label in (("workoutName", "Name"), ("description", "Description")):
        if before.get(field) != after.get(field):
            changes.append(
                {"label": label, "before": before.get(field), "after": after.get(field)}
            )
    old = executed_steps(before)
    new = executed_steps(after)
    if before.get("workoutSegments") != after.get("workoutSegments"):

        def meaningful(step):
            if step is None:
                return None
            value = deepcopy(step)
            for key in ("stepId", "childStepId", "stepOrder"):
                value.pop(key, None)
            return value

        def label(step):
            kind = (step.get("stepType") or {}).get("stepTypeKey") or "step"
            condition = (step.get("endCondition") or {}).get("conditionTypeKey")
            target = (
                step.get("endConditionValue")
                if condition != "lap.button"
                else "lap button"
            )
            unit_key = (step.get("weightUnit") or {}).get("unitKey")
            unit = {"kilogram": "kg", "pound": "lb"}.get(
                unit_key, unit_key or "unit unspecified"
            )
            return (
                f"{exercise_name(step) if kind != 'rest' else 'Rest'} · {target} {condition if condition != 'lap.button' else ''} · {step.get('weightValue')} {unit}"
                if kind != "rest"
                else f"Rest · {target} {condition if condition != 'lap.button' else ''}"
            )

        for index in range(max(len(old), len(new))):
            first = old[index][1] if index < len(old) else None
            second = new[index][1] if index < len(new) else None
            if meaningful(first) != meaningful(second):
                fields = sorted(
                    k
                    for k in set(first or {}) | set(second or {})
                    if k not in ("stepId", "childStepId", "stepOrder")
                    and (first or {}).get(k) != (second or {}).get(k)
                )
                changes.append(
                    {
                        "label": f"Step {index + 1}"
                        + (f" ({', '.join(fields)})" if fields else ""),
                        "before": label(first) if first else "None",
                        "after": label(second) if second else "Removed",
                    }
                )
        if not any(c["label"].startswith("Step ") for c in changes):
            changes.append(
                {
                    "label": "Repeat structure or step order",
                    "before": f"{len(old)} played steps",
                    "after": f"{len(new)} played steps",
                }
            )
    return changes


def garmin_exercise_catalog(query):
    """Search the FIT exercise codes already shipped with our fitparse dependency."""
    from fitparse.profile import FIELD_TYPES

    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 100:
        raise ValueError("Enter an exercise search (1–100 characters)")
    words = re.findall(r"[a-z0-9]+", query.lower().replace("_", " "))
    alias = any(w in words for w in ("captain", "captains", "capitan")) or (
        "chair" in words and any(w in words for w in ("leg", "legs", "knee"))
    )
    if alias:
        words = ["leg", "raise"]
    found = []
    for key, field in FIELD_TYPES.items():
        if not key.endswith("_exercise_name"):
            continue
        category = key.removesuffix("_exercise_name").upper()
        if alias and category != "LEG_RAISE":
            continue
        for code in ["", *(field.values or {}).values()]:
            code = code.upper()
            label = (code or category).replace("_", " ").title()
            haystack = (category + " " + code).replace("_", " ").lower()
            if all(word in haystack for word in words):
                found.append(
                    {
                        "category": category,
                        "exerciseCode": code,
                        "name": label,
                        "generic": not code,
                    }
                )
    return {
        "exercises": found[:60],
        "truncated": len(found) > 60,
        "note": "Captain's chair has no dedicated code in this catalogue. Use generic LEG_RAISE with a Captain's chair description; do not substitute hanging leg raises silently."
        if alias
        else "Generic category entries support a description when an exact exercise is unavailable.",
    }


def append_exercise(
    details, category, code, sets_count, reps, weight, rest_seconds, notes
):
    """Build an additive full-edit draft; never reuse another exercise's targets."""
    from fitparse.profile import FIELD_TYPES

    field = FIELD_TYPES.get(str(category).lower() + "_exercise_name")
    if (
        field is None
        or not isinstance(code, str)
        or (code and code.lower() not in (field.values or {}).values())
    ):
        raise ValueError(
            "Choose a category and exerciseCode from search_garmin_exercises"
        )
    if not isinstance(category, str) or category != category.upper():
        raise ValueError("Use the returned uppercase category")
    for value, maximum, label in ((sets_count, 20, "sets"), (reps, 500, "reps")):
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 1 <= value <= maximum
        ):
            raise ValueError("Invalid " + label)
    if weight is not None and (
        isinstance(weight, bool)
        or not isinstance(weight, (int, float))
        or not math.isfinite(weight)
        or not 0 <= weight <= 2000
    ):
        raise ValueError("Invalid external weight")
    if rest_seconds is not None and (
        isinstance(rest_seconds, bool)
        or not isinstance(rest_seconds, int)
        or not 1 <= rest_seconds <= 3600
    ):
        raise ValueError("Invalid rest seconds")
    if not isinstance(notes, str) or len(notes) > 500:
        raise ValueError("Exercise notes must be at most 500 characters")
    if not code and not notes.strip():
        raise ValueError("Describe the exercise when using a generic category")
    segments = deepcopy(details.get("segments"))
    if not isinstance(segments, list) or not segments:
        raise ValueError("Workout has no segment to append to")
    existing = list(executed_steps({"workoutSegments": segments}))
    if any(
        s.get("category") == category
        and (s.get("exerciseName") or "") == code
        and (
            code
            or (s.get("description") or "").strip().casefold()
            == notes.strip().casefold()
        )
        for _, s, _ in existing
    ):
        raise ValueError(
            "This exercise is already in the template. Review it before adding duplicate sets."
        )
    if (
        existing
        and (existing[-1][1].get("stepType") or {}).get("stepTypeKey") == "cooldown"
    ):
        raise ValueError(
            "Workout ends with a cooldown. Use the full editor to choose the insertion position."
        )
    if rest_seconds is None:
        prior = next(
            (
                s
                for _, s, _ in reversed(existing)
                if (s.get("stepType") or {}).get("stepTypeKey") == "rest"
            ),
            None,
        )
        if not prior:
            raise ValueError("No existing rest step to copy. Specify rest_seconds.")
        rest = deepcopy(prior)
        rest.pop("stepId", None)
        rest["childStepId"] = None
    else:
        rest = {
            "type": "ExecutableStepDTO",
            "stepType": {"stepTypeId": 5, "stepTypeKey": "rest", "displayOrder": 5},
            "endCondition": {
                "conditionTypeId": 2,
                "conditionTypeKey": "time",
                "displayOrder": 2,
            },
            "endConditionValue": rest_seconds,
        }
    exercise = {
        "type": "ExecutableStepDTO",
        "stepType": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
        "endCondition": {
            "conditionTypeId": 10,
            "conditionTypeKey": "reps",
            "displayOrder": 10,
            "displayable": True,
        },
        "endConditionValue": reps,
        "targetType": {
            "workoutTargetTypeId": 1,
            "workoutTargetTypeKey": "no.target",
            "displayOrder": 1,
        },
        "category": category,
        "exerciseName": code,
        "description": notes or None,
        "weightValue": weight,
        "weightUnit": {"unitId": 8, "unitKey": "kilogram", "factor": 1000.0}
        if weight is not None
        else None,
    }
    tail = segments[-1]["workoutSteps"]
    if (
        existing
        and (existing[-1][1].get("stepType") or {}).get("stepTypeKey") != "rest"
    ):
        tail.append(deepcopy(rest))
    for _ in range(sets_count):
        tail.extend([deepcopy(exercise), deepcopy(rest)])
    return {
        "operation": "edit",
        "workoutId": details["workoutId"],
        "expectedRevision": details["revision"],
        "name": details["name"],
        "description": details["description"],
        "segments": segments,
    }


class GarminAdapter:
    def __init__(self):
        from garminconnect import Garmin

        self.client = Garmin(
            is_cn=os.getenv("GARMINCONNECT_IS_CN", "false").lower() == "true"
        )
        self.client.login(os.getenv("TOKEN_DIR", "/home/appuser/.garminconnect"))

    def list(self):
        result = []
        for offset in range(0, 2000, 100):
            page = self.client.get_workouts(offset, 100)
            result.extend(page)
            if len(page) < 100:
                return result
        raise ValueError(
            "Too many Garmin workouts; narrow the account library before syncing"
        )

    def get(self, workout_id):
        return self.client.get_workout_by_id(workout_id)

    def update(self, workout_id, payload):
        # Same endpoint as upstream update_workout; retain the stable ingestion dependency.
        self.client.garth.put(
            "connectapi",
            f"/workout-service/workout/{workout_id}",
            json=payload,
            api=True,
        )

    def activity_sets(self, activity_id):
        return self.client.get_activity_exercise_sets(identity(activity_id))

    def update_activity_sets(self, activity_id, payload):
        return self.client.garth.put("connectapi", f"/activity-service/activity/{identity(activity_id)}/exerciseSets", json=payload, api=True)

    def create(self, payload):
        return self.client.garth.post("connectapi", "/workout-service/workout", json=payload, api=True)

    def devices(self):
        return self.client.get_devices()

    def device_messages(self):
        return self.client.connectapi('/device-service/devicemessage/messages')

    def deliver(self, workout_id, device_id, name):
        workout_id, device_id = identity(workout_id), identity(device_id)
        return self.client.garth.post("connectapi", "/device-service/devicemessage/messages", json=[{
            "deviceId": device_id, "messageUrl": f"workout-service/workout/FIT/{workout_id}",
            "messageType": "workouts", "groupName": None, "messageName": name,
            "priority": 1, "fileType": "FIT", "metaDataId": workout_id,
        }], api=True)


class GarminWorkouts:
    def __init__(self, path, factory=GarminAdapter):
        self.path = Path(path)
        self.factory = factory
        self.lock = threading.Lock()

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path)
        try:
            db.row_factory = sqlite3.Row
            db.execute(
                "CREATE TABLE IF NOT EXISTS updates(id TEXT PRIMARY KEY, created REAL, workout_id INTEGER, plan_type TEXT, plan_hash TEXT, before_json TEXT, after_json TEXT, preview_json TEXT, status TEXT)"
            )
        except BaseException:
            db.close()
            raise
        return db

    def call(self, body, plans):
        with self.lock:
            operation = body.get("operation")
            if operation not in (
                "list",
                "details",
                "edit",
                "preview",
                "revise",
                "apply",
                "review",
            ):
                raise ValueError("Unknown Garmin workout operation")
            if operation == "review":
                name = body.get("workoutName")
                if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
                    raise ValueError("Choose a workout name")
                try:
                    session_time = datetime.fromisoformat(
                        str(body.get("sessionTime", "")).replace("Z", "+00:00")
                    )
                    if session_time.tzinfo is None:
                        raise ValueError()
                    cutoff = session_time.timestamp()
                except (TypeError, ValueError, OverflowError):
                    raise ValueError("Invalid session time") from None
                db = self.connect()
                try:
                    matches = []
                    for row in db.execute(
                        "SELECT created,after_json FROM updates WHERE status='done' AND created<=? ORDER BY created DESC",
                        (cutoff,),
                    ):
                        saved = json.loads(row["after_json"])
                        if saved.get("workoutName", "").casefold() == name.casefold():
                            matches.append((row["created"], saved))
                        if matches:
                            break
                finally:
                    db.close()
                if matches:
                    as_of, workout = matches[0]
                    source = "app_snapshot"
                elif time.time() - cutoff <= 72 * 3600:
                    client = self.factory()
                    candidates = [
                        w
                        for w in client.list()
                        if w.get("workoutName", "").casefold() == name.casefold()
                        and (w.get("sportType") or {}).get("sportTypeKey")
                        == "strength_training"
                    ]
                    if len(candidates) != 1:
                        return {
                            "reason": "No unique Garmin strength template matches this workout name."
                        }
                    workout = client.get(identity(candidates[0]["workoutId"]))
                    as_of = time.time()
                    source = "current_template"
                else:
                    return {
                        "reason": "No saved Garmin template snapshot predates this session. A current template would not establish the historical plan."
                    }
                planned = []
                for _, step, _ in executed_steps(workout):
                    if (step.get("stepType") or {}).get(
                        "stepTypeKey"
                    ) != "interval" or (step.get("endCondition") or {}).get(
                        "conditionTypeKey"
                    ) != "reps":
                        continue
                    planned.append(
                        {
                            "exercise": exercise_name(step),
                            "weight": step.get("weightValue")
                            if (step.get("weightUnit") or {}).get("unitKey")
                            == "kilogram"
                            else None,
                            "reps": step.get("endConditionValue"),
                        }
                    )
                return {
                    "name": workout.get("workoutName") or name,
                    "source": source,
                    "asOf": datetime.fromtimestamp(as_of, timezone.utc).isoformat(),
                    "plannedSets": planned,
                }
            if operation == "list":
                return {
                    "workouts": [
                        {
                            "id": identity(w["workoutId"]),
                            "name": w.get("workoutName", "Untitled"),
                            "planType": workout_type(w.get("workoutName")),
                        }
                        for w in self.factory().list()
                        if (w.get("sportType") or {}).get("sportTypeKey")
                        == "strength_training"
                    ]
                }
            if operation == "details":
                before = self.factory().get(identity(body.get("workoutId")))
                if (before.get("sportType") or {}).get(
                    "sportTypeKey"
                ) != "strength_training":
                    raise ValueError("Select a strength workout")
                return {
                    "revision": fingerprint(before),
                    "workoutId": before["workoutId"],
                    "name": before.get("workoutName") or "",
                    "description": before.get("description") or "",
                    "segments": before.get("workoutSegments") or [],
                }
            db = self.connect()
            try:
                if operation == "edit":
                    workout_id = identity(body.get("workoutId"))
                    before = self.factory().get(workout_id)
                    if (
                        identity(before.get("workoutId")) != workout_id
                        or (before.get("sportType") or {}).get("sportTypeKey")
                        != "strength_training"
                    ):
                        raise ValueError("Select a strength workout")
                    if body.get("expectedRevision") is not None and body[
                        "expectedRevision"
                    ] != fingerprint(before):
                        raise Conflict(
                            "Garmin workout changed; read it again before drafting edits"
                        )
                    after = full_workout_edit(before, body)
                    changes = full_edit_summary(before, after)
                    token = str(uuid.uuid4())
                    preview = {
                        "previewId": token,
                        "workoutId": workout_id,
                        "name": after["workoutName"],
                        "fullEdit": True,
                        "changes": changes,
                        "before": {
                            "name": before.get("workoutName"),
                            "description": before.get("description"),
                            "segments": before.get("workoutSegments"),
                        },
                        "after": {
                            "name": after["workoutName"],
                            "description": after.get("description"),
                            "segments": after["workoutSegments"],
                        },
                    }
                    db.execute(
                        "INSERT INTO updates VALUES(?,?,?,?,?,?,?,?,?)",
                        (
                            token,
                            time.time(),
                            workout_id,
                            None,
                            fingerprint(None),
                            json.dumps(before),
                            json.dumps(after),
                            json.dumps(preview),
                            "preview",
                        ),
                    )
                    db.commit()
                    return preview
                if operation == "preview":
                    workout_id = identity(body.get("workoutId"))
                    before = self.factory().get(workout_id)
                    if identity(before.get("workoutId")) != workout_id:
                        raise ValueError("Garmin returned a different workout")
                    plan_type = workout_type(before.get("workoutName"))
                    plan = next((p for p in plans if p["type"] == plan_type), None)
                    if (before.get("sportType") or {}).get(
                        "sportTypeKey"
                    ) != "strength_training":
                        raise ValueError("Select a strength workout")
                    after, changes, skipped = (
                        make_update(before, plan)
                        if plan and plan.get("exercises")
                        else (deepcopy(before), [], [])
                    )
                    editable = [
                        {k: v for k, v in r.items() if k != "path"}
                        for r in editable_steps(before)
                    ]
                    token = str(uuid.uuid4())
                    preview = {
                        "previewId": token,
                        "workoutId": workout_id,
                        "name": before.get("workoutName"),
                        "editable": editable,
                        "changes": [
                            {k: v for k, v in c.items() if k != "path"} for c in changes
                        ],
                        "structureChanged": before.get("workoutSegments")
                        != after.get("workoutSegments"),
                        "skipped": skipped,
                    }
                    db.execute(
                        "INSERT INTO updates VALUES(?,?,?,?,?,?,?,?,?)",
                        (
                            token,
                            time.time(),
                            workout_id,
                            plan_type,
                            fingerprint(plan),
                            json.dumps(before),
                            json.dumps(after),
                            json.dumps(preview),
                            "preview",
                        ),
                    )
                    db.commit()
                    return preview
                token = str(uuid.UUID(body.get("previewId", "")))
                row = db.execute(
                    "SELECT * FROM updates WHERE id=?", (token,)
                ).fetchone()
                if not row:
                    raise ValueError("Preview not found; create a new preview")
                if operation == "revise":
                    if row["plan_type"] is None:
                        raise ValueError(
                            "Full edits cannot be revised as target-only edits"
                        )
                    if row["status"] != "preview" or time.time() - row["created"] > 900:
                        raise Conflict(
                            "Preview expired or already used; reload the workout"
                        )
                    if not isinstance(body.get("useSuggestions", False), bool):
                        raise ValueError("Invalid suggestion choice")
                    before = json.loads(row["before_json"])
                    base = (
                        json.loads(row["after_json"])
                        if body.get("useSuggestions")
                        else before
                    )
                    after, changes = manual_update(
                        before, base, body.get("manualTargets", [])
                    )
                    preview = json.loads(row["preview_json"])
                    new_token = str(uuid.uuid4())
                    preview.update(
                        previewId=new_token,
                        changes=[
                            {k: v for k, v in c.items() if k != "path"} for c in changes
                        ],
                        editable=[
                            {k: v for k, v in r.items() if k != "path"}
                            for r in editable_steps(after)
                        ],
                        structureChanged=before.get("workoutSegments")
                        != after.get("workoutSegments"),
                    )
                    if not body.get("useSuggestions"):
                        preview["skipped"] = (
                            [
                                {
                                    "exercise": "Workout",
                                    "field": None,
                                    "applied": True,
                                    "reason": "Consecutive sets with identical weight and reps are grouped into Garmin repeat blocks.",
                                }
                            ]
                            if preview["structureChanged"]
                            else []
                        )
                    db.execute(
                        "INSERT INTO updates VALUES(?,?,?,?,?,?,?,?,?)",
                        (
                            new_token,
                            row["created"],
                            row["workout_id"],
                            row["plan_type"],
                            row["plan_hash"],
                            row["before_json"],
                            json.dumps(after),
                            json.dumps(preview),
                            "preview",
                        ),
                    )
                    db.execute(
                        "UPDATE updates SET status='superseded' WHERE id=?", (token,)
                    )
                    db.commit()
                    return preview
                if row["status"] == "done":
                    return {
                        "ok": True,
                        "workoutId": row["workout_id"],
                        "alreadyApplied": True,
                    }
                if row["status"] == "sending":
                    # Reconcile a lost response or earlier verification failure without
                    # repeating a write whose remote outcome was initially uncertain.
                    actual = self.factory().get(row["workout_id"])
                    if saved_workout_matches(json.loads(row["after_json"]), actual):
                        db.execute(
                            "UPDATE updates SET status='done',created=? WHERE id=?",
                            (time.time(), token),
                        )
                        db.commit()
                        return {
                            "ok": True,
                            "workoutId": row["workout_id"],
                            "alreadyApplied": True,
                            "reconciled": True,
                        }
                    raise Conflict(
                        "The previous update could not be verified. Check Garmin and create a new preview; no repeat update was sent."
                    )
                if row["status"] != "preview":
                    raise Conflict(
                        "Previous update outcome is uncertain. Check Garmin and create a fresh preview; this request will not be sent again."
                    )
                if time.time() - row["created"] > 900:
                    raise Conflict("Preview expired; create a new preview")
                plan = next((p for p in plans if p["type"] == row["plan_type"]), None)
                if fingerprint(plan) != row["plan_hash"]:
                    raise Conflict("Suggestions changed; create a new preview")
                before = json.loads(row["before_json"])
                after = json.loads(row["after_json"])
                if before == after:
                    raise ValueError("No workout changes to apply")
                client = self.factory()
                current = client.get(row["workout_id"])
                if fingerprint(current) != fingerprint(before):
                    raise Conflict("Garmin workout changed; create a fresh preview")
                db.execute("UPDATE updates SET status='sending' WHERE id=?", (token,))
                db.commit()
                client.update(row["workout_id"], after)
                actual = client.get(row["workout_id"])
                if not saved_workout_matches(after, actual):
                    raise Conflict(
                        "Garmin accepted the request but read-back did not match. Check Garmin before trying again."
                    )
                db.execute(
                    "UPDATE updates SET status='done',created=? WHERE id=?",
                    (time.time(), token),
                )
                db.commit()
                return {
                    "ok": True,
                    "workoutId": row["workout_id"],
                    "updatedFields": len(json.loads(row["preview_json"])["changes"]),
                }
            finally:
                db.close()
