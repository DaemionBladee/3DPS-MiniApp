# 3DPS-MiniApp — Master Project Roadmap

**Version:** 1.4 (cross-domain logic and dependency audit) — 2026-11-11  
**Target:** Telegram-first 3D printing and custom design service; two Mini App roles (Customer, Owner).  
**Current phase:** Pre-hardware. Use virtual printer profiles and simulated payments/production until validated.

## 0. Non-negotiable project decisions

- One Telegram bot, one React + TypeScript Mini App, one Python business backend, one PostgreSQL database.
- Roles in MVP: **Customer** and **Owner**; owner performs operator duties. Design permissions to allow future staff roles without creating an operator UI now.
- Services: printing existing models, custom design, and design + printing.
- Level 2 quotations: automatic **final** quotes for strictly eligible standard printing requests **only after hardware/profile calibration**; special orders get owner review. Before that, development estimates are explicitly **non-binding**.
- 100% payment before the corresponding stage begins; payments owner-verified. Combined design + printing may require separate fully paid design and print phases.
- Owner must approve printer assignments; failed jobs require owner review before reprints.
- Filament tracked by material variant/spool with reservations, movements and actual consumption.
- Customer/owner management primarily inside Telegram Mini App; bot sends alerts/deep links.
- Never expose database or printer controls publicly; separate uploaded-model processing from API/bot.

## 1. Target architecture

```
Telegram bot (Aiogram, long polling)
  |  launch button / notifications / deep links
  v
Telegram Mini App (React + TypeScript + Vite; customer + owner)
  |  same-origin HTTPS /api/v1
  v
Caddy reverse proxy -> FastAPI (auth, domain services, permissions)
                         |                  |
                         v                  v
                 PostgreSQL          Private file storage
                         |                  |
                         +------> Background job queue
                                      |
                                      v
                            Isolated model/slicer worker
                                      |
                              Virtual printer profiles

Future hardware: owner-approved jobs -> secured workshop agent -> actual printers
```

**Repository guidance:** Keep a monorepo; reuse/adapt the existing `3DPS-MiniApp` and Mini App bootstrap work. Audit it first. The prior starter is a prototype, not a production baseline. Backend is a modular monolith, not microservices.

## 2. Milestones and acceptance gates

All milestones are scoped to be small enough for Codex to complete in reviewed PRs. A milestone is complete only when its acceptance checks pass; do not accept a plausible-looking UI without connected APIs and tests.

### M00 — Audit and freeze project contracts
**Dependency:** None  
**Deliverables:** Repository audit, approved `AGENTS.md`, `docs/PRODUCT_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/BUSINESS_RULES.md`, updated `docs/OPEN_DECISIONS.md`, ADR folder, updated `.env.example`, risk register. Map old starter files and decide what to keep.  
**Acceptance:** Owner and customer roles; Level-2 rules; design-vs-print payment stages; status transitions and simulation restrictions documented. No unreviewed destructive schema changes.

### M01 — Mini App React foundation
**Dependency:** M00  
**Deliverables:** React + TypeScript + Vite; Tailwind; shadcn/ui components; React Router; TanStack Query; responsive app shell; Telegram theme/safe-area/back-button integration; two role-shell mock dashboards; Vitest/RTL/Playwright baseline.  
**Acceptance:** App renders in a simulated browser viewport for mobile/desktop, supports light/dark mode, typecheck/lint/tests/build all pass; no mock identities in production build. Telegram in-app device testing is scheduled for M02/G1.

### M02 — Telegram launch, authentication and role security
**Dependency:** M01  
**Deliverables:** BotFather Menu/Main Mini App URL and launch button (or documented owner action if credentials unavailable), development HTTPS test plan, signed raw Telegram `initData` verification in FastAPI, **minimal Alembic-managed user/session schema and DB test fixture owned by M02**, explicitly provisioned owner ID, short-lived secure server-side sessions, CSRF protection, **owner-only API and user-scoped auth fixtures**, logout. M03 extends this schema to business domains; do not postpone essential auth persistence to M03.  
**Acceptance:** Automated HMAC/session/CSRF/owner-only endpoint tests pass with PostgreSQL fixtures; no mock auth in production build. Real Telegram phone launch and cookie behavior are a **separate G1 device-check gate**: record PASS only if actually tested, otherwise PENDING with steps and evidence required. Cross-customer order/file isolation is tested when those resources exist in M04/M09.

