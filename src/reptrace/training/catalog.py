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
