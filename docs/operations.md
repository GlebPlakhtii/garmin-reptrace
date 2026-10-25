# Operations

## Health and troubleshooting

```bash
docker compose ps
curl --fail http://localhost:3001/api/health
docker compose logs --tail 50 strength-web
```

Health confirms the app can load data; it does not prove a complete Garmin sync.
Check the Garmin sync page for the distinction between a watch upload, a collector
poll and each metric's last sample. Inspect logs privately and redact credentials,
identifiers and training details before sharing them.

| Symptom | Check |
| --- | --- |
| Empty app after moving the checkout | Compose project name and original volume bindings |
| Garmin login expired | Re-run interactive collection authentication; inspect token-directory permissions |
| No strength sets | `activity` in `FETCH_SELECTION`, `FETCH_STRENGTH_SETS`, and whether old activities need backfill |
| Browser saves rejected | Correct host:port in `WEB_ALLOWED_HOSTS` and the actual origin; don't disable validation |
| Port unavailable | Existing service on 3001, or a configured bind IP no longer present |
| Old date on one recovery metric | Device/account support and sample age, not necessarily a broken collector |
| AI/Telegram unavailable | Owner pairing, token, enabled report flags, API access and configured models |
| Demo refuses to save | Expected: use a normal installation for writes |

## Consistent backups

For a backup spanning both databases, stop writers first. This is a planned
maintenance operation; the web app and bot are unavailable until restarted.
The collector, web, and bot should all be stopped, but leave InfluxDB running for
its portable backup. Use a private backup directory outside the public repository.

```bash
mkdir -p backups
chmod 700 backups
docker compose stop garmin-fetch-data telegram-bot strength-web
docker compose exec influxdb influxd backup -portable /tmp/garmin-reptrace-influx-backup
docker compose cp influxdb:/tmp/garmin-reptrace-influx-backup ./backups/influxdb
```

Use a fresh destination for every backup. Copy application files from the stopped
web container (the complete directory includes both SQLite databases, journals
and any auxiliary files):

```bash
docker compose cp strength-web:/var/lib/form ./backups/app-state
# If you use the bot:
docker compose cp telegram-bot:/var/lib/form-bot ./backups/bot-state
cp -a garminconnect-tokens ./backups/garminconnect-tokens
```

Also retain the effective deployment configuration and `.env` privately. Restart
only the services you use:

```bash
docker compose up -d strength-web
docker compose --profile garmin up -d garmin-fetch-data
# If previously enabled:
docker compose --profile telegram up -d telegram-bot
```

Test restoration into an isolated installation before relying on a backup.
Restore the Influx portable backup using the matching InfluxDB version and restore
application/token directories with UID/GID 1000 ownership. Do not overwrite a live
database while writers run. A complete restore needs both the training measurements
and the corresponding SQLite revision/archive state.

## Update and rollback

Retain the current image with a dated local tag and keep the matching Compose
configuration before rebuilding:

```bash
docker image tag garmin-reptrace:local garmin-reptrace:rollback-YYYYMMDD
docker compose build strength-web
docker compose up -d --no-deps strength-web
```

Recreate collector/bot only when used and affected. Verify HTTP health, app assets,
and existing data. To roll back, tag the saved image back to `garmin-reptrace:local` and
recreate affected services with `--no-build`, using the matching saved configuration.
The first migration from an older image needs its old command paths as well.
Never delete named volumes as an update/rollback procedure.
