"""Export an allowlisted public source tree without private runtime data/history."""

import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "README.md",
    "LICENSE",
    "NOTICE.md",
    "pyproject.toml",
    "uv.lock",
    "Dockerfile",
    "docker-compose.yml",
    ".dockerignore",
    ".gitignore",
    ".env.example",
    ".python-version",
    "easy-install.sh",
)
DIRECTORIES = (
    "LICENSES",
    "src",
    "tests",
    "scripts",
    ".github",
)
DOCS = (
    "architecture.md",
    "configuration.md",
    "development.md",
    "migration.md",
    "operations.md",
    "publication.md",
    "showcase.md",
    "user-guide.md",
    "equipment-and-garmin.md",
    "exercise-volume-factors.md",
    "weekly-muscle-map.md",
)
IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "*.sqlite*", "*.db*", ".env", "*.egg-info"
)


def export(destination):
    destination = Path(destination).resolve()
    if destination == ROOT or ROOT in destination.parents:
        raise ValueError("Choose a destination outside the working checkout")
    destination.mkdir(parents=True, exist_ok=False)
    for name in FILES:
        shutil.copy2(ROOT / name, destination / name)
    for name in DIRECTORIES:
        shutil.copytree(ROOT / name, destination / name, ignore=IGNORE)
    (destination / "docs").mkdir()
    for name in DOCS:
        shutil.copy2(ROOT / "docs" / name, destination / "docs" / name)
    shutil.copytree(ROOT / "docs/media", destination / "docs/media", ignore=IGNORE)
    # Public contribution guidance, without the local machine/deployment journal.
    (destination / "AGENTS.md").write_text(
        "# Repository guidance\n\nRead `.github/CONTRIBUTING.md` and `docs/development.md`.\n"
        "Preserve local changes and private data. Run `bash scripts/check.sh`.\n"
        "Use synthetic records and isolated development storage for tests.\n"
        "Never publish, send external actions, or deploy without user authorization.\n",
        encoding="utf-8",
    )
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(f"Exported source for review: {export(args.destination)}")


if __name__ == "__main__":
    main()
