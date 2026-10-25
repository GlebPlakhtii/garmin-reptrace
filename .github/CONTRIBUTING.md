# Contributing to Garmin RepTrace

Garmin RepTrace is a Python 3.13 application with native JavaScript modules. Read
[the architecture](../docs/architecture.md) and [repository guidance](../AGENTS.md)
before changing storage, calculations, or integrations.

## Develop

```bash
uv sync --locked
uv run garmin-reptrace-demo
bash scripts/check.sh
```

The demo runs at http://127.0.0.1:3002 with synthetic records and rejects writes.
Node 22 or newer is recommended for the JavaScript tests. There is no frontend
bundler. For real persistence tests, follow [development](../docs/development.md).

Keep changes focused. Use descriptive names and small, testable functions;
prefer the existing standard-library and ES-module patterns to new dependencies.
Keep shared training rules canonical. Missing values are not zero, adjusted
volume is an estimate, and less assistance means more resistance.

Use synthetic fixtures. Never commit tokens, filled environment files, personal
training logs, database backups, or screenshots of a real account. Preserve
request identities, revisions, audit history, and recovery paths in storage changes.

Run the standard checks and describe what they verified in the pull request.
Calculation changes need independent expected values; persistence changes need
retry, conflict, readback, and interrupted-write coverage. For UI changes, inspect
desktop populated/empty/error states and keyboard behavior. Don't claim live
Garmin or Telegram validation based only on mocks.

## Issues and pull requests

Use this repository's Issues and Pull Requests. Include reproduction steps,
expected and actual behavior, and sanitized logs. Explain significant design
changes before investing in a large rewrite. Keep unrelated cleanup separate.

Original contributions are distributed under [AGPL-3.0-only](../LICENSE).
Keep the inherited [BSD notices](../LICENSES/BSD-3-Clause.txt) intact.
Retain upstream attribution when moving or adapting inherited code.
