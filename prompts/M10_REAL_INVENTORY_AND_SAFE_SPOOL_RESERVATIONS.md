# Codex Task M10 — Real inventory and safe spool reservations

**Prerequisites:** M03, M07, M09 implemented and tested.

Read root `AGENTS.md`, the specific milestone in `docs/MASTER_ROADMAP.md`, `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`, and `docs/DEPENDENCY_MATRIX.md`. Also read the relevant documents: `docs/DATA_MODEL.md`, `docs/INTEGRITY_RULES.md`, `docs/STATE_MACHINES.md`.

Inspect the actual repository, code, migrations, tests and Git status. Prepare a small implementation plan, then implement only this milestone. Do not assume a future milestone exists.

## Required implementation
1. Implement materials/variants/spools, immutable signed inventory movement ledger with one-time opening stock, suppliers and audited adjustments.
2. Add item-scoped multiple-spool holds with expiry/firm/release/partial-consumption; integrate genuine stock adapters into M09 printing checkout gate.
3. Provide owner inventory Mini App pages, low-stock alerts and reservation history.
4. Keep real payment disabled until capacity holds M11, printer onboarding and separate launch authorization.

## Acceptance and negative tests
- Two orders racing for last usable grams cannot oversell; expired provisional holds released.
- Consumption and ledger use one physical event; no double-decrement or negative remaining grams.
- No filament reservation on a design stage.

## Hard restrictions
- Two roles only: Customer and Owner.
- Do not expose real payment, binding manual/automatic quotes, live printing or physical printer controls unless the relevant M16 gate and owner approval exist.
- Keep real-versus-simulated data and payment identities immutable; never fabricate test results or actual Telegram device testing.
- Preserve existing migrations; isolate private models; use transaction/idempotency controls for side effects.

## Completion report
List changed files and schemas, commands run/results, permission and concurrency tests, any blockers, and the next milestone. Stop; do not continue without review.
