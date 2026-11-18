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
The same disposable Influx host and port support `tests/integration/coherent_snapshots.py`, `tests/integration/garmin_coordination.py` and `tests/integration/manual_import.py`. The last script checks conflicting date matches, an interrupted reviewed import, partial-session filtering, repeatable recovery and the archived originals.
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

## Telegram dashboard calculations

The complete workout PNG is rendered by `reports/workout_sheet.py`, using the
canonical adjusted-volume adapter. It includes unidentified exercises and every
recorded set. Synthetic tests cover complete long sheets, missing values,
owner-only delivery and PNG fallback.

Legacy workout widgets use `telegram/workout_widget.html` and a private snapshot store.
The HTML must stay under Telegram's 32768-byte raw and 4096-byte zlib limits;
each private state page must stay under 1024 UTF-8 bytes. Synthetic tests cover
authorization, pagination, missing values, restart recovery, client errors and
query handling while the coach worker is busy. Browser previews can check layout
with a stub `TelegramWidget`, but do not validate Telegram's native renderer or
prove live Bot API delivery.

Install Node.js 22+ when running the bot outside Docker. Its dashboard tools
execute the existing browser calculation module through a fixed stdin/stdout
adapter; there is still no frontend build step. Docker includes the Node binary.
See [Telegram tools](telegram-tools.md) for supported reads, previews and exports.

After-workout reports also require Node.js 22+: `reports/volume.mjs` calls the
same adjusted-volume calculation as the dashboard. Session totals, historical
comparisons, charts and AI facts use those estimates with the saved volume
settings and dated bodyweight. Weekly and monthly reports retain recorded volume.

Run the separate-process Garmin/collector checks with an isolated development
InfluxDB and temporary state paths:

```bash
run_state=$(mktemp -d)
INFLUXDB_HOST=127.0.0.1 INFLUXDB_PORT=18087 \
  WEB_STATE_PATH="$run_state/state.sqlite" \
  GARMIN_WORKOUT_STATE_PATH="$run_state/garmin.sqlite" \
  PYTHONPATH=src:. .venv/bin/python tests/integration/garmin_coordination.py
```

It creates/drops a unique database and exercises actual Influx writes with
synthetic Garmin responses, a separate collector process, stale batches,
unresolved-operation protection, local crash recovery and reviewed reversal.
It does not call Garmin or prove watch delivery.

The same isolated endpoint and temporary state environment can run
`tests/integration/coherent_snapshots.py`. It pauses a separate writer between
set and workout-summary changes, checks bounded busy responses and preservation
of the previous cache, and verifies consistent refresh/export results afterward.

Exercise definitions live in `src/reptrace/training/exercise_catalog.json`.
Keep changes there; Python compatibility imports and native JavaScript JSON
modules consume it directly. The catalog parity test checks both runtimes. Include
the JSON resource and `web/static/recovery.mjs` when verifying wheel contents.

Operation recovery is under **More → Operation recovery** and linked from
**Garmin workouts**. Inspect its empty, pending, completed and unavailable states,
including with Influx unavailable. Status reads are local and work in the demo;
the demo still rejects all continuation actions. The demo also isolates its
operation journal and shared-lock path. Test continuation only with synthetic
adapters and temporary storage unless a live external action is explicitly authorized.


## Running detail and Telegram reports

`training/running_metrics.json` owns summary labels, units and conversions for the
web and Telegram reports. `training/running.py` normalizes the read-only Garmin
activity/detail/split/zone responses. Descriptor factors are metadata, not extra
multipliers on returned sample values. Native running cadence and double cadence
are distinguished; null chart samples remain gaps. Synthetic tests cover these
units, treadmill calibration, paired pace totals, comparisons and safe CSV output.

`garmin/running.py` stores only normalized display data in `RUNNING_STATE_PATH`
(default: `running.sqlite` beside `WEB_STATE_PATH`). This is a disposable imported
cache, not an activity editor. SQLite transactions preserve previous detail on
interruption; partial and failed Garmin refreshes retain prior usable sections.
Tests use temporary cache files and synthetic clients, including restart, retry,
rollback, origin/membership validation and owner-only Telegram delivery. The demo
uses `web/running_demo.py` and makes no Garmin requests, even when importing detail.

Check the Running overview, detailed charts, alternate metric/axis controls,
keyboard sample slider, type/search/date filters, comparison, empty states and
failed-detail refresh with prior charts retained. Run links are real only for
numeric Garmin IDs. Telegram `/run` reports are standalone HTML; test attachment
retry without resending the already-delivered summary. Do not send live test
messages to the owner unless asked.

## Shared exercise loads

The four named next-session plans share each repeated exercise's load proposal
from its latest performance across the routines. Rep targets and set counts stay
specific to each routine; moving to a heavier shared load caps reps at that
routine's lower target. Uniform loads can span different set counts. Unequal set
counts with multiple top/back-off loads require review instead of guessing the
mapping. Explicit single-session adaptations keep their original loads.

Verified one-time manual loads take precedence across routines and expire after
the next matching exercise performance in any named routine. Single-type Telegram
requests resolve all four plans before selecting the requested result. Tests cover
both source selection and this single-request behavior. Progression increments
and equipment restrictions remain exercise-wide; sharing does not invent smaller
increments or bypass the existing automatic-increase limit.
