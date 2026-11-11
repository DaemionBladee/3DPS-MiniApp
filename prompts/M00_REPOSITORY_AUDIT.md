# Codex Task M00 — Audit and baseline the existing 3DPS-MiniApp repository

Read repository-root `AGENTS.md`, `docs/MASTER_ROADMAP.md`, `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md` and `docs/DEPENDENCY_MATRIX.md`, then inspect all existing source files and Git status before changing anything.

## Goal
Produce a reliable, migration-safe implementation plan for the **existing codebase** (possibly with earlier Telegram bot or Mini App bootstrap examples). Don't assume docs describe implemented behavior.

## Do
1. Inventory existing Python bot/API, frontend, Docker services, schemas, tests and authentication.
2. Identify conflicts between old starter code and the agreed **two-role Customer/Owner** and **Level 2** business policies.
3. Find security issues, incomplete demo logic, placeholders, missing Alembic migrations and secrets exposure.
4. Propose a minimal monorepo path preserving working modules. Distinguish `existing`, `prototype`, `missing`, `unsafe`, and `needs migration` features.
5. Document API schema direction, database migration strategy, deployment environment and testing gaps.
6. **Create** `docs/IMPLEMENTATION_BASELINE.md` with audit findings and decisions; **create** `docs/adr/0001-project-baseline.md` with key design choices. These two files are expected M00 outputs and are not supplied in this instruction package.
7. Review and update `docs/OPEN_DECISIONS.md`; do not invent values for undecided pricing, printer models, legal classification or provider availability.
8. Provide a prioritized, scoped M01 task plan and required preconditions for M02/M03. Record the **M03 transactional outbox -> M08 notifications** dependency, **M05 scoping -> M07/M08 quotation** dependency, and **M09 simulated stock/capacity holds -> M10 spool reservation + M11 capacity holds** contract. Identify design service line items, payment-credit uniqueness, and cross-stage order invariants. Do not assume these later modules already exist.

## Do not
- Do not build the rest of the app, rewrite the repository wholesale, run destructive migrations, drop DB data, enable live payments/quotes, connect physical printers, or change the product policy.
- Do not invent tests or claim functionality as implemented without inspecting/running it.
- Do not commit unless asked.

## Acceptance
Report current file tree, architecture gaps, risk register, file-level recommendations, tests that ran with actual outputs, and next M01 task. Stop for review.