### M03 — Database and domain API foundation
**Dependency:** M02 (minimal auth persistence created there); M00 approved  
**Deliverables:** Extend the existing M02 SQLAlchemy async/Alembic/auth foundation with **minimal core domain models (projects, stage requests and basic records) created incrementally**, not every eventual inventory/payment/production table; PostgreSQL integration tests, status transition services, OpenAPI versioned contracts, generated TypeScript types, transactions, audit log, idempotency keys, **minimal transactionally written notification outbox**, and initial ownership checks. Avoid a second schema/migration framework. M08 will use this outbox for initial owner alerts; M13 extends retries/preferences/reporting.  
**Acceptance:** Fresh installation and migration upgrade work; DB constraints and rollback strategy tested; FastAPI `/api/v1/health` and `/api/v1/auth/me` operational (the auth endpoint was introduced in M02 and is verified again in M03); React can call backend via relative `/api` URLs.

### M04 — Customer intake: secure uploads and print request wizard
**Dependencies:** M02, M03  
**Deliverables:** Service picker; private STL/3MF/OBJ uploads; reference image uploads where needed; server-side persisted drafts; item quantities/material/color/quality/special instructions; summary and submit; file size/type/ZIP-bomb constraints; owner visibility.  
**Acceptance:** Customer can resume draft, upload multiple models and submit; other customers cannot view/download it; corrupted/oversize uploads fail safely; uploaded files are private and queued for analysis, not executed on API host.

### M05 — Custom design and combined service workflow
**Dependencies:** M03, M04  
**Deliverables:** Design brief, references, revision limits/scope, design project records, design proof versions and customer approval UI, conversion of approved design to a linked print request. The owner can **scope** design without a model upload, but **real quotation issuance belongs to M07–M08**. Use a clearly labeled simulated quote/payment fixture for the prototype approval workflow; M09 implements actual stage-payment services. No real design production begins on unpaid live orders.  
**Acceptance:** Design can be scoped and tracked without uploaded STL; proof versions remain immutable; progression into simulated design work requires the explicit simulation-paid fixture. **Do not claim actual design quote or live payment support in M05.** Approval of a design version does not automatically authorize print production.

### M06 — Virtual printer profiles and model analysis/slicing
**Dependencies:** M04, M03  
**Deliverables:** Virtual printer models, material compatibility, trusted slicer profile registry, model validation, dimensions/unit confirmation, isolated PrusaSlicer adapter, background queue and bounded workers, parsed filament/time and warnings, stored analysis/slicing provenance.  
**Acceptance:** Known test model produces reproducible estimates under pinned profile/version; failures time out and enter manual review; no physical printer required; processing service has no DB/bot secrets or printer-network access.

### M07 — Pricing engine and Level 2 auto-quote eligibility
**Dependencies:** M06, M05, M03  
**Deliverables:** Decimal cost engine with MMK rounding policy for physical-printing estimates, spool/material cost, machine-hour assumptions, labor/overhead, risk, margin, minimums, pricing-version snapshots; **independent manually scoped design-service pricing basis (labor, revisions, deliverables, approved digital currency policy) without requiring slicing or filament**; eligibility policy engine with pass/fail/unknown reasons; quote expiry/versioning, **`BINDING_QUOTES_ENABLED` and `AUTO_QUOTE_ENABLED` independent feature gates**; **separate `test_estimate` / `simulation_offer` from `binding_offer` in server schema and UI**. Currency of digital design charges is decided separately under payment policy.  
**Acceptance:** Unit tests for rounding and edge cases; use a clearly simulated stock-availability adapter with seeded stock fixtures until the actual ledger lands in M10. Fail closed (manual review) when slicer/profile/stock data is unknown; stale/changed requests require a new eligibility evaluation; auto-issued quote references exact model/profile/pricing versions. **In pre-hardware development, no binding/payable offers; any acceptance is simulation-only.**

### M08 — Owner exception review and quotation UX
**Dependencies:** M07, M02  
**Deliverables:** Owner queue in Mini App for flagged requests; approve/ask clarification/revise/reject; detailed model/estimate/specification views; quotation detail/accept/decline/expiry customer screens (**record acceptance; stage order + obligation creation belongs to M09**); **first transactional-outbox-based Telegram notification (on M03 outbox foundation)** with authorized deep link; audit history.  
**Acceptance:** Manual quote issuance remains non-binding while `BINDING_QUOTES_ENABLED=false`. Owner decision mutates through FastAPI only; quotation/version mismatch invalidates old buttons; customer cannot approve their own special quote; review notifications do not reveal private data in public chats.

