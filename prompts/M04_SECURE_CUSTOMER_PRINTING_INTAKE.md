# Codex Task M04 — Secure customer printing intake

**Prerequisites:** M03 implemented and tested.

Read root `AGENTS.md`, the specific milestone in `docs/MASTER_ROADMAP.md`, `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`, and `docs/DEPENDENCY_MATRIX.md`. Also read the relevant documents: `docs/DATA_MODEL.md`, `docs/SECURITY.md`, `docs/API_CONTRACTS.md`, `docs/FRONTEND_SPEC.md`.

Inspect the actual repository, code, migrations, tests and Git status. Prepare a small implementation plan, then implement only this milestone. Do not assume a future milestone exists.

## Required implementation
1. Implement customer printing request wizard, persisted drafts, per-file and per-item specs, server-side validation and item quantities.
2. Create private quarantine uploads, content/size/archive limits, owner/cross-customer access checks, and generated storage keys.
3. Create durable `processing_tasks` in `pending` state; do NOT claim slicing starts until M06 is implemented.
4. Implement request revision and canonical specification hashing; resubmission and changed files supersede stale downstream approvals.

## Acceptance and negative tests
- Customer can resume draft and submit multi-file request; duplicate submission creates only one revision.
- Malformed/oversize/unsafe archives rejected; arbitrary file ID cannot be accessed by a second customer.
- Worker pending != analyzed; quote and checkout not exposed.

## Hard restrictions
- Two roles only: Customer and Owner.
- Do not expose real payment, binding manual/automatic quotes, live printing or physical printer controls unless the relevant M16 gate and owner approval exist.
- Keep real-versus-simulated data and payment identities immutable; never fabricate test results or actual Telegram device testing.
- Preserve existing migrations; isolate private models; use transaction/idempotency controls for side effects.

## Completion report
List changed files and schemas, commands run/results, permission and concurrency tests, any blockers, and the next milestone. Stop; do not continue without review.
