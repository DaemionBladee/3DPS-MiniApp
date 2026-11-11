# Codex Task M08 — Owner review, versioned offer acceptance and notifications

**Prerequisites:** M07 and M03 outbox implemented and tested.

Read root `AGENTS.md`, the specific milestone in `docs/MASTER_ROADMAP.md`, `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`, and `docs/DEPENDENCY_MATRIX.md`. Also read the relevant documents: `docs/BUSINESS_RULES.md`, `docs/API_CONTRACTS.md`, `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`.

Inspect the actual repository, code, migrations, tests and Git status. Prepare a small implementation plan, then implement only this milestone. Do not assume a future milestone exists.

## Required implementation
1. Implement owner-only review/clarify/revise/reject with immutable spec hash and exact quotation version approval.
2. Implement simulation offer issuance, customer acceptance/decline/change, quote expiry/supersession and one accepted quote-version guard. M08 records acceptance only; **M09 must atomically create the order + stage obligation** on first order materialization.
3. Add owner review and customer quote React pages; redact cost/margin for customers.
4. Deliver first private bot notification using M03 transactional outbox, authorized deep-link navigation and idempotent delivery.

## Acceptance and negative tests
- Customer cannot perform owner decisions or read another user quote.
- Two quote versions accepted concurrently produce at most one accepted version; stale/expired rejected. M09 covers resulting order uniqueness.
- Outbox stays correct on DB rollback and Telegram retry.

## Hard restrictions
- Two roles only: Customer and Owner.
- Do not expose real payment, binding manual/automatic quotes, live printing or physical printer controls unless the relevant M16 gate and owner approval exist.
- Keep real-versus-simulated data and payment identities immutable; never fabricate test results or actual Telegram device testing.
- Preserve existing migrations; isolate private models; use transaction/idempotency controls for side effects.

## Completion report
List changed files and schemas, commands run/results, permission and concurrency tests, any blockers, and the next milestone. Stop; do not continue without review.
