# Configuration

The root `.env.example` lists Compose-facing settings. Copy it to `.env`, keep it
private, and recreate affected services after changes. Compose's `.env` performs
interpolation: it does **not** automatically pass arbitrary variables to every container.
Add collector-specific options to its `environment` section or use `docker compose run -e`.

| Setting | Purpose |
| --- | --- |
| `USER_TIMEZONE` | IANA timezone for collection/display; Compose defaults to UTC |
| `WEB_BIND_IP` | Host interface for port 3001; defaults to 127.0.0.1 |
| `WEB_ALLOWED_HOSTS` | Additional allowed host:port values for a deliberate remote setup |
| `GARMINCONNECT_IS_CN` | Garmin China account selection |
| `TELEGRAM_BOT_TOKEN` | Dedicated bot token |
| `TELEGRAM_ALLOWED_USER_ID` | Private owner ID; blank enables secure pairing |
| `TELEGRAM_PAIRING_CODE` | Optional initial pairing secret; otherwise generated in private bot logs |
| `REPORT_TIMEZONE`, `WEEKLY_REPORT_TIME` | Report zone and local schedule time |
| `WEEKLY_REPORT_ENABLED` | Calculated Monday summary |
| `POST_WORKOUT_REPORT_ENABLED` | Report for newly detected eligible completed sessions |
| `MONTHLY_REPORT_ENABLED` | Monthly HTML review |
| `REPORT_SETTLE_SECONDS` | Wait for imported workout data to stabilize |
| `OPENAI_API_KEY` | Optional external AI service credential |
| `OPENAI_MODEL`, `OPENAI_CHAT_MODEL`, `OPENAI_FOOD_MODEL` | Model identifiers for the corresponding optional feature |
| `OPENAI_REASONING_EFFORT`, `OPENAI_CHAT_REASONING_EFFORT` | Requested reasoning settings |
| `FOOD_HAND_LENGTH_CM` | Optional scale reference when the full hand is visible in a food photo |

Model defaults reflect the existing application configuration, not a guarantee
of availability in every API account. Choose supported model identifiers for your
account. Core analytics and local next-session calculation work without them.

## Native runtime

Direct Python execution defaults to localhost; Docker sets `WEB_HOST=0.0.0.0`
inside its container and publishes only the configured host interface. Set explicit
`WEB_STATE_PATH` and `GARMIN_WORKOUT_STATE_PATH` to writable private files for native
runs. Defaults retain `/var/lib/form/` for installation compatibility.

Database settings are `INFLUXDB_HOST`, `INFLUXDB_PORT`, `INFLUXDB_DATABASE`,
`INFLUXDB_USERNAME`, `INFLUXDB_PASSWORD`, and `INFLUXDB_ENDPOINT_IS_HTTP`.
`TOKEN_DIR` controls stored Garmin tokens. The bot's API base is `FORM_API_URL`
(retained for compatibility); `TELEGRAM_STATE_PATH` controls its persistent file.

## Garmin collection

Useful collector options include `UPDATE_INTERVAL_SECONDS`, `FETCH_SELECTION`,
`FETCH_STRENGTH_SETS`, `KEEP_FIT_FILES`, `ALWAYS_PROCESS_FIT_FILES`,
`FORCE_REPROCESS_ACTIVITIES`, `AUTO_DATE_RANGE`, `MANUAL_START_DATE` and
`MANUAL_END_DATE`. The source remains the authority for their defaults.

The default selection includes activity, sleep, daily averages, body composition,
training status/readiness and additional Garmin health series. An explicit
`FETCH_SELECTION` replaces that list; include `activity` for strength sets and
`training_status,training_readiness` for those cards.

To fetch a limited historical range, first stop the scheduled collector to avoid
parallel writers, then run the collector with explicit overrides:

```bash
docker compose stop garmin-fetch-data
docker compose run --rm -e AUTO_DATE_RANGE=False \
  -e MANUAL_START_DATE=2026-01-01 -e MANUAL_END_DATE=2026-01-31 garmin-fetch-data
docker compose --profile garmin up -d garmin-fetch-data
```

This contacts Garmin and writes history. Respect rate limits and do not use
production collection as a web smoke test. Password prompting uses a hidden
terminal input; reusable tokens avoid storing a password in Compose.

## Pair Telegram securely

If no owner ID was configured, inspect the bot's local logs privately for its
`/start <pairing-code>` instruction and send it to your own bot in a private chat.
A bare `/start` does not claim the bot. Pairing persists in the bot state volume.
Never paste the pairing code, token, or unredacted logs into GitHub issues.

Review schedule flags before startup. Weekly summaries cover the previous
Monday–Sunday; after-workout reports wait for stable data and do not replay all
historical workouts. Monthly reports use the configured report timezone.
