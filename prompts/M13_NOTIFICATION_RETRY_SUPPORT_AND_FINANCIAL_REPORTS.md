# Codex Task M13 — Notification retry, support and financial reports

**Prerequisites:** M03 outbox, M08, M09–M12 implemented and tested.

Read root `AGENTS.md`, the specific milestone in `docs/MASTER_ROADMAP.md`, `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`, and `docs/DEPENDENCY_MATRIX.md`. Also read the relevant documents: `docs/ARCHITECTURE.md`, `docs/INTEGRITY_RULES.md`, `docs/PRODUCT_SPEC.md`.

Inspect the actual repository, code, migrations, tests and Git status. Prepare a small implementation plan, then implement only this milestone. Do not assume a future milestone exists.

## Required implementation
1. Extend the same M03 outbox to retry/backoff/dead-letter and subscriber preferences; never create a competing event system.
2. Implement customer milestones, owner priority alerts and authorized support links with no sensitive public information.
3. Create owner revenue/payment/credit/refund reports per currency, inventory consumption/cost reporting, and simulated-vs-live separation.
4. Instrument critical events and delivery errors with correlation IDs and sensitive data redaction.

## Acceptance and negative tests
- Duplicate provider/event notification retries do not mutate domain state.
- Customer cannot access owner reports or another customer notification.
- Revenue reports exclude simulated money and cross-currency addition.

## Hard restrictions
- Two roles only: Customer and Owner.
- Do not expose real payment, binding manual/automatic quotes, live printing or physical printer controls unless the relevant M16 gate and owner approval exist.
- Keep real-versus-simulated data and payment identities immutable; never fabricate test results or actual Telegram device testing.
- Preserve existing migrations; isolate private models; use transaction/idempotency controls for side effects.

## Completion report
List changed files and schemas, commands run/results, permission and concurrency tests, any blockers, and the next milestone. Stop; do not continue without review.
