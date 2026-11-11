# Codex Task M16 — Hardware calibration and safe manual live launch

**Prerequisites:** M15, hardware, payment policy signoff implemented and tested.

Read root `AGENTS.md`, the specific milestone in `docs/MASTER_ROADMAP.md`, `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`, and `docs/DEPENDENCY_MATRIX.md`. Also read the relevant documents: `docs/OPEN_DECISIONS.md`, `docs/SECURITY.md`, `docs/PAYMENTS_COMPLIANCE.md`, `docs/DEPENDENCY_MATRIX.md`.

Inspect the actual repository, code, migrations, tests and Git status. Prepare a small implementation plan, then implement only this milestone. Do not assume a future milestone exists.

## Required implementation
1. Onboard owned physical printers, real compatible materials and stock, calibrate slicer/quality/time/cost profiles with repeat prints.
2. Complete local workshop safety plan; never expose unattended automatic printer starts.
3. Validate category-specific payment provider and delivery policy, dry-run full charge/credit/QC/receipt/refund and physical capacity holds.
4. Enable **manual binding quotes and owner-approved low-risk physical print orders first** after signoff, then separately consider Level-2 auto-quote enablement based on evidence.

## Acceptance and negative tests
- No live request can charge/pay or print on uncalibrated profiles or without owner-controlled assignment.
- One manual real end-to-end order finishes with reconciled funds, filament, QC and handover.
- Level-2 auto-quote remains OFF until a separate signed decision.

## Hard restrictions
- Two roles only: Customer and Owner.
- Do not expose real payment, binding manual/automatic quotes, live printing or physical printer controls unless the relevant M16 gate and owner approval exist.
- Keep real-versus-simulated data and payment identities immutable; never fabricate test results or actual Telegram device testing.
- Preserve existing migrations; isolate private models; use transaction/idempotency controls for side effects.

## Completion report
List changed files and schemas, commands run/results, permission and concurrency tests, any blockers, and the next milestone. Stop; do not continue without review.
