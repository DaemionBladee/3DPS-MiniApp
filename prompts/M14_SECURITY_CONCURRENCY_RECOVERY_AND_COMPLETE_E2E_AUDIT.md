# Codex Task M14 — Security, concurrency, recovery and complete E2E audit

**Prerequisites:** M02–M13 implemented and tested.

Read root `AGENTS.md`, the specific milestone in `docs/MASTER_ROADMAP.md`, `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`, and `docs/DEPENDENCY_MATRIX.md`. Also read the relevant documents: `docs/SECURITY.md`, `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`, `docs/DEPENDENCY_MATRIX.md`.

Inspect the actual repository, code, migrations, tests and Git status. Prepare a small implementation plan, then implement only this milestone. Do not assume a future milestone exists.

## Required implementation
1. Run threat model and negative auth/file/CSRF payment/owner-action tests; verify worker isolation with real sandbox constraints.
2. Run PostgreSQL concurrency and idempotency tests for last-spool and last-capacity reservations, duplicate orders and reused payment credits.
3. Exercise full simulated print and design+print lifecycle, including partial QC, fails, refunds, design delivery, timeouts and version conflicts.
4. Run DB + private-file backup/restore drills, migration upgrade tests, scan dependencies/images and document unresolved findings.

## Acceptance and negative tests
- No critical security finding left open for staging release.
- Restore succeeds in isolated staging from encrypted backups; authorization tests pass.
- All simulation/live gates fail closed.

## Hard restrictions
- Two roles only: Customer and Owner.
- Do not expose real payment, binding manual/automatic quotes, live printing or physical printer controls unless the relevant M16 gate and owner approval exist.
- Keep real-versus-simulated data and payment identities immutable; never fabricate test results or actual Telegram device testing.
- Preserve existing migrations; isolate private models; use transaction/idempotency controls for side effects.

## Completion report
List changed files and schemas, commands run/results, permission and concurrency tests, any blockers, and the next milestone. Stop; do not continue without review.
