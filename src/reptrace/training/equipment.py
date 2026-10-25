"""Validated equipment inventories, expressed in the same kg units as logged sets."""

import math


def validate_equipment(value):
    if not isinstance(value, dict):
        raise ValueError("Invalid equipment configuration")
    profiles = value.get("profiles", {})
    assignments = value.get("assignments", {})
    if not isinstance(profiles, dict) or len(profiles) > 100:
        raise ValueError("Use at most 100 equipment profiles")
    if not isinstance(assignments, dict) or len(assignments) > 1000:
        raise ValueError("Invalid exercise assignments")
    checked = {}
    for identity, profile in profiles.items():
        if not isinstance(identity, str) or not identity or len(identity) > 80:
            raise ValueError("Invalid equipment identity")
        if not isinstance(profile, dict):
            raise ValueError("Invalid equipment profile")
        name = profile.get("name")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
            raise ValueError("Equipment name must contain 1–120 characters")
        loads = profile.get("loads")
        if not isinstance(loads, list) or not 1 <= len(loads) <= 500:
            raise ValueError("Each profile needs 1–500 available loads")
        if any(
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            or not 0 <= v <= 2000
            for v in loads
        ):
            raise ValueError("Available loads must be numbers between 0 and 2000 kg")
        checked[identity] = {"name": name.strip(), "loads": sorted(set(loads))}
    for exercise, identity in assignments.items():
        if not isinstance(exercise, str) or not exercise.strip() or len(exercise) > 120:
            raise ValueError("Invalid exercise name")
        if not isinstance(identity, str) or identity not in checked:
            raise ValueError("Assigned equipment profile does not exist")
    return {"profiles": checked, "assignments": dict(assignments)}
