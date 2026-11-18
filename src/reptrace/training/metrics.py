"""Missing-aware numeric primitives shared by training, nutrition and reports."""

import math
import re

from reptrace.training.catalog import BODYWEIGHT_CATEGORIES, DEFAULT_VOLUME_PROFILES


def known(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def total(values):
    values = [v for v in values if known(v)]
    return sum(values) if values else None


def average(values):
    values = [v for v in values if known(v)]
    return {
        "value": round(sum(values) / len(values), 2) if values else None,
        "days": len(values),
    }


def is_assisted(exercise, settings):
    configured = settings.get("exercises", {}).get(exercise, {}).get("assistance")
    if isinstance(configured, bool):
        return configured
    return bool(re.search(r"\bassisted\b|\bassistance\b", exercise, re.I))


def estimated_max_kg(weight, reps, exercise, category):
    """Epley estimate in the recorded load convention for one identified lift."""
    if not known(weight) or weight <= 0 or not known(reps) or not 1 <= reps <= 10 or reps != int(reps):
        return None
    if category in BODYWEIGHT_CATEGORIES or is_assisted(exercise, {}):
        return None
    if category in (None, "", "MANUAL", "UNKNOWN"):
        # A first manual workout has no Garmin code. Only a reviewed, externally
        # loaded movement provides enough context to interpret its recorded kg.
        profile = DEFAULT_VOLUME_PROFILES.get(exercise)
        if not profile or profile.get("bodyweight") != 0 or profile.get("assistance"):
            return None
    return weight if reps == 1 else weight * (1 + reps / 30)
