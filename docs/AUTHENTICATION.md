# M02 authentication — development and verification

This is the M02 auth-only workflow. Projects, orders, files, quotations, payments,
inventory and production are not implemented. Keep all live gates off. Read
[SECURITY.md](SECURITY.md) and [ADR 0002](adr/0002-telegram-authentication.md).

## API and trust boundaries

FastAPI owns identity. React sends the **exact raw** `Telegram.WebApp.initData`
as `{"init_data":"..."}` to `POST /api/v1/auth/telegram`. The backend verifies
Telegram's bot-token HMAC-SHA256 protocol, decoded-field uniqueness, strict
encoding/JSON and timestamps before any identity or session is created.
Only `hash` is excluded from the sorted data-check-string; Telegram's optional
`signature` field participates in bot-token HMAC mode. This is separate from the
third-party Ed25519 verification protocol. Aiogram's maintained reference
signature checker independently agrees with the synthetic test vectors.

| Endpoint | Behavior |
|---|---|
| `POST /api/v1/auth/telegram` | Signed raw launch -> user/session; JSON and exact configured Origin required. Extra client role fields rejected. |
| `GET /api/v1/auth/me` | Current user, role/capabilities and session-bound CSRF token; 401 without a valid cookie. |
| `GET /api/v1/auth/csrf` | Current session's CSRF token; no public token issuance. |
| `POST /api/v1/auth/logout` | Exact Origin + session CSRF; revokes DB session and clears cookie, 204. |
| `GET /api/v1/owner/auth-check` | Harmless Owner-only proof endpoint: 401 anonymous, 403 Customer, 200 configured Owner. |
| `GET /api/v1/auth/users/{uuid}` | Auth fixture returns only the caller's user; other IDs return 404, including for Owner. |
| `GET /api/v1/health` | Public liveness only; startup checks PostgreSQL connectivity. |

No mock-auth endpoint exists, including in development. A development frontend
mock is a presentation-only preview with **no server user, cookie or privilege**.
Production excludes that adapter even if its frontend flag was accidentally on.

Sessions use 32 random bytes, with only SHA-256 token hashes persisted. The
`__Host-3dps_session` cookie is always Secure, HttpOnly, SameSite=Lax, Path=/,
without Domain. CSRF tokens are HMAC-derived per session and returned only to
the authenticated same-origin app. They remain in React memory. Sessions have a
fixed one-hour default expiry; logout and administrative DB revocation apply
server-side. No long-lived browser storage or role headers are used.

Launch proof defaults: maximum age 300 seconds, future skew at most 30 seconds.
A normalized digest of a used signed launch proof is unique in the session
table, so encoding/order changes and logout do not permit reuse. React restores
the cookie first and submits a launch once, including under StrictMode. After
logout or rejected proof, **close and reopen Telegram** for fresh launch data;
there is no automatic authentication retry loop.

The M02 final review corrected frontend recovery: a connection retry first
checks the real cookie, then may submit a current proof that was never attempted.
If a retained Telegram WebView has received genuinely fresh raw launch data,
“Check sign-in again” can use that new proof after logout/expiry/rejection.
Previously attempted or logged-out proofs are not submitted again. A committed
login whose cookie was lost still requires a fresh launch if cookie restoration
fails. See [the final acceptance review](M02_FINAL_ACCEPTANCE_REVIEW.md) for the
new tests and actual results.

## Trusted Owner provisioning

Set `OWNER_TELEGRAM_IDS` only through the server's trusted secret/configuration
process to the intended test account's verified numeric Telegram ID. Empty means
**no Owner**. No first-user grant, public registration option, frontend-supplied
role or browser deep-link flag can grant privileges. The allowlist is checked on
each authenticated request; a DB role edit alone cannot elevate a Customer.

Changing the allowlist requires a trusted configuration change and process
restart, then verification with the target test accounts. Removal demotes an
existing session on its next request. Explicit user deactivation and session
`revoked_at` also block access. No public role-management endpoint is supplied.

## Run the backend locally

Required: Python 3.12 (tested 3.12.14), uv (tested 0.13.5), PostgreSQL 16
(tested 16.15), Node/npm from the frontend runbook. Never use a production DB or
bot for this workflow. There is one Alembic chain under `backend/alembic/`.

```sh
cd backend
UV_CACHE_DIR=/tmp/3dps-uv-cache uv sync --frozen
```

Copy root `.env.example` to ignored `.env.local` and securely supply:

