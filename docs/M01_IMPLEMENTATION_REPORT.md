# M01 — React Mini App foundation

Date: 2026-11-11 (Asia/Rangoon). M00 architecture approval and M01 authorization
were supplied explicitly by the owner. **M01 implementation complete; stop for
review before M02.** No G1/device/authentication or live-operation claim is made.

## Implemented scope

The restored checkout contained the M00 documents and inert env template but
no working frontend or backend. Existing documents were preserved, with approval
status notes updated; no backend functionality was removed.

- React 19, strict TypeScript 6, Vite 8 and Tailwind 4 under `miniapp/`, pinned
  dependencies/lockfile, Node 24.22.1 and npm 11.9.0 tooling.
- React Router routes `/app` and `/owner`, root redirect and recoverable not-found
  screen. Only Customer and Owner workspace presentations exist. Business
  modules are inert; no customer/order/payment/stock records are fabricated.
- Responsive navigation and dashboard layouts, reusable button/card/badge and
  loading/error/empty states, accessible names/focus/skip link and reduced motion.
- TanStack Query provider/cache defaults; optional user-triggered health query
  demonstrates loading, safe connection failure and retry without faking an API.
- Official Telegram Web App presentation adapter: validated theme colors,
  system-theme fallback, viewport and safe/content insets, back-button lifecycle
  and event cleanup. No identity is parsed from `initDataUnsafe` or trusted.
- Explicit `VITE_TELEGRAM_MOCK=true` development-only dynamic UI adapter, no
  persisted identity, session, role headers or backend privilege. Normal browser
  shows Telegram entry guidance; actual Telegram context shows pending secure
  sign-in until M02. Production cannot enter the mock workspace.
- Central relative `/api/v1` transport with same-origin cookies, safe normalized
  errors, cancellation, no-content handling, URL/path/redirect restrictions and
  explicit CSRF/idempotency header support for future commands. No auth endpoints
  or mutations are wired. Backend enforcement remains an M02+ requirement.
- Configurable Vite `/api` proxy; ESLint, Vitest/RTL, Playwright and a frontend CI
  workflow. Real FastAPI/OpenAPI domain types remain deferred until APIs exist.

## Changed files

New frontend files (35):

```text
miniapp/
  .env.example
  .node-version
  package.json
  package-lock.json
  index.html
  tsconfig.json
  tsconfig.node.json
  eslint.config.js
  vite.config.ts
  playwright.config.ts
  scripts/check-production.mjs
  e2e/foundation.spec.ts
  src/
    main.tsx
    styles.css
    app/{App.tsx,App.test.tsx,PresentationGate.tsx,ServiceConnection.tsx,query-client.ts}
    components/layout/AppShell.tsx
    components/ui/{Badge.tsx,Button.tsx,Card.tsx,States.tsx,utils.ts}
    integrations/telegram/{TelegramProvider.tsx,TelegramProvider.test.tsx,mock.ts,types.ts}
    lib/api/{client.ts,client.test.ts}
    pages/{CustomerDashboard.tsx,OwnerDashboard.tsx,NotFound.tsx}
    test/setup.ts
```

Also added `.github/workflows/frontend.yml` and this report. Updated root
`README.md` with tested commands, `.gitignore` for generated frontend artifacts,
and M00 approval metadata in `IMPLEMENTATION_BASELINE.md`, `OPEN_DECISIONS.md`
and `adr/0001-project-baseline.md`. The baseline retains its historical M00
inventory, with an explicit current-status note. Other unresolved business,
legal, pricing, provider and schema decisions were not silently resolved.
The existing M00 imports remain part of the pre-existing uncommitted workspace,
not new M01 application work.

Browser tests live inside `miniapp/e2e/` so they resolve the single frontend
dependency installation; this is the scoped equivalent of the roadmap's
suggested root `tests/e2e/`. Native accessible/shadcn-style reusable primitives
are used rather than adding unnecessary complex component dependencies.

## Commands and actual results

Commands below ran from `miniapp/` unless stated otherwise. No test suite was
replaced with a zero-test placeholder.

