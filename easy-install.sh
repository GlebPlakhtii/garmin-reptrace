#!/usr/bin/env bash
# Local checkout only: never downloads or executes an upstream installer.
set -euo pipefail
cd "$(dirname "$0")"
command -v docker >/dev/null || { echo "Install Docker Engine and Docker Compose first." >&2; exit 1; }
docker compose version >/dev/null
if [[ ! -f .env ]]; then cp .env.example .env; fi
mkdir -p garminconnect-tokens
if [[ ! -w garminconnect-tokens ]]; then
  echo "Token directory needs to be writable by container UID 1000. See README.md." >&2
  exit 1
fi
docker compose up -d --build influxdb strength-web
echo "Garmin RepTrace: http://localhost:3001 — see README.md to enable Garmin sync."