### M09 — Order confirmation, stage payments and verification
**Dependencies:** M08, M03  
**Deliverables:** Materialize recorded valid accepted quote -> **one stage order + one stage obligation atomically and idempotently**; category-specific checkout for Telegram Stars via verified invoice/pre-checkout/successful-payment updates (implemented in sandbox before activation), separate physical-goods evidence flow where approved, verification/rejection by owner, refund records and idempotent state transitions; separate design and printing obligations. **Before checkout for a printing stage, reserve/revalidate simulated stock/capacity through a bounded hold; M10 replaces filament holds and M11 introduces real printer-class capacity holds. No live physical checkout while either adapter remains simulated.** Test payments only until launch.  
**Acceptance:** Simulated order/receipt is never considered real payment. Test duplicate/wrong-buyer/wrong-amount Stars events, expiration, pre-checkout deadline, and owner verification hold. Uploading a receipt never marks payment verified; only owner can do so; stage payment and required approvals gate work; duplicate receipts/provider callbacks cannot double-confirm or reserve. Missing/expired stock hold blocks new checkout; payment success followed by stock/capacity failure enters audited owner hold/refund resolution, never production. **Design-only stages have no filament/printer prerequisite. Digital goods/services sold inside Telegram use Telegram Stars (`XTR`) where applicable; external/manual MMK payments must not be offered as an in-Telegram workaround.** Physical print payment methods require separate approval. See `docs/PAYMENTS_COMPLIANCE.md`.

### M10 — Filament inventory and transactional reservations
**Dependencies:** M03, M07, M09  
**Deliverables:** Materials/variants/spools, stock movement ledger, procurement, corrections, reservations, release and waste/actual use; minimum stock alerts; stock reconciliation.  
**Acceptance:** Concurrent reservations never oversell stock; provisional checkout holds expire/release or are atomically promoted to firm on verified printing-stage payment; paid but unassignable jobs remain on owner hold rather than silently consuming stock; waste, retries and remaining weight reconcile; all adjustments audited.

### M11 — Hybrid printer scheduling and owner assignment
**Dependencies:** M06, M09, M10  
**Deliverables:** Printer profile vs physical asset distinction, **time-bounded printer-class capacity holds and expiry/reconciliation**, compatibility/fit/workload recommendations, proposed split by quantity, owner approval/reassignment history, **conflict-free specific-printer assignment windows**, simulation queue.  
**Acceptance:** Incompatible/maintenance printers never recommended; overlapping approved printer slots rejected; allocation changes audited; no job released before fully verified payment and approved assignment; simulator supports zero physical machines.

### M12 — Production lifecycle, failures, QC and fulfillment
**Dependencies:** M11  
**Deliverables:** Owner production board; manual start/pause/complete logging; actual material capture; print failure and owner decision; **linked reprint attempts with partial quantity-level QC reconciliation**; pickup/shipping details and handover confirmation; **scope-conditional secure digital design-deliverable release** after design payment and exact-version approval; combined design+print does not necessarily transfer downloadable files.  
**Acceptance:** Failed job does not auto-reprint; passed QC quantities cover ordered output before fulfillment; contracted digital design delivery requires approved version and paid design stage; job/order statuses independent and transition-validated; customer sees meaningful status without simulated progress fabricated as actual machine data.

### M13 — Notifications, support and reports
**Dependencies:** M08–M12  
**Deliverables:** Expand the M03 transactional outbox and M08 initial owner alerts into robust notification delivery: retries, dead-letter handling, preferences, customer milestones, support/thread linkage, and revenue/cost/inventory summaries. Do not replace the earlier outbox with a parallel messaging implementation.  
**Acceptance:** Events are deduplicated; no customer-specific information is leaked; dead-letter/retry handling recorded; metrics reconcile with DB records.

### M14 — Security, reliability and end-to-end staging audit
**Dependencies:** M02–M13  
**Deliverables:** Threat model; upload and parser hardening; disposable CI/Compose integration-staging setup for restoration and E2E tests; RBAC/IDOR/CSRF/session tests; dependency scans; rate limiting; audit log coverage; backup/restore drills; load tests; migrations from prior versions; log/metrics/alerting; Telegram client regression testing.  
**Acceptance:** No critical findings open; isolated worker restrictions verified; successful restore in staging; full E2E customer -> quote -> payment -> assignment -> QC -> fulfillment in simulator, including negative tests.