- `DATABASE_URL`: `postgresql+asyncpg` DSN for the private development DB.
- `BOT_TOKEN`: **actual dedicated test bot token**, server/bot only.
- `SESSION_SECRET`: cryptographically random, at least 32 characters.
- `PUBLIC_BASE_URL`: exact frontend origin, with scheme/host/port, no path/query.
- `OWNER_TELEGRAM_IDS`: optional trusted test Owner allowlist.

The backend uses the actual bot token locally to compute HMAC. A proxy-held
placeholder that is substituted only in outbound HTTPS cannot perform this
local verification. Use the machine/container's secure runtime secret facility
or an ignored local env file; never enter a token in chat or a `VITE_*` value.

From `backend/`, load the ignored env file without printing its values:

```sh
.venv/bin/python -m dotenv -f ../.env.local run -- .venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:create_app --factory --env-file ../.env.local --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
```

Migrations create only users, hashed/revocable sessions and auth rate counters,
plus Alembic metadata. They never run automatically on API startup. Review SQL
before applying to any retained data. Initial downgrade removes auth data and
is tested **only in a disposable database**; it is not an operational rollback
instruction for retained data. Use reviewed backups/recovery for retained data.

From `miniapp/`, run `npm ci`, then `VITE_TELEGRAM_MOCK=false npm run dev`.
Browser requests use relative `/api/v1` through the existing Vite proxy. For
loopback-only browser development `PUBLIC_BASE_URL=http://127.0.0.1:5173` is
allowed in development/test; cookies remain Secure. Use HTTPS for reliable
end-to-end and all real Telegram testing. No insecure-cookie escape exists.

## Docker development

Root `compose.yaml` supplies a private PostgreSQL service and a non-root API
image. API host binding is loopback-only; PostgreSQL publishes no host port.
Bot long polling is optional under profile `bot`. This is development Compose,
not production hosting or M15 deployment.

For Compose, root `.env.local` must additionally contain `POSTGRES_PASSWORD`;
Compose constructs its internal development DSN. Use URL-safe password
characters, or URL-encode them consistently when providing a custom DSN. Check
config without printing resolved secrets:

```sh
docker compose --env-file .env.local config --quiet
docker compose --env-file .env.local build api
docker compose --env-file .env.local up -d db
docker compose --env-file .env.local run --rm api alembic upgrade head
docker compose --env-file .env.local up -d api
```

Run Vite on the host with its default proxy target `http://127.0.0.1:8000`.
For a Vite process inside a future Compose frontend, use the internal API
origin instead; no such frontend container is introduced by M02.

In managed Cloud builds, mount the configured CA as a **build secret** when the
proxy intercepts TLS. The tested image build from repository root was:

```sh
docker --host=unix:///var/run/docker.sock build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -f backend/Dockerfile -t 3dps-api:m02-test .
```

Use the local daemon and inherited proxy/CA settings. Do not disable TLS or hash
verification. `backend/requirements.txt` is exported with hashes from `uv.lock`;
the image installs using `pip --require-hashes` and runs as UID 10001. Images
are pinned by digest. No secrets or session CA are copied into image layers.

## Automated tests in Codex Cloud or local development

No real bot is needed: fixtures create signed synthetic launch data outside the
browser and use only disposable test DBs. Keep the existing isolated checkout;
no Git worktree or permanent server is needed. Live processes do not survive
environment publication/restoration; restart needed test services each task.
In a restricted Cloud workspace use writable caches, for example
`UV_CACHE_DIR=/tmp/3dps-uv-cache` and `npm ci --cache /tmp/3dps-npm-cache`.
The Docker test helper defaults its uv cache to a temporary writable location.

From repository root, the tested helper creates its **own** Docker PostgreSQL
container with an automatically assigned loopback port, runs frozen backend
installation/tests and removes only that container on exit:

```sh
backend/scripts/test-postgres.sh
```

Alternatively, set `TEST_DATABASE_URL` securely to an existing disposable
`postgresql+asyncpg` DB, then run from `backend/`:

```sh
.venv/bin/ruff check app alembic tests scripts ../telegram_bot
.venv/bin/mypy app scripts ../telegram_bot
.venv/bin/pytest -q
```

The pytest guard requires loopback host and a `3dps_test*` database; it refuses
missing configuration or SQLite instead of silently skipping. The test role
needs CREATEDB because migration tests create/drop their own unique disposable
databases. Test DB cleanup truncates only the explicitly guarded test DB.
Never point these fixtures at retained development/customer data.

Frontend tests from `miniapp/`:

```sh
npm run check
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e
```

Omit the explicit executable setting when Playwright's installed Chromium is
available. The UI browser suite uses intentional API fixtures for deterministic
screen states. A separate real-stack check has **no API response mocks**:

