# M03 business foundation runbook

M03 adds authenticated simulation drafts, not customer intake or commercial
operations. See [ADR 0003](adr/0003-business-transaction-foundation.md) and
[the implementation report](M03_IMPLEMENTATION_REPORT.md). Preserve the M02
setup and security configuration in [AUTHENTICATION.md](AUTHENTICATION.md).

## Run and migrate

Use the existing Python 3.12.14/uv 0.13.5 environment and Node 24.22.1/npm 11.9.0.
No new dependency is required. Configure private test/development settings using
`.env.example`; keep all live flags false and development authentication false.
Bot token, session secret, Owner Telegram ID and database DSN remain server-only.

```sh
cd backend
uv sync --frozen
uv run --frozen alembic upgrade head
uv run --frozen alembic current
uv run --frozen alembic check
uv run --frozen uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

`DATABASE_URL` must identify the intended private development database. Review
migrations before applying them. Head is `0002_business_foundation`, extending
`0001_auth_foundation`. For existing M02 installations this adds five tables;
it does not rewrite authentication or delete sessions. Compose's existing API
image includes the new code and migration; use the existing documented Compose
build/migration process, then start API. There is no automatic startup migration.

In another terminal, run `cd miniapp && npm ci && npm run dev` with the existing
`/api` proxy. Real authentication requires the shared HTTPS origin configured as
`PUBLIC_BASE_URL` and a real test Telegram launch. The explicitly opted-in UI mock
remains disconnected: it cannot create authenticated drafts or choose server roles.

## Implemented API

All paths below begin `/api/v1`. Reads require an unexpired authenticated cookie
unless stated. Mutations require exact configured Origin, session-bound
`X-CSRF-Token`, JSON, and `Idempotency-Key` (8–128 ASCII letters/digits/`_`/`-`).
Command JSON buffering is bounded to 32 KiB. Input objects reject extra fields.

| Method/path | Behavior |
|---|---|
| `GET /health` | Public liveness only; no DB/credential details |
| `GET /ready` | Owner-only DB/schema-head check; keep internal at a deployed gateway |
| `POST /requests` | `{service_type, customer_notes?}` -> `{project, request}` (201) |
| `GET /projects` | Current actor's projects, bounded pagination |
| `GET /projects/{id}` | Own project, or Owner inspection |
| `GET /requests` | Current actor's requests, bounded pagination |
| `GET /requests/{id}` | Own request, or Owner inspection |
| `GET /owner/requests` | Owner-only paginated request list |
| `PATCH /requests/{id}` | `{expected_version, customer_notes}`; own draft only |
| `POST /requests/{id}/transitions` | `{expected_version, target, reason}`; cancellation only succeeds now |

Service types: `printing`, `custom_design`, `design_and_print`. The latter two
create a design stage only. Every project/request has `mode=simulation`.
Ownership, role, status and mode cannot be supplied on creation. The transition
input recognizes `submitted` to return the explicit unavailable-intake guard
(409); no successful submission route exists. All cancellation reasons need at
least three non-whitespace characters. Edits/cancellations return the updated
request and version. Exact retries return the original typed response, even if
the expected version has since advanced, after current authorization checks.

Use `?limit=20&offset=0`; limits are 1–100 and offsets 0–10000. Response:
`{items, next_offset}`. Error schema remains M02's
`{code, message, correlation_id}`. 401 expired/invalid session, 403 role/CSRF/Origin,
404 inaccessible/missing resource, 409 stale version/key mismatch/transition,
422 invalid input, 413 oversize body, 503 database/transaction failure. No SQL,
rejected notes, proof, token or cookie is echoed in errors.

## Tests and generated contracts

Use only disposable loopback PostgreSQL, with a database name starting
`3dps_test`. Tests require a role able to create uniquely named disposable
migration databases; they truncate only their guarded test database and drop
only databases created by their own fixture. Never set TEST_DATABASE_URL to
customer data. There is no SQLite fallback or silent DB-test skip.

```sh
cd backend
TEST_DATABASE_URL="$M03_TEST_DSN" uv run --frozen pytest -q
uv run --frozen ruff check app alembic tests scripts ../telegram_bot
uv run --frozen mypy app scripts ../telegram_bot
PYTHONPATH=. uv run --frozen python scripts/export_openapi.py
cd ../tools/api-types
npm ci
npm run generate
cd ../../miniapp
npm run check
npm run test:e2e
```

`M03_TEST_DSN` is a task-local variable pointing to the disposable database.
For Cloud with existing system Chromium, prefix browser commands with
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium`; otherwise install the
Playwright version with `npx playwright install chromium`.

