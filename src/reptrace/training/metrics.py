"""Missing-aware numeric primitives shared by training, nutrition and reports."""

import math


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
