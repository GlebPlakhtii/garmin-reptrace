"""Exercise definitions shared by Python and the native browser/Node model.

The JSON resource is the only editable catalog. Aliases apply when normalizing
incoming records; loading the catalog never renames saved history or overrides.
"""

from importlib.resources import files
import json


CATALOG = json.loads(
    files(__package__).joinpath("exercise_catalog.json").read_text(encoding="utf-8")
)
EXERCISES = CATALOG["exercises"]
EXERCISE_NAME_ALIASES = CATALOG["aliases"]
BODYWEIGHT_CATEGORIES = set(CATALOG["bodyweightCategories"])
MUSCLE_GROUPS = CATALOG["muscleGroups"]
DEFAULT_MUSCLES = {
    name: entry["muscle"] for name, entry in EXERCISES.items() if "muscle" in entry
}
MUSCLE_INVOLVEMENT = {
    name: entry["roles"] for name, entry in EXERCISES.items() if "roles" in entry
}
DEFAULT_VOLUME_PROFILES = {
    name: entry["volume"] for name, entry in EXERCISES.items() if "volume" in entry
}


def recorded_exercise_mappings(rows):
    """Infer a mapping for new sets only when recorded categories agree."""
    mappings = {}
    for row in rows:
        name = row.get("Exercise")
        if not name or not row.get("ExerciseCategory") or not row.get("last"):
            continue
        mapping = (row["ExerciseCategory"], row["last"])
        if name in mappings and mappings[name] != mapping:
            mappings[name] = None
        else:
            mappings[name] = mapping
    return {name: mapping for name, mapping in mappings.items() if mapping is not None}
