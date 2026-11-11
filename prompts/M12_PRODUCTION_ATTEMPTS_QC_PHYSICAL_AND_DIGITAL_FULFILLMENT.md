# Codex Task M12 — Production attempts, QC, physical and digital fulfillment

**Prerequisites:** M11 and M05 implemented and tested.

Read root `AGENTS.md`, the specific milestone in `docs/MASTER_ROADMAP.md`, `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`, and `docs/DEPENDENCY_MATRIX.md`. Also read the relevant documents: `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`, `docs/PRODUCT_SPEC.md`.

Inspect the actual repository, code, migrations, tests and Git status. Prepare a small implementation plan, then implement only this milestone. Do not assume a future milestone exists.

## Required implementation
1. Implement owner-run job lifecycle and accurate unit-level partial output, linked reprint attempts, failures and immutable waste/filament records.
2. Require owner decision before reprint, ensure units QC passed sum to order quantity (without double counting retries).
3. Implement physical pickup/delivery handover independently of digital design file release.
4. Implement secure `design_deliveries` only when the approved design-stage scope promises downloadable files; require correct paid design order and exact approved immutable design version. Design+print need not transfer CAD/STL files unless agreed.

## Acceptance and negative tests
- Print failure creates no automatic reprint; partial QC does not fulfill order prematurely.
- Design-only paid and approved order delivers without physical printer; unpaid design file download denied.
- Double consumption, fake delivery and unauthorized reprint denied.

## Hard restrictions
- Two roles only: Customer and Owner.
- Do not expose real payment, binding manual/automatic quotes, live printing or physical printer controls unless the relevant M16 gate and owner approval exist.
- Keep real-versus-simulated data and payment identities immutable; never fabricate test results or actual Telegram device testing.
- Preserve existing migrations; isolate private models; use transaction/idempotency controls for side effects.

## Completion report
List changed files and schemas, commands run/results, permission and concurrency tests, any blockers, and the next milestone. Stop; do not continue without review.
