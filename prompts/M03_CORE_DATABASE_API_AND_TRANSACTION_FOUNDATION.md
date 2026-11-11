# Codex Task M03 — Core database, API and transaction foundation

**Prerequisites:** M02 implemented and tested.

Read root `AGENTS.md`, the specific milestone in `docs/MASTER_ROADMAP.md`, `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`, and `docs/DEPENDENCY_MATRIX.md`. Also read the relevant documents: `docs/DATA_MODEL.md`, `docs/API_CONTRACTS.md`, `docs/ARCHITECTURE.md`, `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`.

Inspect the actual repository, code, migrations, tests and Git status. Prepare a small implementation plan, then implement only this milestone. Do not assume a future milestone exists.

## Required implementation
1. Extend the existing M02 Alembic migration chain only; create minimal `service_projects`, `service_requests`, audit/idempotency/outbox primitives, and reusable transition-service boundaries; do not precreate all future domain tables.
2. Add async SQLAlchemy session/unit-of-work and transaction-aware application services with row-version conflict detection, idempotency-key persistence and strict migrations.
3. Implement typed FastAPI versioned endpoints for health/readiness and basic service-project/request skeleton; generate React OpenAPI types and configure same-origin client.
4. Outbox writes must be in the same transaction as audited domain changes; delivery worker may be deferred until M08.

## Acceptance and negative tests
- Alembic upgrade in fresh PostgreSQL and upgrade of seeded previous schema; verify no `create_all` in production.
- Rollback entire service command on validation, DB or outbox failure; duplicate idempotency key cannot create duplicate project.
- Authorization, typed API errors, basic backend/frontend smoke test.

## Hard restrictions
- Two roles only: Customer and Owner.
- Do not expose real payment, binding manual/automatic quotes, live printing or physical printer controls unless the relevant M16 gate and owner approval exist.
- Keep real-versus-simulated data and payment identities immutable; never fabricate test results or actual Telegram device testing.
- Preserve existing migrations; isolate private models; use transaction/idempotency controls for side effects.

## Completion report
List changed files and schemas, commands run/results, permission and concurrency tests, any blockers, and the next milestone. Stop; do not continue without review.