1. Create a separate disposable DB named `3dps_test_browser` (or supported
   suffixed variant), migrate it with `DATABASE_URL` and Alembic as above.
2. Export `TEST_BROWSER_DATABASE_URL` to that loopback DB, never the main test DB.
3. From `miniapp/`, run:

```sh
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:auth-integration
```

This builds production React, starts actual FastAPI and an ephemeral loopback
HTTPS gateway, and verifies five Customer/Owner/cookie/CSRF/logout/forgery flows
against PostgreSQL. It needs free local ports 18002/18443 and OpenSSL. It creates
synthetic credentials internally, intercepts only Telegram's presentation SDK,
and tears down processes/certificate files. Its self-signed certificate is
accepted only in its ephemeral test browser contexts; no package verification
is weakened. This test is not real Telegram client evidence.

## OpenAPI-generated frontend types

From `backend/`: `PYTHONPATH=. .venv/bin/python scripts/export_openapi.py` exports
`backend/openapi.json` with synthetic configuration and no network/DB connection.
From `tools/api-types/`: run `npm ci` and `npm run generate` to regenerate
`miniapp/src/lib/api/schema.d.ts`. Frontend shortcut: `npm run generate:api`.

The locked generator needs TypeScript 5; it is deliberately isolated from the
working TypeScript 6 frontend. Regeneration must produce no unexpected diff.
No peer-dependency override or copied handwritten domain DTO is used.

## Real Telegram verification — PENDING, required externally

No real bot token, Owner ID, stable HTTPS endpoint or physical Telegram device
was configured in this Cloud run. Complete this checklist using test accounts
and record actual platform/version/date/result evidence; **G1 remains PENDING**.

1. Create/configure a dedicated test bot in BotFather. Securely provision its
   token and the intended test Owner ID on the backend. Keep all live flags off.
2. Expose the frontend and `/api/v1` under **one valid HTTPS origin** using a
   controlled staging/test gateway or authorized development tunnel to Vite.
   Set `PUBLIC_BASE_URL` to that exact origin. Keep DB/API internals private;
   do not connect any payment provider, production DB or physical printer.
3. In BotFather set the Menu/Main Mini App URL to the same HTTPS `/app` URL.
   No bot username or URL was invented in source. Either configure the menu
   manually, or start the included Aiogram adapter from repository root:
   `PYTHONPATH=backend backend/.venv/bin/python -m dotenv -f .env.local run -- backend/.venv/bin/python -m telegram_bot`.
   Compose alternative: `docker compose --env-file .env.local --profile bot up -d bot`.
   This adapter sets a launch menu and answers private `/start` with a Web App
   button; it is not needed for offline HMAC tests and was not connected to a
   real Telegram account during this task.
4. Disable frontend mock mode. Launch via the actual bot on Telegram Android,
   iOS and Desktop. Confirm signed raw launch verification and secure cookie
   roundtrip, refresh/reopen restoration, theme/safe-area/back-button/keyboard
   behavior, and no signed data/tokens in console/server logs or storage.
5. With two separate test accounts, verify Customer API denial at Owner paths,
   the provisioned Owner's access, and denial for another account even when it
   alters URL/role hints. Confirm logout invalidates the cookie server-side;
   closing and relaunching yields new proof, not an automatic replay loop.
6. Check configured expiry/future rejection and throttling on test fixtures;
   verify cookie persistence/SameSite behavior in each real client. If third-
   party/embedded context policy blocks cookies, record evidence and review the
   deployment/session policy explicitly; do not weaken Secure/CSRF/CORS silently.

## Operational limits and remaining risks

Auth rate counters live in PostgreSQL and include failed attempts. Defaults are
10 login requests per 60 seconds per transport peer and 60 session requests per
window. Forwarded headers are not trusted; behind Vite/gateway many users can
share a bucket. Review trusted proxy/IP and edge request timeout/rate settings
before wider exposure; do not accept arbitrary `X-Forwarded-For`. A DB outage
fails auth closed. The gateway must also bound slow/oversize traffic; M02 bounds
login bodies but is not the M14/M15 deployment-hardening audit.

Session/proof records are retained; no automatic deletion job is implemented.
Any later retention job must preserve replay protection for at least the full
launch freshness window and retain required security evidence. Account/session
revocation and secret rotation require a trusted server operation; no customer
or owner public administrative mutation was added in this milestone.

Do not prune solely on session expiry: the configured session lifetime may be
shorter than the permitted proof-freshness window. Deleting that session's
unique proof record too early would allow a logged-out/expired launch to replay.
Retention policy and any separate proof tombstones need explicit review first.
