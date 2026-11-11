# M03 implementation and verification report

This is the implementation-task record. The subsequent
[M03 final acceptance review](M03_FINAL_ACCEPTANCE_REVIEW.md) records current
180-test backend evidence, production-mode container verification and the
review-branch/PR handoff. Commit/push and container-build limitations below
refer to this earlier implementation run, not the later acceptance task.

Date: 2026-11-11 UTC. Base: `08fb8e0353f0364b722aa3a3e07454124b2f1ebc`,
branch `codex/m02-telegram-auth`. Started from a clean working tree.
**M03 implementation and local checks pass. Stop for review; M04 is not started.**

## Verified instructions and scope

Read root AGENTS and the requested roadmap, architecture, data model, state
machine, integrity, dependency, security and M02 acceptance files, plus API
contracts and the existing React/authentication implementation before extending it.
The requested `prompts/M03_BACKEND_FOUNDATION.md` does not exist. The actual
milestone prompt is
`prompts/M03_CORE_DATABASE_API_AND_TRANSACTION_FOUNDATION.md`, which was used.
The acceptance review is `docs/M02_FINAL_ACCEPTANCE_REVIEW.md` (no literal
backslash in its name). These discrepancies were reported before implementation.

Reused FastAPI app/settings, async DB factory, M02 user/session models,
security middleware/dependencies, same-origin React API client, auth provider,
Query, dashboard components, existing migration chain and tests. No dependency
was added. The new business models/domain/services/API remain in the existing
modular monolith.

## Implemented behavior

- Atomic parent service project and first stage draft for all three service
  types. Combined projects begin with design, with no speculative print stage.
- Customer-scoped paginated project/request reads, Owner inspection/listing,
  own draft edits and reasoned Customer/Owner cancellation. Unknown/inaccessible
  IDs return 404. Owner cannot edit another customer's notes or impersonate a
  customer at creation. Only trusted server configuration selects Owner.
- Optimistic row versions, specification revision/hash, domain transition guard,
  actor/action/entity-scoped persistent command keys and typed original response
  replay. Reused key with different data returns 409.
- Transactional audit, pending notification outbox and idempotency result; no
  delivery worker or Telegram alerts. DB trigger rejects audit UPDATE/DELETE.
- Current session/active account/configured role revalidated inside command
  transaction. Resource permissions also checked before returning cached private
  responses. User/session/request locking serializes conflicting writes and
  revocation; PostgreSQL advisory locks handle concurrent duplicate commands.
- Typed `/api/v1` business endpoints and Owner-protected DB/schema readiness.
  Existing liveness and auth endpoints remain operational. Cookie-authenticated
  writes require session CSRF and exact configured Origin. Draft command bodies
  have a 32 KiB limit; trusted fields and malformed text fail validation.
- Generated actual OpenAPI and TypeScript schemas. Authenticated React users
  explicitly load drafts, create/edit/cancel simulations, and see pending/error/
  empty states. Owner can inspect and cancel. Exact failed command retries keep
  their key in memory; ambiguous network/5xx responses block new edits until
  retry. Existing disconnected development UI mock grants no backend identity.

Submission is deliberately blocked with `409 intake_not_available`: M04 file/
item validation and M05 design scope do not exist. Request states implemented
are `draft` and terminal `cancelled`; there is no fabricated submitted/analyzing
workflow. Project status aggregation is deferred rather than invented. See
[ADR 0003](adr/0003-business-transaction-foundation.md) for the exact decisions.

## Migration evidence

New revision `0002_business_foundation` extends `0001_auth_foundation`, adding
only `service_projects`, `service_requests`, `audit_logs`,
`idempotency_records`, `notification_outbox`, constraints/indexes and the audit
immutability trigger. The original authentication migration is byte-identical
to HEAD, verified directly. No runtime `create_all()` was introduced.

Used PostgreSQL **16.15**, the existing pinned official 16-bookworm image, in a
task-owned Docker container bound to loopback port 55432. Only disposable test
DBs were used, including `3dps_test_m03_final` and separate
`3dps_test_browser_m03final`. Fresh upgrade reached
`0002_business_foundation (head)`; `alembic check` reported
**“No new upgrade operations detected.”** The public schema has the three M02
application tables, five M03 tables and `alembic_version`, with no future-domain
tables.

