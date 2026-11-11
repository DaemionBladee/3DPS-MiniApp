# Codex Task M05 — Design intake and combined-stage lineage

**Prerequisites:** M03 and M04 implemented and tested.

Read root `AGENTS.md`, the specific milestone in `docs/MASTER_ROADMAP.md`, `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`, and `docs/DEPENDENCY_MATRIX.md`. Also read the relevant documents: `docs/PRODUCT_SPEC.md`, `docs/DATA_MODEL.md`, `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`.

Inspect the actual repository, code, migrations, tests and Git status. Prepare a small implementation plan, then implement only this milestone. Do not assume a future milestone exists.

## Required implementation
1. Implement design brief, scope and revision policy; design stages without fake STL or print items.
2. Create versioned immutable design proof files and customer review of the exact published version.
3. Generate at most one linked printing-stage request per approved design version/project, storing `source_design_version_id`, using idempotent transactional creation.
4. Use simulation-only payment/quote fixtures for demonstrating proof workflow; do not implement real design work release prior to M08/M09.

## Acceptance and negative tests
- Design-only project with zero print items passes validation; print request still needs at least one print item.
- Old proof approval cannot approve newer version; simultaneous conversion creates only one linked print request.
- Design stage payment cannot authorize manufacturing.

## Hard restrictions
- Two roles only: Customer and Owner.
- Do not expose real payment, binding manual/automatic quotes, live printing or physical printer controls unless the relevant M16 gate and owner approval exist.
- Keep real-versus-simulated data and payment identities immutable; never fabricate test results or actual Telegram device testing.
- Preserve existing migrations; isolate private models; use transaction/idempotency controls for side effects.

## Completion report
List changed files and schemas, commands run/results, permission and concurrency tests, any blockers, and the next milestone. Stop; do not continue without review.
