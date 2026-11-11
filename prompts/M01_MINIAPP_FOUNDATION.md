# Codex Task M01 — React/TypeScript Telegram Mini App foundation

**Prerequisite:** M00 reviewed and accepted.

Read `AGENTS.md`, `docs/FRONTEND_SPEC.md`, `docs/ARCHITECTURE.md` and `docs/SECURITY.md`. Implement the smallest working frontend foundation in the existing repository.

## Implement
1. React+TypeScript strict+Vite inside `miniapp/` (reuse any existing bootstrap safely).
2. Tailwind, accessible reusable components, light/dark Telegram theme handling, safe-area support, navigation and loading/error/empty states.
3. Two route shells only: `/app` customer and `/owner` owner. The owner page contains placeholder modules for reviews, payment, production and inventory; no operator route.
4. React Router, TanStack Query, centralized typed API client foundation with relative `/api/v1` URLs.
5. Vite `/api` proxy for Docker/host as appropriate.
6. Telegram integration adapter and **explicit development-only** UI mock. Do not make mock login a production backend bypass.
7. Vitest/RTL setup, typecheck, lint, build, README/run documentation.

## Do not
- No invented quote calculations in React, no real payment, no physical printer remote start, no owner API grant based only on React route.
- No unsupported production credentials in browser bundle.

## Acceptance
Both responsive shells render and navigate; production build contains no active test role override; API health request succeeds if backend is running; type/lint/unit/build report exact results. Stop after M01.
