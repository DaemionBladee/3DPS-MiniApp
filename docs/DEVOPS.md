# Development, testing and deployment runbook

M03 business API/migrations and Cloud test instructions are maintained in
[BUSINESS_FOUNDATION.md](BUSINESS_FOUNDATION.md).
M02 runnable authentication setup, Docker/Cloud tests, schema generation and
real Telegram device steps are maintained in [AUTHENTICATION.md](AUTHENTICATION.md).
M01 frontend commands remain in the root README. Planned broader services and
deployment targets below are not claims that later milestones have been implemented.

## Primary workflow: Codex Cloud website + private GitHub
- This project is developed with **Codex on the website**, not necessarily with Codex CLI. Upload the **contents of the package** so `AGENTS.md` is at GitHub repo root, alongside `docs/` and `prompts/`; do not nest the entire instruction directory.
- Prepare and publish a Codex Cloud environment attached to the repository. Configure only test dependencies, scoped environment variables and allowed network destinations; never use production bot tokens, customer data, live wallet details or production DB secrets.
- Check which facilities the particular environment offers. **Do not assume Docker/Compose, host networking, full Telegram interactive preview, or long-lived bot processes work in cloud tasks.** Run supported tests and record unsupported end-to-end checks as pending; use optional CachyOS or staging VPS for the rest.
- Each cloud task has its own isolated workspace; review and save/merge code through the GitHub workflow before subsequent milestones. No direct production deployment by Codex without explicit owner permission.

