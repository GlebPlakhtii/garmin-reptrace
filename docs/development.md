# Development and verification

Use Python **3.13**, locked dependencies, and Node's native test runner:

```bash
uv sync --locked
bash scripts/check.sh
uv build
uv run garmin-reptrace-demo
```

The web app uses native ES modules. No frontend bundler, linter or type-check
command is configured. `PYTHON_BIN` overrides the check script's default
`.venv/bin/python`. Package wheels must include `web/static/` and
`exports/templates/`, not just Python modules.

## Isolated persistence checks

Use a disposable development Influx instance, never the production database:

```bash
docker run -d --name garmin-reptrace-test-influx -p 127.0.0.1:18087:8086 influxdb:1.11
```

After Influx is ready:

```bash
test_state=$(mktemp -d)
INFLUXDB_HOST=127.0.0.1 INFLUXDB_PORT=18087 \
  WEB_STATE_PATH="$test_state/state.sqlite" \
  GARMIN_WORKOUT_STATE_PATH="$test_state/garmin.sqlite" \
  PYTHONPATH=src .venv/bin/python tests/integration/web_storage.py
```

The integration script creates and drops its own uniquely named test database.
It covers real persistence behavior; mocked tests do not replace that check.
Remove only the disposable container when finished:

```bash
docker rm -f garmin-reptrace-test-influx
```

For a writable development web server, set an isolated `INFLUXDB_DATABASE`,
explicit database host/port, temporary SQLite paths, `USER_TIMEZONE`,
`WEB_HOST=127.0.0.1`, and an unused `WEB_PORT` before running `uv run garmin-reptrace`.
Do not run `garmin-reptrace-sync` as a smoke check: it contacts Garmin and writes records.

## UI and documentation

Use `garmin-reptrace-demo` for synthetic desktop screenshots and `--empty` for empty
states. Check relevant keyboard controls and navigation/reload behavior. Save
screenshots in `docs/media/`; never capture a real account for public documentation.
The read-only demo intentionally rejects saves and external Garmin actions.

For production code changes, inspect the smallest meaningful diff, run the
standard checks, and verify build/runtime behavior. Distinguish mocked integration
checks from live external-service validation in release notes.

Python formatting for this preparation used `uvx ruff@0.14.1 format src tests scripts`.
This is an optional formatter command, not an additional build or test dependency.

## Running a focused group

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests/unit/training -t .
node --test tests/frontend/test_web_model.mjs
```

Unit tests are grouped by feature under `tests/unit/`. Cross-feature fixtures use
explicit `tests.unit.…` imports. Integration tests are outside unittest discovery
and must be invoked with an explicitly configured development database.
