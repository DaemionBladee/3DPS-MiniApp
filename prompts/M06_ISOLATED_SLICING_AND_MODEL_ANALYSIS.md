# Codex Task M06 — Isolated slicing and model analysis

**Prerequisites:** M03 and M04 implemented and tested.

Read root `AGENTS.md`, the specific milestone in `docs/MASTER_ROADMAP.md`, `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`, and `docs/DEPENDENCY_MATRIX.md`. Also read the relevant documents: `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, `docs/SECURITY.md`, `docs/DEPENDENCY_MATRIX.md`.

Inspect the actual repository, code, migrations, tests and Git status. Prepare a small implementation plan, then implement only this milestone. Do not assume a future milestone exists.

## Required implementation
1. Create versioned virtual printer model and approved slicer profile registry (no physical machines necessary).
2. Implement durable processing-task leases/retries and isolated worker processing of validated uploads, with bounded CPU/RAM/disk/time/logs and no Telegram token/DB/printer credentials in worker.
3. Parse and validate PrusaSlicer results with model checksum and profile/version provenance, customer dimension/unit confirmation, failure statuses.
4. Provide safe analysis endpoints; uncertain inputs route to manual review and never silently quote.

## Acceptance and negative tests
- Known fixtures have repeatable profile-specific grams/seconds; malformed files, timeout and partial outputs fail closed.
- Worker cannot access privileged credentials or network; duplicate task delivery is idempotent.
- Physical-printer table can be empty.

## Hard restrictions
- Two roles only: Customer and Owner.
- Do not expose real payment, binding manual/automatic quotes, live printing or physical printer controls unless the relevant M16 gate and owner approval exist.
- Keep real-versus-simulated data and payment identities immutable; never fabricate test results or actual Telegram device testing.
- Preserve existing migrations; isolate private models; use transaction/idempotency controls for side effects.

## Completion report
List changed files and schemas, commands run/results, permission and concurrency tests, any blockers, and the next milestone. Stop; do not continue without review.
