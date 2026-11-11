# Codex Task M15 — Controlled HTTPS staging/production infrastructure

**Prerequisites:** M14 implemented and tested.

Read root `AGENTS.md`, the specific milestone in `docs/MASTER_ROADMAP.md`, `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`, and `docs/DEPENDENCY_MATRIX.md`. Also read the relevant documents: `docs/DEVOPS.md`, `docs/SECURITY.md`, `docs/OPEN_DECISIONS.md`.

Inspect the actual repository, code, migrations, tests and Git status. Prepare a small implementation plan, then implement only this milestone. Do not assume a future milestone exists.

## Required implementation
1. Configure dedicated VPS/HTTPS/Caddy, private Docker networking, deployment manifests, secrets, health monitoring and tested backups.
2. Connect a separate production bot/Mini App URL only with authorized BotFather configuration and real-device validation.
3. Offer at most an invitation-only *nonpayable* intake/waitlist before hardware; ensure simulation data are not presented to real customers as live obligations.
4. Manual deployment approval and rollback plan; no direct Codex Cloud production access without owner permission.

## Acceptance and negative tests
- Only HTTPS gateway exposed; no public DB/Redis/workers or printer ports.
- Telegram Android/iOS/Desktop checks actually run or explicitly pending.
- All live flags off; backend rejects attempts to collect live payment or issue binding quote.

## Hard restrictions
- Two roles only: Customer and Owner.
- Do not expose real payment, binding manual/automatic quotes, live printing or physical printer controls unless the relevant M16 gate and owner approval exist.
- Keep real-versus-simulated data and payment identities immutable; never fabricate test results or actual Telegram device testing.
- Preserve existing migrations; isolate private models; use transaction/idempotency controls for side effects.

## Completion report
List changed files and schemas, commands run/results, permission and concurrency tests, any blockers, and the next milestone. Stop; do not continue without review.
