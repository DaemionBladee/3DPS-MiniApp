# Codex task template — 3DPS-MiniApp

**Milestone:** M__ — [specific vertical slice]  
**Dependency:** [what is already implemented and tested]  
**Business requirement:** [reference doc heading]  

Read root `AGENTS.md`, the milestone in `docs/MASTER_ROADMAP.md`, and the cross-domain contracts `docs/STATE_MACHINES.md`, `docs/INTEGRITY_RULES.md`, `docs/DEPENDENCY_MATRIX.md` as relevant. Inspect existing source, migrations and tests.

## Objective
[One user-facing outcome]

## Implement
- [Specific API / UI / database change]
- [Security and auth checks]
- [Success/failure/edge cases]
- [Tests and documentation]

## Constraints
- Preserve two-role Customer/Owner MVP.
- No binding quotations of any kind (manual or automatic) until `BINDING_QUOTES_ENABLED` and live gates; automated issuance additionally requires `AUTO_QUOTE_ENABLED` and calibrated hardware.
- Payments owner-verified; assignments owner-approved; reprints owner-reviewed.
- Keep simulation explicitly separated from production.
- No destructive migrations or unrelated architecture changes.

## Acceptance tests
- [Happy path with expected data and state]
- [Unauthorized cross-role/user request denied]
- [Invalid input and stale version refused]
- [Concurrent/idempotent action protected]
- [UI feedback and Telegram message where relevant]

## Completion report
1. Changed files and features
2. Commands executed with passing/failing results
3. Migrations and data risks
4. Known limitations and security considerations
5. Proposed next narrow task

Stop after this scope; don't begin another milestone.