| Command / check | Actual result |
|---|---|
| `node --version`, `npm --version` | `v24.22.1`, `11.9.0` |
| `npm install --save-exact …` / `npm install --save-dev --save-exact …` | Dependency/tool installation succeeded; exact versions persisted in manifest and lockfile. Cache used `/tmp/3dps-npm-cache`. |
| `npm ci --cache /tmp/3dps-npm-cache` | Exit 0; clean lockfile-based reinstall, 249 packages installed. |
| `npm run typecheck` | PASS, application/unit tests and Vite/Playwright/browser test configurations. Also runs as part of `build`. |
| `npm run lint` | PASS, ESLint with zero warnings allowed. |
| `npm run test` | PASS: **3 files, 34 tests**; no failures/skips. |
| `npm run build` | PASS: strict checks and production Vite build in ignored `dist/`. JS approximately 350 kB / 110 kB gzip; CSS approximately 27 kB / 6.3 kB gzip. |
| `npm run check:production` | PASS: builds with `NODE_ENV=production` and `VITE_TELEGRAM_MOCK=true`; build plugin rejects any mock module inclusion and artifact inspection finds no development mock. |
| `npm run check` | Exit 0: typecheck, lint, 34 tests, build and adversarial production check. Final CSS refinement was followed by another build and browser regression run. |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e` | PASS: **8 tests**, 2 workers, no retries/skips. Rebuilds the adversarial production artifact before tests. System Chromium `156.0.8078.79` used. |
| Manual local Vite startup + Playwright screenshots | Customer desktop/mobile and dark Owner mobile captured outside the checkout and visually inspected; no external assets or fabricated records required. |
| Actual local `/api/v1/health` through Vite proxy | HTTP **502**, observed by curl and a real browser request with no health fixture. No API is configured/running at the default target; UI showed “Service not connected” with retry. This is **not** a passed backend health check; successful HTTP UI tests use explicit fixtures. |
| `git diff --check` plus explicit untracked-file inspection | PASS: 10 relative Markdown links resolved, new-file whitespace checked, manifest/lockfile dependencies match exactly, all five root live/policy flags remain false. |

Vitest coverage includes both workspaces and inert services, two-role navigation,
theme switching, browser/Telegram entry gates, loading/connection error/retry,
unknown routes, explicit mock opt-in and production refusal, theme/inset/viewport
events and cleanup, native back behavior, relative requests, unsafe URL rejection,
HTTP status normalization, CSRF/idempotency headers, malformed JSON/HTML, empty
204/HEAD responses and cancellation.

Playwright covers 320px/390px phones, 768px tablet and 1440px desktop with
no horizontal overflow, both workspaces and readable owner intro width,
light/dark themes, disabled project action, keyboard navigation and not-found
recovery. Production tests attempt URL/localStorage role overrides and unverified
Telegram context; neither enables a role selector or Owner shell. External SDK
loading is intercepted for deterministic UI tests; health responses are stubbed
only in the explicit transport-state test.

Initial check failures were investigated and corrected: Vitest's `loadEnv`
export changed (now imported from Vite); RTL options and browser-test DOM typings
were aligned with their actual APIs; one not-found assertion used mismatched
copy. Independent review identified JSON parsing before empty 204 handling,
which was fixed and covered with a JSON-header regression test. Visual review
then found a narrow Owner intro column; a width assertion reproduced the tablet
case and the responsive grid was corrected. The final affected runs pass.
An initially installed deprecated ESLint 9 was replaced with supported pinned
ESLint 10 before final validation. No TLS or dependency verification was disabled.

## Boundaries and remaining work

No M01 acceptance blocker remains. Real backend health, verified Telegram
`initData`, owner provisioning, sessions, CSRF validation, authorization and
PostgreSQL migrations are absent by milestone design. There is no working
backend to preserve/remove and no database migration in this change.

Real Telegram Android/iOS/Desktop launch, safe-area/keyboard/cookie behavior and
BotFather/HTTPS configuration remain **PENDING M02/G1 external evidence**. Browser
SDK fixtures are not device or authentication tests. The GitHub workflow has
been added but not run remotely. No production deployment, environment draft
change/publication, commit or push was performed.

All root live feature flags remain false; no binding quote, payable order,
payment collection, physical printer connection or production data operation
was introduced. Existing open decisions keep their deadlines. Review M01 before
authorizing M02; no M02 implementation has started.