### M15 — VPS deployment and controlled pre-hardware release
**Dependencies:** M14  
**Deliverables:** Hosted staging smoke/security checks, domain + Caddy HTTPS, production Docker Compose, private PostgreSQL and Redis, secure secret handling, monitored jobs, offsite encrypted backups, CI/CD with manual release approval, environment isolation, BotFather production URL. Customer-facing real service transactions held until hardware is ready; optional invitation-only request/waitlist intake.  
**Acceptance:** App opens in Telegram on real devices; only HTTPS gateway exposed; backups tested; service remains available independently of developer laptop; real payments/production/automatic final quotes disabled.

### M16 — Actual printer onboarding, calibration, and live-order launch
**Dependencies:** M15 and purchased/installed hardware  
**Deliverables:** Register physical printers and filament; validate build/material/nozzle compatibility; calibrate slicer profile, time and material estimates against real prints; confirm labor, electrical, depreciation and failure rates; physical print QC and emergency procedures; production terms, refunds and shipping; controlled activation of Level 2 auto-quote rules.  
**Acceptance:** Repeatable calibrated test prints; end-to-end real but low-risk **manually quoted** order succeeds first; no automatic unattended print starts; approval/payment gates verified; live feature flags enabled individually after owner signoff. **Level-2 automatic binding quotes are a separate subsequent launch switch after manual production evidence**.

## 3. Project release gates

| Gate | Milestones | What is usable | Still prohibited |
|---|---|---|---|
| G1 — Mini App linked | M00–M03 plus verified device test | Secure Customer/Owner login, test dashboards, typed API | Real orders/payment |
| G2 — Request capture | M04–M05 | Non-payable test requests, private files, design briefs, owner review | Any binding quote or payment |
| G3 — Estimating simulator | M06–M08 | Development prices, owner/quote workflows, alerts | Customer payment for uncalibrated print |
| G4 — Software-complete simulator | M09–M13 | Full simulated order life cycle and accounting logic | Physical print and real order acceptance |
| G5 — Staging/hosted | M14–M15 | Secure deployed application and invitation-only testing | Live production before hardware |
| G6 — Production release | M16 | Real paid orders and calibrated Level-2 auto-quotes | Unattended printer start by default |

## 4. Technical contracts to freeze early

1. Role model: `customer`, `owner`; future staff permissions mapped to capabilities.
2. Service types: `printing`, `custom_design`, `design_and_print`.
3. Independent request, quotation, order, payment, assignment, print-job, QC and fulfillment state machines.
4. Quote versions and request/model/profile/pricing snapshots are immutable once issued.
5. All financial operations use PostgreSQL `NUMERIC` and Python `Decimal`; MMK-specific rounding policy is stored and versioned.
6. Real customer data and uploaded model files are private; all downloads authorized per resource.
7. File upload and slicing are asynchronous and isolated; failure is `manual_review`, never silent acceptance.
8. Payment receipt != verified funds; immutable verified payment credit must not be reused across different obligations; owner verifies. A design stage requires its own payment and scope approval; printing additionally needs payment, viable stock/capacity, and owner-approved printer assignment. Check/revalidate stock **before charging**, not only after settlement.
9. Inventory is ledger-driven, with transactional reservation and actual consumption.
10. API uses `/api/v1`, generated TS types; same-origin URL in production.
11. Bot alerts use opaque references in deep links to Mini App pages, not public sensitive details. A signed link is still **not authorization**; require Telegram session and server-side access checks.
12. Development/staging/production feature flags isolated; mock Telegram authentication cannot function in production.

## 5. Suggested monorepo

```
3DPS-MiniApp/
├── AGENTS.md
├── docs/
│   ├── PRODUCT_SPEC.md
│   ├── BUSINESS_RULES.md
│   ├── STATE_MACHINES.md
│   ├── INTEGRITY_RULES.md
│   ├── DEPENDENCY_MATRIX.md
│   ├── ARCHITECTURE.md
│   ├── DATA_MODEL.md
│   ├── API_CONTRACTS.md
│   ├── FRONTEND_SPEC.md
│   ├── SECURITY.md
│   ├── PAYMENTS_COMPLIANCE.md
│   ├── OPEN_DECISIONS.md
│   ├── DEVOPS.md
│   ├── MASTER_ROADMAP.md
│   └── adr/              # created during M00
├── miniapp/                 # React/TypeScript/Vite
│   └── src/{app,features,components,integrations,lib,pages}
├── backend/                 # FastAPI modular monolith, workers, tests
├── telegram_bot/             # Aiogram handlers, notifications (valid Python module name)
├── migrations/              # Alembic (location can follow backend)
├── deploy/{caddy,compose}/
├── tests/e2e/
├── compose.yaml
└── .env.example
```