For the actual React/HTTPS/FastAPI/PostgreSQL test, create and migrate a separate
loopback database named `3dps_test_browser` (or `3dps_test_browser_<suffix>`).
Then run:

```sh
TEST_BROWSER_DATABASE_URL="$M03_BROWSER_TEST_DSN" npm run test:auth-integration
```

That existing script now tests seven M02/M03 flows, preserves all original
security checks, and adds mobile draft creation/editing, cross-customer denial
and Owner cancellation. It signs synthetic credentials in Node, intercepts only
Telegram's presentation SDK, and starts its own temporary TLS gateway and API.
No `/api` response is mocked. For an already built and migrated **disposable**
application container on `127.0.0.1:18002`, set `TEST_CONTAINER_API=true`; the
harness uses that caller-owned API instead of spawning host Uvicorn. The fixed
loopback address cannot select an external API. The container must use only
synthetic fixture credentials matching the harness, exact origin
`https://127.0.0.1:18443`, Owner ID `111`, and a separate `3dps_test_browser_*`
database. This option exists only in the Node test harness and does not add an
application setting, dev-login endpoint or frontend bypass. The caller stops
its container after the test. Production-mode container verification includes
Owner readiness and private API interactive-docs rejection. See the CI workflow
for the complete disposable container invocation.

No `/api` response is mocked. It cleans up its API/gateway/certificate, leaves
test DB inspection to the caller, and writes synthetic-data screenshots under
ignored `miniapp/test-results/`. It is not a real Telegram or Caddy deployment test.

CI retains `.github/workflows/authentication.yml` and `frontend.yml`. The backend
workflow runs all auth/business/migration tests, Alembic metadata checks,
regeneration drift checks, application image build/start/migration and the
seven-flow real-stack script against both host Uvicorn and a production-mode
application container. Frontend workflow
runs the complete frontend checks and ten UI browser tests. Configuring these
checks does not prove that hosted GitHub Actions executed them.

## Required external verification

Use separate test bot, Owner and two Customer Telegram accounts, with all live
features disabled and no production data. Follow the HTTPS/BotFather/client
checklist in AUTHENTICATION.md on Android, iOS and Desktop. Then verify:

1. Customer opens project drafts, saves each service type, edits a draft, closes
   and reopens the Mini App, and sees persisted records. Combined project has
   only its design stage. No upload, submit, quote, payment or printer controls.
2. The second Customer cannot retrieve the first customer's project/request IDs
   or use `/owner/requests`, including direct API requests with its own session.
3. Only the server-provisioned Owner loads all drafts. Owner cannot edit another
   customer's notes; a reasoned cancellation becomes visible to the Customer
   after reopening/reloading the draft list.
4. Verify cookie, CSRF, exact Origin, logout and fresh-launch recovery through
   the intended HTTPS proxy, including each Telegram client's cookie behavior.
5. Inspect one audit and pending outbox record per committed mutation. No actual
   alert is delivered in M03. Record client versions and observed results.

These device/proxy checks and G1 acceptance remain external. Outbox delivery,
record retention/cleanup, least-privilege production DB roles, backups and live
release gates are not claimed complete. Stop after M03 review; M04 adds secure
file intake only after authorization to begin it.
