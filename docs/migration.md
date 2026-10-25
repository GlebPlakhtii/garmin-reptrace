# From Form to Garmin RepTrace

Garmin RepTrace changes the product and Python package identity, not the stored training
schema. Garmin RepTrace features and Garmin/Telegram integrations remain. The supported primary install is the root Docker Compose stack.

| Before | Now |
| --- | --- |
| `src/garmin_grafana/` | `src/reptrace/` |
| Collector-default image | Web-default Garmin RepTrace image |
| Script-path commands | `garmin-reptrace`, `garmin-reptrace-sync`, `garmin-reptrace-telegram`, etc. |
| Collector launched by default | Optional `garmin` profile |
| Telegram launched by default | Optional `telegram` profile |

## Keep your data attached

**Do not run `docker compose down -v`.** Back up first. Keep the existing Compose
project name when moving/renaming the checkout. Named volumes are project-scoped:
using a new project name can start a new empty volume even when the service keys
are identical. Find your current project and volume identities with `docker compose ls`
and the containers' Compose labels before migrating.

The service keys `strength-web`, `garmin-fetch-data`, `telegram-bot` and storage
keys `strength_web_data`, `telegram_bot_data`, `influxdb_data` remain
for compatibility. `/var/lib/form` and `/var/lib/form-bot` also remain. Existing
SQLite files, archives, revisions and tokens are reused. Browser preference/storage
keys are retained so the rename does not discard drafts or appearance choices.

If you used the old default Europe/Kyiv timezone, explicitly set
`USER_TIMEZONE=Europe/Kyiv` and `REPORT_TIMEZONE=Europe/Kyiv` in `.env`. New Compose
installs default to UTC. Preserve any existing bind address and allowed hosts.

With the **same project name and volumes**, build and recreate the affected services:

```bash
docker compose build strength-web
docker compose up -d --no-deps strength-web
docker compose --profile garmin up -d --no-deps garmin-fetch-data
# Only if you already use the bot:
docker compose --profile telegram up -d --no-deps telegram-bot
```

No database migration or Garmin re-import is required for the rename. Check health,
existing dates/workouts, saved settings and served branding. Keep the preceding
image and configuration until verified. Custom scripts importing `garmin_grafana`
must switch to `garmin-reptrace`; no legacy Python package alias is shipped.

Fixed container names were removed from the new configuration to allow separate
installations. Use `docker compose exec strength-web …` instead of hard-coding an
old container name. The root Compose stack is the supported deployment path.

## Private manual-import review rules

Record-specific legacy TSV corrections have moved out of public source into a
private JSON review profile. The local migration preserves the existing rules at
`.data/manual-import-review.json` (excluded from Git, images and publication).
When re-importing that reviewed log, pass it explicitly:

```bash
uv run garmin-reptrace-import /path/to/private-log.tsv \
  --review-profile .data/manual-import-review.json
```

This is a dry run; add `--write` only after reviewing it and configuring the intended
database. For a container, mount both the TSV and review profile read-only and pass
their container paths. Existing imported records and registry markers do not change.
Without a profile, extra values are rejected rather than silently corrected.

## Internal package organization

CLI names and storage locations are unchanged by the package refactor. Custom
Python imports must use the feature packages, for example `reptrace.web.server`,
`reptrace.storage.state`, `reptrace.garmin.workouts` and
`reptrace.training.planning`. See the architecture source map. Direct execution
of nested Python files is replaced by installed commands or `python -m`.

## Garmin RepTrace name

The application and distribution are named **Garmin RepTrace** / `garmin-reptrace`.
New installations use `garmin-reptrace`, `garmin-reptrace-demo`,
`garmin-reptrace-sync`, `garmin-reptrace-telegram`, `garmin-reptrace-backfill`, and
`garmin-reptrace-import`. The previous `reptrace` commands remain aliases.
The Python import namespace remains `reptrace`; no storage, browser-preference,
Compose volume, or database identities change with this branding update.
