# Codex Cloud setup and start instructions

The published environment already supplies the M07 dependency installation and
start instructions. Do not republish or replace settings to resume this branch.
The checked-in equivalent is `bash scripts/codex-cloud-install.sh`. It uses frozen
Python/npm locks, repository Node version, private temporary caches, and either
system Chromium or a locally installed Playwright Chromium. It preserves tracked
source changes, TLS verification, the inherited proxy and credentials. It does
not create a database, migrate data, seed commercial policies or start live services.

## Reusable start instructions

Read AGENTS.md and the selected milestone before editing. Inspect the branch,
working tree and existing implementation. Use the managed cloud runtime skill;
refresh environment readiness after a restored snapshot. Do not overwrite earlier
work or automatically publish environment settings.

Check Python 3.12.14, uv 0.13.5, Node 24.22.1, npm 11.9.0, backend/.venv,
miniapp/node_modules and tools/api-types/node_modules. Run the install script if
dependencies are missing. Use system Chromium with
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium`, or use the local browser
cache selected by the install script. No Telegram bot secret is needed to export
OpenAPI or run isolated tests with synthetic signing credentials.

Check Docker through the local Unix socket, clearing only endpoint/context/TLS
selectors as described by the cloud runtime skill. Keep Docker configuration,
registry credentials, inherited proxy and CA trust. For networked image builds,
pass `--secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt`. Never disable TLS.

Create a task-owned PostgreSQL 16 test container on a loopback port only. Use a
fresh database named `3dps_test_*`; backend fixtures refuse other targets. Point
`TEST_DATABASE_URL` at it using the `postgresql+asyncpg` driver. The fixtures migrate
their disposable database themselves. Never use production credentials or data.
See `backend/scripts/test-postgres.sh` for the standard container harness.
A browser database must instead use the `3dps_test_browser*` namespace and be
migrated to head before running the real-stack harness.

Build `worker/Dockerfile` and resolve its immutable image ID to
`M06_TEST_WORKER_IMAGE` for native parser/slicer tests. A missing sandbox must be
reported explicitly; never replace it with fabricated analysis. No physical
printer network or hardware is required or permitted. Aggregate cgroup resource
limits need separate verification on a supported target host.

Run relevant Python, database, contract and frontend checks. Start preview servers
only for tests or when requested. Keep production authentication, quotation,
payment and printer gates disabled. Do not commit, push, merge, publish or deploy
unless explicitly requested for this milestone. Stop at the milestone boundary.

## Checks

From `backend`: `uv run --frozen pytest -q`,
`uv run --frozen ruff check app alembic tests scripts ../telegram_bot ../worker`,
`uv run --frozen mypy app scripts ../telegram_bot ../worker`,
`DATABASE_URL="$TEST_DATABASE_URL" uv run --frozen alembic check`.
Export with `PYTHONPATH=.:.. uv run --frozen python scripts/export_openapi.py`.
From `tools/api-types`: `npm run generate`. Re-export and regenerate to check drift.
From `miniapp`: `npm run check`, `npm run test:e2e`,
`TEST_BROWSER_DATABASE_URL=... npm run test:auth-integration`.
All values in tests are synthetic. This document does not authorize production
schema changes or environment publication.

Restored Docker vfs layers intermittently exceeded the old 20-second container
creation budget. The controller allows 60 seconds to create a stopped container;
this does not execute the model. The existing 90-second execution wall, 85-second
sandbox alarm, process budgets, secret-free environment and network restrictions
remain unchanged. Registry test probes allow the same bounded cold-start time.

Security-probe tests allow 75 seconds for cold container materialization plus probe
execution. The CPU test still requires a real kernel kill (`worker_crashed`), not a
controller timeout. The tested kernel/process limits are unchanged.
