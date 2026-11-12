# System architecture and implementation boundaries

## Implemented M05 design slice

M05 extends the same modular monolith and M04 storage services. New design briefs,
immutable scope/proof histories, exact-version reviews and combined-stage lineage
are documented in [ADR 0005](adr/0005-design-intake-and-lineage.md) and
[DESIGN_INTAKE.md](DESIGN_INTAKE.md). Preview/reference validation adds pinned
Pillow; credentials/descriptors are cleared in the bounded parser subprocess.
No worker execution, real quote/payment or digital release is introduced.


M04 extends the modular monolith with private printing intake. See
[ADR 0004](adr/0004-private-printing-intake.md), [PRINTING_INTAKE.md](PRINTING_INTAKE.md)
and [the implementation report](M04_IMPLEMENTATION_REPORT.md). M02 authentication
and M03 transaction primitives remain in use. A bounded validation subprocess
checks structure; durable model-analysis tasks stay pending. No queue consumer,
slicer, notification delivery or commercial service is introduced.

## Target runtime (single monorepo; modular monolith)
```
Telegram client / BotFather
   |  bot menu + notifications
   v
React+TypeScript Mini App (customer/owner)
   | same-origin HTTPS `/api/v1/*`
   v
Caddy HTTPS gateway --> FastAPI application (auth, domain services)
                            |        |             |
                            v        v             v
                        PostgreSQL  Private files  Queue / Outbox
                                                   |
                                                   v
                                         Isolated slicer/analysis worker
                                                   |
                                           Versioned virtual profiles

Aiogram long-polling bot -> FastAPI/domain services + notification outbox
Future: owner-approved production plan -> secured workshop agent -> physical printers
```

The bot **must not** duplicate quotation, stock, approval or payment business logic; shared Python services own it. For Stars digital checkout, the bot receives and validates Telegram payment updates through a dedicated shared payment adapter; do not reuse manual receipt-verification handling. Bot may notify users through Telegram and open Mini App deep links. No remote/unattended physical printing in MVP.

## Recommended monorepo target (adapt existing code, do not blindly replace)
```
3DPS-MiniApp/
  AGENTS.md
  docs/                 # product, rules, architecture, data, API, security, operations
  miniapp/
    src/
      app/              # providers, router, shell
      pages/            # route-level composition
      features/         # requests, quotes, approvals, payments, orders, inventory, printers
      components/       # ui primitives/shared cards/dialogs
      integrations/telegram/
      lib/api/          # generated types, clients, errors, query cache
      lib/auth/
      hooks/ stores/ styles/
    tests/
  backend/
    app/
      api/v1/           # request/response adapters; deps
      core/             # configuration, auth, logging
      domain/           # entities/types/status transitions
      services/         # application use cases
      repositories/     # data access
      database/         # SQLAlchemy models/sessions
      workers/          # model/slicer tasks
      integrations/     # Telegram/slicer/storage adapters
    alembic/
    tests/
  telegram_bot/          # Aiogram bot handler adapters (Python-importable package name)
  deploy/               # Caddy, Compose, deployment configs
  tests/e2e/
  compose.yaml
  .env.example
```

Do not expose an unsupported empty tree as a working service. Add packages incrementally; favor a shared Python library inside backend for bot and API use cases.

## Layer responsibilities
- React: forms, validated user input, file upload progress, drafts, accessibility, Telegram theme/back button, authorized display. No authoritative pricing/business decisions.
- FastAPI: signature/session verification, authorization, API validation, command orchestration, safe file access, state transitions, transactions and auditing.
- SQLAlchemy/PostgreSQL: durable relational state and integrity, immutable ledger/history, constraints and concurrency.
- Worker: scan/parse uploaded files; geometry analysis; run a pinned slicer/profile with CPU/RAM/time bounds and zero printer-network reach; save analysis and status in DB via restricted interface.
- Aiogram: Telegram update handling, launch links, notifications and customer support routing; domain calls reuse backend services.
- Caddy: public TLS and same-origin routing; static Mini App under `/`, API under `/api/`.
- Future workshop agent: separate authenticated outbound connection to cloud; operator-approved local execution and printer safety controls.

## Frontend architectural guidance
- Use typed REST via FastAPI OpenAPI -> generated TypeScript types; server response defines actions/permissions but backend still rechecks.
- TanStack Query for server state, React Hook Form/Zod for inputs, local state only for UI; persisted drafts live in backend.
- Route-level error boundary, loading/empty/offline states, stable status display across roles.
- Current environment may have a bare prototype using `create_all`; migrate with Alembic before production.

## Cross-cutting service-project and payment modes
- `service_projects` groups printing/design/combined requests without merging their stage orders or currencies. Design+print has separate quote, order and payment obligation for each stage. `source_design_version_id` ties the single derived print request to an approved design; design service/quote/order items require no fake STL; delivered digital files use private `design_deliveries`.
- `test_estimate` is informational; `simulation_offer` supports simulation-only acceptance and mock payments; `binding_offer` exists only when `BINDING_QUOTES_ENABLED` and live commercial/category gates permit. Store mode on every relevant quote/order/payment record; never promote simulation rows to live by changing config flags. A **design-only** paid stage requires verified design payment and approved scope, but no spool reservation or printer assignment. A **printing** paid stage requires stock/capacity readiness before checkout and owner-approved printer assignment before production.
- For digital goods/services sold inside Telegram, use Telegram Stars (`XTR`); physical prints have separately approved payment methods. See `docs/PAYMENTS_COMPLIANCE.md`.
- Telegram deep links are navigation hints, **not bearer authorization**. Validate session, resource ownership and every owner permission in FastAPI.

## Background processing workflow
1. Upload raw file to quarantine with generated key; register owner and MIME/magic/size/checksum.
2. Worker retrieves restricted input; validate STL/3MF/OBJ, archive expansion, geometry and dimensions; require customer unit confirmation where ambiguous.
3. M04 can persist an analysis task as `pending` (not yet processed); M06 introduces durable worker dispatch, lease/retry and status updates. Slicer adapter resolves approved printer/material/profile versions; executes bounded isolated process without shell injection.
4. Parse output using version-specific parser and validation, keep stderr/errors/provenance, discard dangerous files; emit a sanitized job result to a restricted queue or internal result endpoint. **The slicer worker must not require PostgreSQL or Telegram bot credentials**; the trusted backend consumer commits results.
5. Pricing and eligibility evaluate in backend. Failed/ambiguous tasks route to owner review. Never assume success from a partial subprocess result.

## Cross-service events
Examples: `request.submitted`, `analysis.completed`, `review.requested`, `quotation.issued`, `quote.accepted`, `payment.evidence_received`, `payment.verified`, `assignment.approved`, `job.failed`, `qc.passed`, `order.fulfilled`.
Write domain change + outbox in one DB transaction, deliver Telegram alerts asynchronously, use idempotent processing. **Introduce the outbox table and atomic write API in M03**, use it for the first review/quote notifications in M08, and build full retry/dead-letter/suppression and reporting in M13. Do not send a notification as the only evidence of a committed business change.

## Technical design choices
- JSON REST first; no GraphQL or WebSockets until necessary. Poll active panels 15–30 seconds; Telegram messages for urgent alerts.
- Bot long polling initially (no inbound webhook); if webhooks added later, verify webhook secrets and avoid duplicate processing.
- Same-origin production eliminates cross-origin cookie complexity. Vite `/api` proxy in development.
- Local dev on CachyOS uses Docker Compose, React can run in Docker or on host; do not bind internal services to public interfaces unnecessarily.
- Use virtual printer profile for cost simulation; physical printer asset represents an actual owned device and operational state.

## Implemented M06 analysis boundary

The trusted `backend/app/analysis` controller claims PostgreSQL tasks, streams a
verified private input to an isolated temporary directory and launches the pinned
`worker/Dockerfile` image by immutable digest. The API container has no Docker
socket and never imports or executes geometry/slicing code. Only pure numeric
profile definitions are shared. Each unprivileged, read-only, network-free worker
receives model bytes and unit/dimension/profile settings, without customer text or
credentials. It returns bounded typed JSON; publication validates provenance and
lease fencing before atomically saving immutable analysis/run, state, audit and
outbox records. G-code stays in ephemeral scratch. See
[ADR 0006](adr/0006-isolated-simulation-analysis.md),
[operations](WORKER_OPERATIONS.md) and [profiles](SLICER_PROFILES.md).

## M07 implementation boundary

M07 adds simulation pricing and fail-closed candidate eligibility inside the existing backend. Immutable policy/availability/estimate/line records and private Owner projections are described in [PRICING_POLICIES.md](PRICING_POLICIES.md) and [ADR 0007](adr/0007-simulation-pricing-and-eligibility.md). No quote acceptance or payment service is introduced.
