# Milestone dependency matrix and feature-readiness contract — v1.4

Milestones are **development order**, not permission to charge customers. Each milestone requires its predecessors and *named acceptance tests*; parallel development is allowed only behind stable API/data contracts and feature flags.

| Milestone | Depends on | Implementation capability introduced | Must NOT be assumed yet |
|---|---|---|---|
| M00 Audit | None | Approved requirements, ADRs, actual-code inventory | Any working application functionality |
| M01 Mini App shell | M00 | Buildable React UI, mock two-role navigation | Secure Telegram identity or persistent orders |
| M02 Telegram security | M01 | Verified `initData`, minimal users/sessions Alembic, CSRF, owner authorization | Business domain tables/flows |
| M03 Core domain | M02 | Shared DB/session model, minimal projects/requests, transitions, idempotency/audit/outbox, OpenAPI | All future tables or actual workers |
| M04 Intake | M03 | Printing draft/upload privacy, request items, durable pending-analysis records | Actual analysis/slicer results (M06) |
| M05 Design | M03, M04 | Design brief/scope/proof version UI, design->print lineage in simulation | Live design quotes (M08), live payment (M09) |
| M06 Analysis/slicing | M04 | Isolated worker, pinned profiles, analysis/slicing results | Trustworthy calibrated live costing |
| M07 Pricing/eligibility | M05, M06 | Manual design-pricing basis plus printing cost/eligibility; simulation offers | Live binding quotations/payments |
| M08 Reviews/quotes | M07, M03 outbox | Owner review, versioned offers and **acceptance state**, first notifications | Stage order/obligation creation and payment (M09) |
| M09 Stage orders/payments | M08 | Simulation obligations, payment credits, Stars sandbox contract, checkout gating via mock stock/capacity | Live physical checkout without M10/M11, live Stars until separate approval |
| M10 Inventory | M09, M07 | Real spool ledger and lock-safe item-scoped holds; reconnect M09 checkout adapter | Capacity scheduling/approved physical assignment (M11) |
| M11 Capacity/assignment | M06, M09, M10 | Capacity holds/reconciliation, print split, real/virtual compatibility, **non-overlapping physical printer windows**, owner approval | Physical start without purchased calibrated printer |
| M12 Production/fulfillment | M11, M05 | Attempts/reprints, QC quantity reconciliation, physical fulfillment and digital delivery | Real production live gate |
| M13 Notification/reporting | M03 outbox, M08, M09–M12 | Retry/dead-letter, support, reports, comprehensive alert rules | Production readiness without M14 |
| M14 Security/testing | M02–M13 | End-to-end simulator regression, penetration-style tests, backup restores, migration checks | Public business launch |
| M15 Hosting | M14 | Stable HTTPS Telegram staging/limited public waitlist and monitoring | Real binding quotes/payments/printing |
| M16 Hardware/live | M15, hardware, calibrated policies, payment classification | Controlled manual live print, then optional Level-2 autoquote | Unattended physical starts |

## Contracts to implement early and then specialize
- **Auth migration chain:** M02 owns `users/sessions`; M03 adds early domain tables through the **same Alembic chain**; M04–M12 add their own tables when capabilities become real, never one enormous speculative migration in M03. Add `service_requests.source_design_version_id` as a nullable FK during M05 *after* `design_versions` exists, not as a broken FK in M03.
- **Background work:** M04 persists a `pending_analysis` processing task; M06 introduces isolated execution and transitions to `analyzing`. The API must not pretend to have a slicer before M06.
- **Design stage:** M05 produces model/scope and mock approval UI; M07 supplies design pricing, M08 supplies versioned quote issuance/acceptance, M09 supplies payment obligations and owner verification, M12 releases approved digital deliverables.
- **Quote mode:** M07 produces simulation offer/estimate engine, M08 records eligible acceptance, and M09 materializes the **one** simulated stage order+obligation transactionally. Real binding quotes require owner-approved gates independent of whether the handler is automatic or manual.
- **Checkout:** M09 only exercises mock availability adapter; M10 introduces real spool holds; M11 introduces capacity holds. **No live physical checkout until BOTH real adapters are integrated and tested.** Real full payment may happen before owner approves final physical printer assignment, but production remains blocked until approved.
- **Events:** M03 writes transactional outbox; M08 demonstrates delivery and owner deep link; M13 adds retries/dead-letter/suppression/reporting. Preserve idempotence at each step.
- **Hardware and identity:** Codex Cloud runs unit/integration tests, not permanent app hosting. Real Telegram phone, payment provider sandbox, slicer isolation and actual printers require explicit external test evidence; never mark those passed from generated code alone.

## Mandatory stop points
- After M00: owner approves migration plan, unresolved policy assumptions and architecture.
- After M02: no G1 claim without actual device test; if unavailable, mark it PENDING and continue safe backend development.
- After M08: no binding quotes; only simulated examples.
- After M11: test live-path guards in staging but leave all live flags OFF.
- After M14/M15: perform restore and device tests, then review every OPEN_DECISIONS launch blocker.
- At M16: release manual low-risk printing first after full payment, hardware and QC evidence. Enable Level-2 automatic final quoting only as a **separate subsequent owner-approved action**.

## M07 implementation boundary

The implemented M07 slice persists nonbinding test_estimate records only. Simulation-offer issuance/acceptance remains M08; stock/capacity fixtures confer no hold or checkout authority. See [ADR 0007](adr/0007-simulation-pricing-and-eligibility.md).
