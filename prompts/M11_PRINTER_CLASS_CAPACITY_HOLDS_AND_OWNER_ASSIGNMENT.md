# Codex Task M11 — Printer-class capacity holds and owner assignment

**Prerequisites:** M06, M09, M10 implemented and tested.

Read root `AGENTS.md`, the specific milestone in `docs/MASTER_ROADMAP.md`, `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`, and `docs/DEPENDENCY_MATRIX.md`. Also read the relevant documents: `docs/DATA_MODEL.md`, `docs/INTEGRITY_RULES.md`, `docs/STATE_MACHINES.md`, `docs/DEPENDENCY_MATRIX.md`.

Inspect the actual repository, code, migrations, tests and Git status. Prepare a small implementation plan, then implement only this milestone. Do not assume a future milestone exists.

## Required implementation
1. Distinguish virtual printer profiles/models from physical printer instances; no physical machine required for simulation.
2. Implement bounded printer-class/time capacity holds to avoid overselling; recheck at checkout, expire, release and reconcile under concurrency.
3. Implement recommendations based on build volume, material/profile compatibility and schedule; owner approves specific physical machine and **non-overlapping planned time window** under transaction/range-exclusion constraints, with reassignment history.
4. Integrate real stock+capacity adapters into checkout service but leave all live gates OFF.

## Acceptance and negative tests
- Concurrent holds for last eligible time slot cannot both succeed; capacity loss after payment enters owner hold.
- No live assignment without compatible actual printer and verified payment; two overlapping approved slots on one printer cannot both persist; virtual assignment simulation-only.
- New assignment cannot modify history or bypass owner.

## Hard restrictions
- Two roles only: Customer and Owner.
- Do not expose real payment, binding manual/automatic quotes, live printing or physical printer controls unless the relevant M16 gate and owner approval exist.
- Keep real-versus-simulated data and payment identities immutable; never fabricate test results or actual Telegram device testing.
- Preserve existing migrations; isolate private models; use transaction/idempotency controls for side effects.

## Completion report
List changed files and schemas, commands run/results, permission and concurrency tests, any blockers, and the next milestone. Stop; do not continue without review.
