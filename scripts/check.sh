#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python_bin="${PYTHON_BIN:-.venv/bin/python}"
PYTHONPATH=src "$python_bin" -m unittest discover -s tests/unit -t .
node --test tests/frontend/*.mjs
git diff --check
