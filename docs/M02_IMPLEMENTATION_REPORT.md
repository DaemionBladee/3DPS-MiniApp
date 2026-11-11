# M02 — Secure Telegram authentication

Date: 2026-11-11 (Asia/Rangoon). **M02 implemented; stop for review before M03.**
M01 was explicitly reviewed/accepted in the owner's M02 instruction. Automated
acceptance is verified; real Telegram device/G1 evidence remains **PENDING**.

## Changes and boundaries

Preserved the working React foundation, themes, layout, reusable states and
isolated development UI preview. Added a FastAPI modular-monolith foundation
and PostgreSQL authentication only. No working backend existed to remove.
No projects, business requests, outbox, quotations, orders, payments, inventory,
production or M03 migrations were added. All live gates stay off and unsupported
live/mock-auth configuration fails backend startup.

Implemented endpoints: signed raw `POST /api/v1/auth/telegram`, session
`GET /auth/me`, `GET /auth/csrf`, CSRF-protected `POST /auth/logout`, harmless
Owner-only `GET /owner/auth-check`, self-only `GET /auth/users/{uuid}` and public
`GET /health`, all under `/api/v1`. See the actual exported OpenAPI and
[authentication runbook](AUTHENTICATION.md); remaining business API plans remain
unimplemented.

Security behavior:

- Official bot-token HMAC-SHA256, constant-time MAC comparison, strict decoded
  field uniqueness/percent/UTF-8/JSON/user-ID validation, 16 KiB proof and 32 KiB
  login-body bounds, 300-second age and 30-second future tolerance defaults.
- Two roles only, trusted server allowlist provisioning, empty allowlist grants
  no Owner. No first-user promotion, frontend role authority or mock-login API.
  Each request resolves effective role from trusted configuration.
- Cryptographically random server sessions, hashed tokens at rest, fixed expiry,
  revocation/logout and prior-cookie rotation. Immutable normalized launch-proof
  uniqueness prevents replay, including alternate URL encodings and after logout.
- Always Secure/HttpOnly/SameSite=Lax `__Host-` cookie with root path/no Domain;
  exact Origin check on mutations/login and session-bound CSRF on logout. No
  CORS credential grant, localStorage session or browser bot token.
- Failure-inclusive, atomic PostgreSQL rate counters shared across app instances;
  authenticated reads are bounded too. Proxy headers are not trusted by app or
  documented Uvicorn launch. Error/input/SQL/log handling omits credential values.
- React restores real cookies before sending a raw launch once; StrictMode
  does not replay proofs. Server roles gate navigation; session loss/logout
  clears private query state. Development mocks have no server user/session;
  production excludes the adapter and rejects role/storage/URL hints.

## Files changed

New backend:

```text
backend/
  .python-version
  pyproject.toml
  uv.lock
  requirements.txt
  Dockerfile
  alembic.ini
  alembic/{env.py,script.py.mako,versions/0001_auth_foundation.py}
  app/
    __init__.py
    main.py
    api/{__init__.py,auth.py,schemas.py}
    core/{__init__.py,config.py,errors.py,telegram.py}
    database/{__init__.py,models.py,session.py}
    services/{__init__.py,auth.py}
  scripts/{export_openapi.py,test-postgres.sh}
  openapi.json
  tests/
    __init__.py
    conftest.py
    signing.py
    test_telegram_verification.py
    test_auth_api.py
    test_auth_configuration.py
    test_auth_rate_limits.py
    test_migrations.py
    test_bot_launch.py
```

Other new files: `telegram_bot/{__init__.py,__main__.py}`, `compose.yaml`,
`.dockerignore`, `.github/workflows/authentication.yml`,
`tools/api-types/{package.json,package-lock.json}`,
`miniapp/src/features/auth/{AuthProvider.tsx,AuthProvider.test.tsx,context.ts}`,
`miniapp/src/integrations/telegram/init-data.ts`, generated
`miniapp/src/lib/api/schema.d.ts`, `miniapp/scripts/test-auth-integration.mjs`,
this report, `docs/AUTHENTICATION.md` and ADR 0002.

Updated frontend: `package.json` scripts, `src/main.tsx`, `app/PresentationGate.tsx`,
`app/App.test.tsx`, `components/layout/AppShell.tsx`, `lib/api/client.ts`,
`lib/api/client.test.ts`, `e2e/foundation.spec.ts`, `styles.css`. Root README,
`.env.example`, `.gitignore`, security/DevOps/API/open-decisions documentation
and baseline status notes now describe the M02 implementation accurately.
The M00/M01 uncommitted work already present in the snapshot was preserved.

## Migration and configuration

The one chain starts at **`0001_auth_foundation`**. It creates only `users`,
`sessions` and `auth_rate_limits` plus Alembic version metadata. The auth-only
counter table is necessary to count invalid attempts across workers; counting
successful sessions or using per-process memory would not satisfy throttling.
UUID generation works on the tested PostgreSQL 16.15. Downgrade/recovery tests
operate on disposable databases only; no retained data was migrated/deleted.

Tooling: Python 3.12.14/uv 0.13.5 with frozen dependencies; PostgreSQL 16.15 image
and Python base image pinned by digest; Node 24.22.1/npm 11.9.0 retained. Hashed
runtime requirements are exported from `uv.lock` and installed with hash/TLS
verification intact in a UID 10001 API image. Docker DB is private; API host
binding is loopback-only. The optional Aiogram bot performs launch/menu handling
only and was not connected to an actual account.

