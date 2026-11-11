# ADR 0001 — Documentation-only baseline and incremental modular monolith

- Date: 2026-11-11 (Asia/Rangoon)
- Status: **Accepted as the M00 architecture baseline** — owner approval recorded in the M01 start instruction, 2026-11-11 (client date)
- Scope: Architecture/migration direction. The owner separately authorized M01; no live operation or M02 authorization is implied.
- Evidence: [Implementation baseline](../IMPLEMENTATION_BASELINE.md)

## Context

The work/main commit `3a6da2d6df02ea6d10836f0a3a4f6dd4af90ff23`
contains only a title README. Development commit
`d758653d940124760e5cd7e9b02071a9ba3ce805` adds a v1.4 requirements ZIP,
not source. Missing root instructions have been materialized from that ZIP
while preserving the existing README. No working module or supplied database
needs migration today. Specifications do not establish implemented features.

The agreed product has one owner/operator, customers, three service types,
independent paid stages, no physical printers yet, and fail-closed simulation.
The normative state/integrity/dependency documents constrain implementation.

## Baseline decisions

1. **One incremental monorepo/modular monolith.** Use `miniapp/` for the React
   TypeScript Vite app, `backend/app/` for shared domain/application/data services
   with thin FastAPI adapters, `telegram_bot/` for thin Aiogram 3 handlers, and
   `backend/alembic/` for the single migration chain. Add paths when their
   milestone introduces working code; no empty service scaffold in M00.
   The bot does not duplicate business logic; PostgreSQL is authoritative.
2. **Freeze domain boundaries before schema.** Only `customer`/`owner`; no
   operator role. A service project contains separately versioned design/print
   requests, quotes, orders and obligations. Design lines do not require STL,
   spool or printer. Scope controls digital-file entitlement. Exact approved
   design versions create one linked print request idempotently. Printing needs
   its own payment and owner-approved compatible assignment.
3. **Keep estimates, simulated offers and binding offers distinct.** Estimates
   cannot be accepted. Follow the existing quotation vocabulary with a typed
   mapping `simulation_offer -> simulation order/obligation`,
   `binding_offer -> live order/obligation`; this is not permission to convert
   records. Mode is immutable and checked relationally. All live flags default
   off. Manual binding issuance needs the binding gate; automatic issuance also
   needs calibrated standard-print eligibility and the auto gate. M16 manual
   launch and later auto-quote activation require separate evidence/signoff.
4. **One incremental Alembic chain.** M02 creates auth users/sessions and test
   fixtures. M03 adds minimal projects/requests, transition/transaction/audit/
   idempotency/outbox primitives. M04–M12 add their tables as features arrive;
   M05 adds the design-version FK only after its target exists. No production
   `create_all()`, destructive reset or speculative whole-schema migration.
   If an external legacy DB is later supplied, inspect/version/backup it and
   propose a reviewed conversion before applying anything.
5. **Identifiers and API direction.** Propose database-generated UUID primary
   keys for domain/user records exposed as opaque strings, unique bigint
   Telegram IDs separately; sessions use random high-entropy identifiers hashed
   at rest, not a UUID as a credential. Verify UUID generation with the selected
   PostgreSQL version at M02. Same-origin `/api/v1`, Pydantic/OpenAPI and generated
   TS types are the contract source. Propose `currency_code` as canonical wire
   name, decimal-string money, UTC timestamps, bounded pagination and consistent
   `{code, message, details, correlation_id}` errors. Do not hand-copy domain
   DTOs in M01; reconcile listed contract issues before generating their schema.
6. **Integrity belongs in DB plus domain commands.** Use Decimal/NUMERIC,
   currency-specific rounding/integral XTR, immutable credit/stock/audit history,
   FK/check/unique constraints and lock/version/idempotency protection. Protect
   one active **payable** order per project/stage and one obligation per order;
   precise index/status/replacement policy remains D01, not an implemented SQL
   predicate. Credit transaction uniqueness spans obligations. Net verified
   stage funds and owner release are distinct from provider validation.
7. **Honor upstream dependencies.** M03 atomic outbox supports M08 first alerts
   and M13 retry/reporting. M05 scope -> M07 independent design pricing -> M08
   versioned issuance/acceptance -> M09 atomic order/obligation -> M12 delivery.
   M04 durable pending analysis is not M06 execution. M09 mock stock/capacity
   can authorize simulation only; M10 real spool and M11 real capacity holds
   must both be integrated before live printing checkout. Later physical
   assignment is owner-approved; settlement/resource loss enters audited hold.
8. **Private processing and deployment boundaries.** Raw Telegram initData is
   verified server-side; provision owner explicitly, use revocable secure
   sessions/CSRF/Origin checks and resource authorization. Quarantine uploads
   and authenticate downloads. Isolate bounded parsers/slicers without DB/bot
   credentials or printer network. Trusted backend commits sanitized results.
   Gateway-only public HTTPS, private PostgreSQL/storage/queue; Compose is an
   optional local runtime and Linux VPS/Caddy a later hosting target. Cloud
   tasks are isolated checkouts, not permanent hosting; reuse the existing
   checkout, with no worktree needed. No unattended physical printer start.

## Alternatives and consequences

- Reusing a starter would preserve working code, but none was found; do not
  fabricate a migration/rewrite project or search unrelated repositories.
- Microservices/Kubernetes add deployment and consistency costs with no current
  need; modular services preserve future separation without that complexity.
- A full schema in M03 or independent bot DB would break incremental milestone
  ownership and transaction guarantees. Shared services and one migration chain
  require disciplined boundaries and real PostgreSQL integration/race tests.
- UI-only gates, paid booleans and shared cross-stage totals cannot enforce the
  financial and simulation invariants. DB constraints alone also cannot express
  all cross-entity actor/version/guard rules; transactional commands and negative
  tests are required.
- This ADR freezes baseline direction, not arbitrary pricing, provider, legal,
  hardware, queue implementation, tool versions or policy values. Those remain
  in [OPEN_DECISIONS.md](../OPEN_DECISIONS.md). D01–D08 include remaining
  state/schema and milestone-boundary details; D09–D10 track architecture
  approval and tooling/auth choices. Normative source files are not silently
  rewritten.

## Validation and acceptance

M00 validation is repository/branch/archive inventory and documentation/config
consistency, not app tests. No endpoints, migrations, services or financial
operations were created. The owner accepted this ADR and the migration direction
in the M01 start instruction; individual open decisions still need review by
their stated deadlines. Test schema/UUID/auth choices
in M02, transaction/OpenAPI/outbox choices in M03 and later domain invariants in
their owning milestones. M00 does not claim a working app or passed release gate.
