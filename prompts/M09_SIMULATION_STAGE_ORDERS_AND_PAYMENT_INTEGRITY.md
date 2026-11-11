# Codex Task M09 — Simulation stage orders and payment integrity

**Prerequisites:** M08 implemented and tested.

Read root `AGENTS.md`, the specific milestone in `docs/MASTER_ROADMAP.md`, `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`, and `docs/DEPENDENCY_MATRIX.md`. Also read the relevant documents: `docs/PAYMENTS_COMPLIANCE.md`, `docs/DATA_MODEL.md`, `docs/INTEGRITY_RULES.md`, `docs/STATE_MACHINES.md`.

Inspect the actual repository, code, migrations, tests and Git status. Prepare a small implementation plan, then implement only this milestone. Do not assume a future milestone exists.

## Required implementation
1. Implement separate design/print stage orders, obligations, attempts, immutable verified payment credits, refunds and owner release verification.
2. Implement idempotent Stars sandbox invoice/pre-checkout/successful-payment ingestion; validate exact user/category/amount/currency, preserve owner release requirement; manual evidence is permitted only for approved physical goods.
3. Provide mock stock/capacity hold adapter for simulation printing checkout only; live physical checkout impossible before M10/M11.
4. Implement explicit `on_hold`, `refund_pending`, `refunded` state guards, transaction reference uniqueness, multi-currency separation.

## Acceptance and negative tests
- One provider charge/bank transaction cannot credit two obligations, even concurrently; duplicates never double-credit.
- Partial payment, screenshot, mismatched currency/buyer, invalid hold cannot release stage.
- Design-only simulation paid stage needs no filament/printer; no live checkout flags enabled.

## Hard restrictions
- Two roles only: Customer and Owner.
- Do not expose real payment, binding manual/automatic quotes, live printing or physical printer controls unless the relevant M16 gate and owner approval exist.
- Keep real-versus-simulated data and payment identities immutable; never fabricate test results or actual Telegram device testing.
- Preserve existing migrations; isolate private models; use transaction/idempotency controls for side effects.

## Completion report
List changed files and schemas, commands run/results, permission and concurrency tests, any blockers, and the next milestone. Stop; do not continue without review.
