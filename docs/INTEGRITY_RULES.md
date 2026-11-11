# Data integrity, transaction boundaries and cross-entity invariants — v1.4

**Status:** authoritative companion to `DATA_MODEL.md` and `STATE_MACHINES.md`. Codex must not implement these as UI-only validations. PostgreSQL constraints protect simple local rules; domain services and transaction tests protect multi-table rules.

## One authoritative stage lineage
`service_project -> service_request(stage_kind) -> quotation(mode, stage, revision) -> stage_order -> payment_obligation -> payment_attempts/credits`.
- A printing-only project has one print-stage request/order; design-only has one design-stage request/order; design+print starts with a design-stage request and creates a **single linked printing-stage request** after customer approval of a specific immutable design version.
- A project may contain multiple *request revisions* and historical quotes, but at most one **active paid order per stage** without an explicit audited replacement/refund workflow. `UNIQUE(accepted_quotation_id)` alone does not prevent duplicate stage orders from two different quote versions; enforce stage-level uniqueness/active-order policy transactionally and via a suitable partial unique index.
- Reject **duplicate quote-version acceptance** attempts; a quoted stage has at most one current accepted version, and M09 materializes the linked order/obligation atomically.
- A design request may have zero print `request_items`; its service scope is represented in `design_projects`. `quotation_items` and `order_items` support `item_kind=design_service` with nullable `request_item_id`, an immutable description, price, quantity and scope snapshot. **Do not create fake STL items** for design services.
- All quote/order/obligation references agree on project, request, stage, customer, mode, category, currency and accepted version. Reject any inconsistent mutation atomically.

## Design deliverables and linkage
- `design_versions` are immutable after publication, and each customer review names the exact version. An approval updates `approved_version_id` only under a version-checked transaction.
- For `design_and_print`, record `service_requests.source_design_version_id` on the generated printing-stage request; create it idempotently with a uniqueness guard on source version plus stage/project to avoid duplicate print stages on retries.
- When the signed design scope **includes digital-file delivery** (mandatory for standalone digital design; optional by agreement for design+physical-print), store authorized, audit-trailed delivery as `design_deliveries` (design stage order, approved design version, released files, release timestamp, customer access), not as a physical `deliveries` row. Deliver only after the correct design-stage payment is verified, customer approved exact version, and scope obligations are satisfied. A combined-service design stage may be completed on customer approval of a manufacturing-ready design without granting downloadable source files, **only if that is explicit in the approved scope**.

## Quotation and owner review
- A quote is issued from the specific request **revision and canonical specification hash**, selected model file hashes, slicer/profile/calibration versions when printing, pricing policy version, owner review decision when required, and delivery/tax settings. Persist a complete immutable snapshot, including quote-item provenance; price changes generate new quote versions.
- Design-stage manual pricing must be implemented independently of slicer output: labor estimate, included revisions, deliverables and stage-specific currency/rounding policy. A design quote is **not** blocked by missing print filament.
- `test_estimate` is informational. `simulation_offer` is only accepted into simulation orders. `binding_offer` issuance and acceptance require live gates; quoting acceptance/checkout revalidate status and active revision under locks.

## Monetary ledger and payment truth
- Prices use Decimal/NUMERIC with explicit rounding; XTR must be integral. Never add or compare stage totals across currencies without a separately approved conversion policy.
- The authoritative financial credit table is `payment_credits`, not payment screenshots or editable paid flags. Every stage order has one obligation in MVP; attempts may repeat, but **verified credit entries** are immutable and individually unique by external provider charge or confirmed financial reference (properly scoped to account/provider). Credit belongs to exactly one obligation; the same transfer reference cannot pay two orders. Track overpayment, underpayment, partial payment, refund and chargeback as explicit outcomes rather than an unlocked 'paid' boolean.
- For live stage release, payment state is based on *net verified funds* in the matching currency plus owner verification; a screenshot or client callback is never sufficient. Provider event validation and owner release decisions are separate records. A refund/reversal may move a previously paid stage into dispute/on-hold according to policy; never automatically continue a job after confirmed chargeback.
- Stars `pre_checkout_query` must be answered promptly and validates the exact invoice/obligation, buyer, amount, currency, status, expiry and category. Only verified `successful_payment` with unique charge ID creates credit; retries never double-credit.