## 6. Codex development process

- Create one Git branch and one scoped task per milestone subsection; keep changes reviewable.
- In Codex, start with **audit then plan**, then implement only the approved deliverable.
- Every PR must contain changed-file summary, migrations (if any), updated OpenAPI type generation, test results, relevant docs and rollback considerations.
- CI: Python lint/types/tests, Postgres integration tests, frontend lint/types/unit/build, security scans, Docker image build; e2e in staging for release gates.
- No automatic schema deletion, no unaudited dependencies, no real payments/quotes/printer commands without an explicit feature flag and owner approval.
- Definition of Done: behavior documented; error, edge and permission cases tested; logs and alerts designed; mobile Telegram tested when UI changes; no secrets in logs/source.

### Codex starter instruction

> Audit the current 3DPS-MiniApp repository and the master roadmap. Implement **M00 only**: inventory code and documentation, reconcile the original starter with the Mini App bootstrap, identify gaps and hazards, and propose ADRs. Do not delete data or start future milestones. After tests, provide changed files, commands/results, assumptions and unresolved decisions for review.

## 7. Indicative schedule and critical path

These are planning ranges for one developer with strong Python experience using Codex, but learning some React/Telegram integrations. Not contractual estimates.

- M00–M03: **3–5 weeks part-time** (foundation/login/DB).
- M04–M05: **2–4 weeks** (requests/design/files).
- M06–M08: **3–6 weeks** (slicing/pricing/reviews).
- M09–M13: **5–9 weeks** (payments/inventory/production/notifications).
- M14–M15: **2–4 weeks** (security and deploy).
- M16: **hardware-dependent**, variable, begins only after purchasing/calibrating real printers.

Allow overlapping work only where dependencies are stable and acceptance tests are preserved. This is roughly **15–28 weeks of part-time development before hardware calibration**; time varies substantially with scope changes and testing effort.

## 8. Scope controls and deferred features

**MVP:** customer print requests, design requests, saved drafts, quote review, verified manual payments, spool inventory, virtual scheduling, owner approvals, QC, notifications, secure deployment.

**Later:** fully interactive 3D model viewer, automatic 3MF repair, sophisticated multi-printer optimization, printer telemetry/camera feeds, remote print start, supplier/ERP integrations, multi-tenant shops, analytics warehouse, dedicated operator role/UI, native mobile applications.

## 9. Operational and policy caveats

- An STL has no reliable machine-specific print-time/cost; slicer profiles produce provisional estimates. Virtual profiles do not establish real manufacturing capability.
- Telegram documents distinct payment rules for physical goods and digital goods/services. **For digital goods/services sold inside Telegram, Telegram Stars are required.** Classify each service and payment flow before live checkout; physical prints may use supported physical-goods payment arrangements. Do not assume bank transfer/receipt upload is compliant for standalone digital design. See `docs/PAYMENTS_COMPLIANCE.md`.
- Protect Telegram identity with verified raw initData, short-lived server sessions, CSRF defenses, and real server-side owner role assignment.
- For uploaded files, validate formats/content, enforce size/decompression limits, quarantine, use private storage and isolated workers.
- For real hardware, deploy a local authenticated workshop agent; never expose printer control ports publicly.

## 10. Codex website workflow and package navigation
- `AGENTS.md` lives at the GitHub repository **root**. Docs and prompt files use their actual included names; this file is `docs/MASTER_ROADMAP.md`.
- Codex Cloud must be connected to the repository. Each cloud task runs in an isolated workspace; reviewed changes must be saved to the repository before a later task depends on them.
- Running a local Docker daemon, running a Telegram bot continuously, and obtaining an HTTPS phone-preview URL are **not guaranteed in the Codex Cloud environment**. Prepare these in an optional CachyOS setup or staging VPS where necessary.
- Use M00 to record decisions about physical vs digital service classification, API schema and migration baseline before large code generation.

## 11. Official references

- Telegram Mini Apps: https://core.telegram.org/bots/webapps
- Telegram physical payments: https://core.telegram.org/bots/payments
- Telegram digital goods: https://core.telegram.org/bots/payments-stars
- PrusaSlicer CLI: https://github.com/prusa3d/PrusaSlicer/wiki/Command-Line-Interface
- OWASP File Upload: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
- OWASP Session Management: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