## Optional development system: CachyOS (Arch-based)
- Use host tools: Git, Codex, Node.js/npm, browser, optional slicer GUI. Use Docker Compose for backend, DB, queue and isolated processing.
- Common packages may be installed with `sudo pacman -Syu` then `sudo pacman -S --needed git base-devel python nodejs npm docker docker-compose curl` (verify availability and current package names on the user's host).
- `sudo systemctl enable --now docker`; `sudo docker run --rm hello-world` for validation.
- The Docker group grants root-equivalent control; prefer rootless Docker where feasible or deliberate sudo access. Never expose Docker socket inside customer-facing services.
- Local development uses `.env` based on committed `.env.example`, with secrets kept private and **never** in source control.

## Environment separation
`APP_ENV` is the **infrastructure/deployment environment**. `SIMULATION_MODE` is the **business operational mode**. For example a publicly reachable, invitation-only prelaunch server may have `APP_ENV=production`, `SIMULATION_MODE=true` and **all four live feature flags false**. These are not contradictory. Each new quote/order/payment row still carries mode so it can never be promoted implicitly.

## Suggested environment names and feature switches
| Variable | Purpose | Safe default |
|---|---|---|
| `APP_ENV` | development/staging/production | development |
| `BOT_TOKEN` | Telegram bot secret (backend/bot only) | unset |
| `OWNER_TELEGRAM_IDS` | Owner allowlist from trusted config | unset |
| `DATABASE_URL` | async PostgreSQL DSN | local Docker internal host |
| `SESSION_SECRET` | random high-entropy secret | unset |
| `PUBLIC_BASE_URL` | HTTPS Mini App origin | development tunnel only |
| `BINDING_QUOTES_ENABLED` | Allow *any* binding quote, including manual owner quote, after the relevant live gates | false |
| `AUTO_QUOTE_ENABLED` | Allow automated binding quotes; requires `BINDING_QUOTES_ENABLED` and calibrated profiles | false |
| `PAYMENT_POLICY_APPROVED` | Confirm approved physical/digital payment classification | false |
| `LIVE_PAYMENTS_ENABLED` | Allow real payment flow | false |
| `REAL_PRINTING_ENABLED` | Allow real production | false |
| `SIMULATION_MODE` | Virtual profiles and simulated operations | true |
| `UPLOAD_MAX_MB` | Upload cap and quotas | conservative |
| `STORAGE_ROOT` | Private storage root | private volume |

Backends must validate incompatible flag combinations and fail startup if live actions are enabled while simulation mode is on or required hardware/payment checks are missing. **`LIVE_PAYMENTS_ENABLED` requires `PAYMENT_POLICY_APPROVED`, permitted category-specific methods and owner signoff. `BINDING_QUOTES_ENABLED` additionally requires approved policy and **category/stage-specific live-fulfillment readiness** (digital design requires approved design capacity and compliant checkout, not printer stock; printed items additionally require calibrated printer and stock readiness); `AUTO_QUOTE_ENABLED` requires `BINDING_QUOTES_ENABLED` plus calibrated/approved printer, material, stock and pricing profiles. `REAL_PRINTING_ENABLED` requires verified payment and an actual compatible physical printer.** Maintain separate environment files/secret stores per stage.

## Local service plan
| Service | Image/runtime | Exposed to host? |
|---|---|---|
| frontend | Vite Node LTS dev server | 127.0.0.1:5173 for local testing |
| api | Python backend | 127.0.0.1:8000 optional for host testing |
| bot | Aiogram long polling | No inbound port |
| db | PostgreSQL pinned supported version | Private internal network |
| redis | Redis pinned supported version | Private internal network |
| worker | isolated Python + slicer | No inbound or public port |
| caddy | local/staging reverse proxy | HTTPS when needed |

Development frontend uses Vite proxy `/api` -> `http://api:8000` when inside Compose (or `http://localhost:8000` when Vite runs on host). Browser only uses relative `/api/v1/*` requests.

## HTTPS and Telegram device testing
- For local phone testing, use a temporary **HTTPS tunnel** to the Vite gateway, with mock data and properly authenticated APIs; set the same origin as the bot's Mini App URL in BotFather.
- Temporary tunnel URLs change; never depend on them for production or public customer checkout. Lock down preview as reasonably practical and don't expose owner data via unsecured endpoints.
- Production: DNS -> Caddy -> static React build and private FastAPI under `/api/*`; set stable HTTPS URL in BotFather. Bot can long poll without public webhook.

## Testing commands (targets; adapt to actual repo)
- Cross-domain invariants: run the tests mapped in `docs/INTEGRITY_RULES.md`, `docs/STATE_MACHINES.md`, and `docs/DEPENDENCY_MATRIX.md`. Database race tests must use **actual PostgreSQL**, not SQLite or mocks.
- Python: `ruff check .`, `pytest -q`, `mypy` or `pyright` as configured; run inside pinned Docker environment if dependencies are isolated.
- Frontend: `npm run typecheck`, `npm run lint`, `npm run test`, `npm run build`. Codex must add scripts as part of frontend foundation if missing.
- E2E: Playwright in supported Linux container / CI; exercise two roles and full simulated lifecycle.
- Schema: Alembic upgrade on disposable empty DB; also test migration from an old seeded copy and rollback/recovery where safe.
- Security: verify unauthorized read/write, file access isolation, CSRF, uploads, auth tampering, stale actions and concurrency.

## CI/CD proposal
1. On pull request: frontend lint/type/test/build; backend lint/type/test; Docker build; migration test; dependency/SAST scans.
2. Protect `main`, review changes, inspect generated SQL and infrastructure changes.
3. Staging deploy, run E2E + restore smoke tests.
4. Production deploy only after owner approval; apply reversible migrations safely; health check, canary where possible, rollback plan.
5. Do not auto-deploy experimental worker code or enable real payments/hardware without release gate M16.

## Production baseline
- Stable Debian/Ubuntu LTS VPS with SSH keys, strict firewall, automatic security patch plan, Docker Compose pinned images, resource limits, Caddy TLS and private networks.
- Private PostgreSQL volume and model storage; encrypted off-server backup and tested restore procedure.
- Dedicated worker/container for model processing with strict limits; later separate host/VM for stronger isolation.
- Centralized basic logs/alerts, low-stock and payment queue notifications, HTTPS cert monitoring and offsite backup verification.
- No direct public printer interface; when hardware exists, prefer secured outbound workshop agent and explicit local safety checks.

## Operational incidents / rollback
- API outage: bot should tell customers service temporarily unavailable when possible; preserve drafts and retry notifications from outbox after recovery.
- Slicer failure: mark task failed/manual review; never issue binding quote on unknown result.
- Payment ambiguity: hold order for owner; do not auto-confirm or repeat charge.
- Failed DB migration: restore staging/prod backup according to reviewed migration plan; don't apply ad-hoc destructive fixes.
- Suspected credential leak: rotate token/session secrets, revoke sessions, notify owner and inspect audit logs.
