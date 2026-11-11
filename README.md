# 3DPS-MiniApp

Telegram-first 3D printing and custom design workspace. **M02 adds secure Telegram
authentication with FastAPI/PostgreSQL to the M01 frontend.** Customer and Owner
dashboards remain non-operational shells: no orders, quotations, payments,
uploads or printers are connected. Review M02 before beginning M03.

For real API setup, migrations, Docker/Cloud tests and Telegram device testing,
read [the authentication runbook](docs/AUTHENTICATION.md). The frontend-only UI
preview below still needs no bot credentials or backend.

## Run the frontend

Use Node **24.22.1** (see `miniapp/.node-version`) and npm **11.9.0**. Dependencies
are pinned in `miniapp/package.json` and `package-lock.json`.

```sh
cd miniapp
npm ci
VITE_TELEGRAM_MOCK=true npm run dev
```

Vite listens on loopback port 5173. Open `/app` for the Customer shell and use
the preview toolbar to switch to `/owner`, or switch between light/dark themes.
The explicit mock flag enables **UI presentation only**. It creates no session,
sends no role headers and grants no API permissions. No secrets or bot IDs are
needed. Use only disposable test data.

To retain local settings, copy `miniapp/.env.example` to `miniapp/.env.local`
and deliberately set `VITE_TELEGRAM_MOCK=true`; restart Vite after changes.
Local env files are ignored. Never put bot tokens, session secrets or database
credentials in `VITE_*` variables: Vite exposes those to the browser.

Without mock opt-in or a valid server session, a normal browser shows “Open in Telegram”. The official
Telegram Web App script supplies theme, safe-area, viewport and back-button
presentation in actual Telegram. React restores the real cookie session or sends
raw launch data to FastAPI. Only the server's verified response selects Customer
or Owner access. Production always ignores the mock flag; real authenticated
workspaces are available through the API, without a development role override.

## API foundation

All requests go through `miniapp/src/lib/api/client.ts` using relative
`/api/v1/*` paths and same-origin cookies. The client normalizes safe errors,
accepts cancellation, rejects path/origin escapes and redirects, and requires
an explicit CSRF token for authenticated mutations. Login is the narrowly
scoped pre-session exception, protected by backend Origin/HMAC/rate checks.
Logout enforces CSRF and revokes the server session. Auth DTOs are generated
from actual FastAPI OpenAPI; business schemas remain deferred.

The development-only `API_PROXY_TARGET` defaults to `http://127.0.0.1:8000`.
For a future Compose-hosted API set it to the appropriate internal origin
(for example `http://api:8000` when Vite also runs in Compose). Browser API paths
remain relative. M02's optional Compose supplies the API and private DB; see
the auth runbook for setup. The preview's
optional “Check connection” requests the real `/api/v1/health` on click only;
connection failure is expected if the API is not running. No fake API is supplied.

## Checks

Run from `miniapp/`:

```sh
npm run typecheck          # Strict application, tests and tool configurations
npm run lint               # ESLint, React Hooks and Fast Refresh checks
npm run test               # Vitest + React Testing Library, one complete run
npm run build              # Typecheck + production Vite build in dist/
npm run check:production   # Forces mock=true in production; rejects mock module
npm run check              # All of the above
```

Browser tests use Playwright Chromium:

```sh
npx playwright install chromium
npm run test:e2e
```

`test:e2e` rebuilds the adversarial production artifact before starting isolated
loopback dev/preview servers. It checks phone/desktop shells, keyboard
navigation, themes, connection errors/retry and production role-hint rejection.
It stubs the external Telegram SDK and specific API responses for UI tests;
these are not real Telegram identity or backend-readiness evidence. The separate
`npm run test:auth-integration` builds production React and exercises real
FastAPI/PostgreSQL over ephemeral loopback HTTPS with synthetic signed proofs.
See the runbook for its required disposable browser-test database.

If the environment already supplies system Chromium, browser installation is
optional; use its actual path explicitly, for example:

```sh
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e
```

For a manual production check, run `npm run build` then `npm run preview`
(loopback port 4173). Without a valid session, `/owner?role=owner&mock=true`
cannot grant Owner access. Static hosting later needs SPA fallback routing
for `/app` and `/owner` plus same-origin `/api`; the preview server is not a
production deployment. Frontend and auth GitHub workflows run automated checks;
they have not been executed remotely merely by adding their YAML.

## Scope and review

See [AGENTS.md](AGENTS.md), [approved M00 baseline](docs/IMPLEMENTATION_BASELINE.md),
[frontend specification](docs/FRONTEND_SPEC.md), and
[M01 implementation report](docs/M01_IMPLEMENTATION_REPORT.md). Current results
are in the [M02 implementation report](docs/M02_IMPLEMENTATION_REPORT.md).

Real Telegram Android/iOS/Desktop launch and cookie behavior remain pending G1;
the required external checklist is in the authentication runbook. M02's single
Alembic revision creates authentication tables only. Live quotes/payments/physical
printer operations remain unavailable. Stop after M02 and review before M03.
No environment publication is part of this work.