## Stock, capacity, production allocation
- On-hand grams come from immutable signed movements exactly once; available grams = on-hand minus active `held` and `firm` grams. Use deterministic lock order and DB transaction/unique constraints to prevent concurrent overselling.
- `material_reservations` reference **order_item_id** as well as order/spool/variant; support multiple spools and materials per item. Partial consumption decreases the reserved outstanding grams and posts ledger movements atomically. Never count production waste twice (a `material_consumptions` record and its ledger movement describe the **same** physical usage).
- `capacity_holds` reference the order and reserved printer-class/window/time, have expiry, and cover realistic feasible scheduling before live checkout. They do not constitute physical printer assignment; final job assignment is approved by the owner later. At owner approval, choose a specific physical printer and schedule window; reject overlapping approved/active assignment windows in a transactional check and preferably a PostgreSQL exclusion constraint. Capacity feasibility alone is not a guarantee of an exact printer slot. Invalid/expired capacity blocks checkout and triggers safe owner resolution if money already settled.
- **No live physical checkout** is allowed with mocked stock or mocked capacity holds; simulation-only holds are never accepted as live evidence. A live printing checkout requires real stock plus capacity; M09's mock adapter cannot authorize live funds until M10 and M11 capacity reconciliation exist and have passed release tests.
- `production_jobs` are attempts with `attempt_number` and optional `reprint_of_job_id`; quantity completed/passed/wasted is reconciled per `order_item`. Owner approves new reprint attempt, with stock/cost implications recorded. Final fulfillment requires the **sum of QC-passed units** to meet ordered quantity, not simply one job showing `completed`.
- Design-stage work has neither material holds nor printer assignment.

## File, worker and message integrity
- Uploads belong to a specific principal and current draft/revision. Quarantined/infected/rejected files cannot enter a quotation or public download path. File keys must be server-generated and private.
- Distinguish an uploaded/pending-analysis request from actively processing `analyzing`: in M04, queued analysis is **not a claim that M06 worker exists**. Use durable `processing_tasks` records (retry/lease/timeouts) introduced progressively in M04/M06, not an unbounded FastAPI request/background task. Worker has no database/bot token secrets or printer network access; trusted backend commits results.
- Persist state/audit/outbox atomically, deliver notifications at-least-once, and make consumers idempotent. No Telegram message can be used as financial or production truth.

## Mandatory cross-domain test scenarios
1. Two simultaneous quote acceptances for different versions of the **same stage** create at most one active payable order.
2. Design-only service with zero print request items can be quoted, paid (sim), approved and digitally delivered, without any printer or filament. Combined design+print can proceed after approved manufacturing design without optional digital-file transfer when the scope excludes it.
3. Replaying the same approved design conversion creates only one linked print request and does not pay for printing.
4. The same bank transaction/provider charge cannot credit two different obligations, including under concurrent owner verification.
5. Partial and duplicate payment events cannot release an unpaid stage; one verified fully settled stage cannot unlock another stage.
6. Concurrent spool reservations, class-level capacity holds and physical printer assignment windows cannot oversell/overbook their respective constrained resources.
7. A valid receipt submitted after reservation expiry is not accepted as a checkout bypass.
8. Paid order whose capacity/stock disappears enters `on_hold`, not `queued`; releasing holds and refunding are audited.
9. Two reprint attempts and partial QC passes do not double-complete order quantity or filament usage.
10. Old request revisions, model files, expired quotes and changed owner approval cannot authorize current checkout.
11. Quarantined model/reference files never become directly downloadable/processable.
12. Simulation records remain permanently simulation-only after switching feature flags.
