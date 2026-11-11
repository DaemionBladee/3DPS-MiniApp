# Codex Task M07 — Design and print pricing plus Level-2 eligibility

**Prerequisites:** M05 and M06 implemented and tested.

Read root `AGENTS.md`, the specific milestone in `docs/MASTER_ROADMAP.md`, `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`, and `docs/DEPENDENCY_MATRIX.md`. Also read the relevant documents: `docs/BUSINESS_RULES.md`, `docs/INTEGRITY_RULES.md`, `docs/DATA_MODEL.md`, `docs/PAYMENTS_COMPLIANCE.md`.

Inspect the actual repository, code, migrations, tests and Git status. Prepare a small implementation plan, then implement only this milestone. Do not assume a future milestone exists.

## Required implementation
1. Implement deterministic Decimal/NUMERIC cost calculations and immutable policy/version snapshots, including shipping/tax or explicit unknown safeguards.
2. Implement manual design-service pricing based on scoped deliverables/revision policy and configured XTR/digital category when applicable; no slicer/filament dependency.
3. Implement printing Level-2 eligibility fail-closed rules: material, quality, stock availability adapter, geometry, time, size, deadline, customer requirements and quote cap.
4. Separate nonbinding `test_estimates`, `simulation_offers`, and future `binding_offers`; `BINDING_QUOTES_ENABLED` and `AUTO_QUOTE_ENABLED` default off; no live issuing or payment.

## Acceptance and negative tests
- Currency-specific rounding, zero/missing inputs, unsafe model, out-of-stock and unknown cause review.
- Design quote calculations do not require print_items; cross-currency sums prohibited.
- Simulation offer cannot be promoted by toggling flags.

## Hard restrictions
- Two roles only: Customer and Owner.
- Do not expose real payment, binding manual/automatic quotes, live printing or physical printer controls unless the relevant M16 gate and owner approval exist.
- Keep real-versus-simulated data and payment identities immutable; never fabricate test results or actual Telegram device testing.
- Preserve existing migrations; isolate private models; use transaction/idempotency controls for side effects.

## Completion report
List changed files and schemas, commands run/results, permission and concurrency tests, any blockers, and the next milestone. Stop; do not continue without review.