The actual OpenAPI generates the auth types. `openapi-typescript` requires
TypeScript 5, so it runs in a separate locked tooling package; the app remains
on its working TypeScript 6. The initial incompatible peer install was rejected
and resolved this way, without `--force`/legacy peer overrides or app downgrade.

## Commands and actual results

| Command/check | Actual outcome |
|---|---|
| Local Docker daemon status | Managed local socket available, Docker 29.9.2. |
| `uv lock`; `uv sync --frozen` in `backend/` | PASS, isolated `.venv`; locked Python deps installed. Initial invocation from repository root failed because the manifest is under `backend/`; corrected working directory succeeded. |
| `backend/scripts/test-postgres.sh` | PASS from the saved helper: it creates its own loopback PostgreSQL, runs frozen install and **115 pytest tests**, then removes its own container. |
| `.venv/bin/pytest -q` with guarded `TEST_DATABASE_URL` | **115 passed, no skips**. PostgreSQL 16.15, actual migrations and constraints; no SQLite substitute. |
| `.venv/bin/ruff check app alembic tests scripts ../telegram_bot` | PASS. |
| `.venv/bin/mypy app scripts ../telegram_bot` | PASS, strict, **17 source files**. |
| `bash -n backend/scripts/test-postgres.sh` | PASS. |
| `PYTHONPATH=. .venv/bin/python scripts/export_openapi.py` then locked generator | PASS; actual auth OpenAPI/types exported without any DB/Telegram connection. |
| `npm run check` in `miniapp/` | PASS: strict TypeScript, zero-warning ESLint, **45 tests across 4 files**, production build, forced-mock production-artifact exclusion. |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e` | **10 passed**, no retries/skips. Responsive mock-shell checks plus production role/auth/logout screens with deliberate API fixtures. |
| `TEST_BROWSER_DATABASE_URL=… PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:auth-integration` | **5 real-stack flows passed**: production React + ephemeral HTTPS + actual FastAPI + actual PostgreSQL. No API response mocks. |
| Docker image build with CA secret and hash-verified requirements | PASS. Runtime UID **10001**, liveness **200**, anonymous Owner API **401**. |
| `docker compose --env-file <ignored-test-file> config --quiet` | PASS; resolved credentials not printed. Compose defines development API/private DB/optional bot; the complete Compose stack was not brought up or deployed. |
| Frozen toolchain/static verification | PASS: isolated generator `npm ci`; `uv lock --check --offline`; hashed requirements/OpenAPI/TS regenerate byte-for-byte; 22 relative Markdown links, new-file whitespace, YAML syntax and secret/cache ignore rules verified. |

The backend tests cover an independent Aiogram HMAC reference; valid/forged/
wrong-bot/expired/future/missing/duplicate/malformed data; cookie attributes and
plaintext-token absence in DB; CSRF/Origin/content-type/no-CORS behavior; Owner
and cross-customer identity isolation; expiry, revocation, rotation and replay
including concurrent requests; allowlist removal and DB-role tampering; shared
failed-attempt rate limits/races; production configuration rejection; migration
fresh upgrade, seeded-head idempotence, disposable downgrade/recovery and DB
constraints; private bot launch and provider-log redaction.

Migration tests do not claim an existing legacy/business-schema upgrade: none
exists in M02. They exercise the initial migration plus seeded-head repeatability
and recovery. M03 must extend this exact chain and add its own data-upgrade tests.

The five real-stack browser flows verify: Customer signed login/Secure HttpOnly
cookie/reload restoration; Customer UI and actual Owner API 403 denial; real
missing-CSRF rejection plus successful logout, old-cookie DB revocation and no
automatic proof replay; configured Owner access and both workspaces; forged
proof rejection/no session. The only intercepted destination is the external
Telegram presentation SDK. The synthetic signing key never reaches the browser.
Self-signed TLS trust is confined to ephemeral loopback test browser contexts;
package/artifact verification remains enabled.

Initial test-side argument/copy/JSON expectations were corrected without
weakening security assertions. A future-time API vector uses a sufficient
margin to avoid CI scheduling races; deterministic unit vectors still cover
the exact freshness boundary. Final affected runs and saved helper passed.

## Remaining risks, external evidence and stop point

No automated M02 acceptance blocker remains. **Real Telegram Android/iOS/Desktop
launch and cookie behavior remain PENDING; G1 is not passed.** No real bot token,
Owner account ID, stable HTTPS origin or device was available/configured. Follow
the exact BotFather/test-bot/HTTPS/two-account/expiry/logout/device checklist in
[AUTHENTICATION.md](AUTHENTICATION.md) and record actual evidence there.

Transport-peer rate limits aggregate users behind an unconfigured proxy; before
wider exposure, review the trusted gateway and edge rate/body-timeout policies.
Session/proof retention, secret rotation and incident/admin operations need the
trusted operational process described in the runbook; no public admin mutation
or automatic pruning job is invented. Broader hardening/deployment is not the
M02 auth task. Existing commercial and hardware decisions stay unresolved.

GitHub workflows were added/updated but not run remotely. No production data,
payment provider, binding quotation or physical printer was touched. No commit,
push, environment draft change or publication was performed. Review M02 before
authorizing M03; M03 has not started.