All three migration tests pass. The original M02 roundtrip explicitly targets
its immutable revision. A new fixture upgrades seeded M02 users/sessions to
M03, verifies identity/token-hash preservation and exact table/trigger inventory,
downgrades the empty business schema to M02, verifies auth preservation/trigger
removal, and upgrades again. Each migration fixture creates/drops only its own
randomly named test DB. Downgrade is destructive to business history and was
exercised only in disposable fixtures. Real recovery needs backup/restore or a
reviewed forward migration; no production downgrade is authorized.

## Actual checks and results

Commands below ran from the indicated directory. DSNs are represented by
`M03_TEST_DSN` / `M03_BROWSER_TEST_DSN`, both disposable loopback test targets,
not application or production credentials.

| Directory / command | Actual final result |
|---|---|
| `backend`: `.venv/bin/ruff check app alembic tests scripts ../telegram_bot` | PASS |
| `backend`: `.venv/bin/mypy app scripts ../telegram_bot` | PASS, 25 source files |
| `backend`: `TEST_DATABASE_URL="$M03_TEST_DSN" .venv/bin/pytest -q` | **177 passed**, 24.11s |
| `backend`: `DATABASE_URL="$M03_TEST_DSN" .venv/bin/alembic upgrade head` | PASS, fresh M02 + M03 installation |
| `backend`: `DATABASE_URL="$M03_TEST_DSN" .venv/bin/alembic current` | `0002_business_foundation (head)` |
| `backend`: `DATABASE_URL="$M03_TEST_DSN" .venv/bin/alembic check` | PASS, no metadata drift |
| `backend`: `PYTHONPATH=. .venv/bin/python scripts/export_openapi.py` | PASS, no DB/Telegram connection |
| `miniapp`: `npm run generate:api` | PASS; isolated pinned OpenAPI generator |
| Root: regeneration of both artifacts with SHA-256 before/after assertion | PASS, byte-identical OpenAPI and TS |
| `miniapp`: `npm run check` | PASS: strict TS, ESLint, **58 Vitest/RTL tests**, Vite build, production mock exclusion |
| `miniapp`: `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e` | **10 passed**, 10.8s |
| `miniapp`: `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium TEST_BROWSER_DATABASE_URL="$M03_BROWSER_TEST_DSN" node scripts/test-auth-integration.mjs` | **7 flows PASS**, real production React + ephemeral HTTPS + FastAPI + PostgreSQL |
| `miniapp`: `node --check scripts/test-auth-integration.mjs` | PASS |
| Root: `git diff --check` | PASS |

The 177 backend cases preserve the 131-case M02 suite and add 45 business cases
and one migration case. The 58 frontend cases preserve 51 existing cases and add
7 draft-workspace cases. Existing ten UI browser cases still cover multiple
widths, both roles/themes, production role isolation and authenticated navigation.
The seven real-stack flows preserve the five original M02 checks and add two
business flows. Uvicorn startup, actual business writes, mobile 390px horizontal
layout, cross-customer API denials and Owner cancellation passed through HTTPS.
Customer mobile and Owner desktop screenshots were inspected; artifacts contain
synthetic data only and remain under ignored `miniapp/test-results/`.

Security/concurrency/rollback coverage includes same-key races across two app
instances with distinct DB pools (one project/audit/outbox/result), different-key
version races, repeated Owner-vs-Customer edit/cancel races (one 200, one 409),
concurrent session rotation, revocation between dependency and command, key
scoping across customers, Owner configuration removal before cached replay,
CSRF/Origin on create/edit/cancel, forged trusted fields, malformed/oversize notes,
submission guard, lineage/stage/mode/duplicate-stage constraints, immutable audit,
and failures at audit/outbox/idempotency insertion rolling the entire command
back. Existing-draft outbox failure also preserves prior notes/version/hash.

During implementation, lint/type checks identified routine issues that were
corrected before final checks. A first real-stack attempt could not launch the
absent Playwright-managed browser; using the documented existing
`/usr/bin/chromium` fallback passed. No tests were skipped to bypass PostgreSQL
or browser checks. Non-failing npm update notices and NO_COLOR/FORCE_COLOR
warnings were observed.

Two security/concurrency issues were corrected before completion: cached
responses now reauthorize current resource access after Owner demotion, and
user-before-session **non-key** user locking avoids login rotation/FK lock-order
hazards. Both have regression coverage; there was no deployed-data correction.

## CI, limitations and boundaries

`.github/workflows/authentication.yml` retains its filename/job ID, expands its
name and adds `alembic check`; its existing complete pytest and real-stack steps
pick up M03 automatically. `frontend.yml` continues the full frontend checks and
ten UI tests. Generated-contract drift detection remains configured.
**Hosted GitHub Actions was not run or claimed green in this task.** Changes are
uncommitted/unpushed for review, so this report proves local execution only.
No application Docker image build was repeated; the new Python source/migration
uses the existing COPY layout and unchanged dependencies. PostgreSQL Docker and
actual Uvicorn/browser startup were exercised.

No local automated blocker remains for scoped M03 review. Remaining limits:

- Android/iOS/Desktop Telegram cookie behavior, real BotFather launch and the
  intended deployed HTTPS proxy remain external verification. The loopback TLS
  gateway is not Caddy deployment evidence and does not close G1. Follow
  [BUSINESS_FOUNDATION.md](BUSINESS_FOUNDATION.md)'s device checklist.
- Outbox rows remain pending. Delivery/routing is M08; retries/reporting M13.
  There are no notification-delivery or cleanup claims.
- Audit/idempotency/outbox retention is unresolved. Existing M02 session/proof
  retention remains unchanged; no pruning is introduced that could allow replay.
  Production DB-role hardening and backup/recovery remain release work; table
  owners/superusers can override triggers or truncate trusted databases.
- Current audit entities reference requests and authenticated actors only;
  later system/other-domain events require explicit schema evolution.
- Project status aggregation, deep-link detail screens, cursor pagination beyond
  the bounded initial view, full intake specifications and derived print stages
  need their own reviewed milestone contracts. In-memory retry keys do not
  survive a full WebView reload; reload/resume the persisted list before issuing
  a new creation after an ambiguous response. No exactly-once user intent across
  client reinstall/reload is claimed.

All live feature flags remain disabled. No Operator role, upload/storage worker,
quotation/order/payment/provider table, checkout or physical-printer control was
introduced. No production data, service, deployment, publish, commit or push was
modified/performed. The task-owned disposable PostgreSQL container is removed
after verification; browser/API/gateway processes clean up on completion.

Next proposed work is **M04 secure customer file intake**, only after M03 review:
private uploads, request items/specification, persisted draft wizard, validated
submission and durable pending-analysis records; no M06 processing claim. Do not
begin it automatically.

## Changed files

- `.github/workflows/authentication.yml`
- `README.md`
- `backend/alembic/env.py`
- `backend/alembic/versions/0002_business_foundation.py`
- `backend/app/api/auth.py`
- `backend/app/api/business.py`
- `backend/app/api/business_schemas.py`
- `backend/app/database/business_models.py`
- `backend/app/domain/__init__.py`
- `backend/app/domain/requests.py`
- `backend/app/domain/types.py`
- `backend/app/main.py`
- `backend/app/services/requests.py`
- `backend/app/services/transactions.py`
- `backend/openapi.json`
- `backend/tests/test_business_foundation.py`
- `backend/tests/test_migrations.py`
- `compose.yaml`
- `docs/API_CONTRACTS.md`
- `docs/ARCHITECTURE.md`
- `docs/BUSINESS_FOUNDATION.md`
- `docs/DEVOPS.md`
- `docs/M03_IMPLEMENTATION_REPORT.md`
- `docs/adr/0003-business-transaction-foundation.md`
- `miniapp/scripts/test-auth-integration.mjs`
- `miniapp/src/app/ServiceConnection.tsx`
- `miniapp/src/features/requests/RequestWorkspace.test.tsx`
- `miniapp/src/features/requests/RequestWorkspace.tsx`
- `miniapp/src/lib/api/schema.d.ts`
- `miniapp/src/pages/CustomerDashboard.tsx`
- `miniapp/src/pages/OwnerDashboard.tsx`
- `miniapp/src/styles.css`
