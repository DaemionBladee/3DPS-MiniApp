# Authoritative state machines and transition guards — v1.4

**Status:** normative business contract. Implement transitions in backend domain services, not as arbitrary ORM/UI status changes. This file documents allowed *business paths*, not automatically complete code. Add a transition-table test for each entity when its milestone is implemented. Every transition has actor, expected version, idempotency key (for side effects), timestamp, reason when needed, and audit record.

## General rules
- Entity `mode=simulation` and `mode=live` is immutable from creation. A change in server feature flags never upgrades a record.
- `request_revision`, `spec_snapshot_sha256`, file checksums, design version, slicer profile/version, pricing policy, and approval references must be checked at issue, accept, and checkout. Revisions supersede affected offers/approvals; previously verified payment is **never** silently erased or repurposed.
- A quote is an *offer*, not an order; an order is *not* paid merely because a receipt or invoice UI exists.
- Different stages under one `service_project` have independent quotes, orders, obligations, statuses and fulfillment rules. Never use design-stage payment to release print-stage work.
- A failed/ambiguous transition must leave the database unchanged and return a typed 409/422/etc. Failure modes must be tested.

## Service request
| From | To | Actor / guard |
|---|---|---|
| `draft` | `submitted` | Customer; valid current revision, file/scope validation, unique submission command |
| `submitted` | `analyzing` | Backend; **printing only**; model-processing worker is available |
| `submitted` / `analyzing` | `manual_review` | Backend; special/unknown/failure; preserve failure reason |
| `submitted` / `manual_review` | `awaiting_customer` | Owner; clarification request |
| `awaiting_customer` | `submitted` | Customer; **new revision**, recheck downstream approvals/offers |
| `analyzing` / `manual_review` / `submitted` | `ready_for_quote` | Backend or owner; required analysis or design scope complete |
| `ready_for_quote` | `quoted` | Backend; an offer issued at exact revision (sim or live) |
| `quoted` | `submitted` | Customer requests a changed spec; create new revision; supersede affected open offers |
| `quoted` | `closed` | Backend; completed/declined/cancelled and no pending obligations |
| `draft` / `submitted` / `awaiting_customer` | `cancelled` | Customer/owner; only if no nonrefundable obligations/active work |

## Special owner review
`pending -> approved | clarification_requested | rejected | superseded`.
`clarification_requested -> pending` **only for a new review referencing the new request revision**; do not reactivate an approval of old specifications. Approval must reference `spec_snapshot_sha256` and exact quote version if one exists. Rejection must block new checkout until a revised request and decision.

## Quotation (two immutable kinds)
- **Simulation offers**: `draft -> test_issued -> test_accepted | test_declined | test_expired | test_superseded`. They create *simulation orders only*. `test_estimate` is a separate informational entity with **no accept transition**.
- **Live binding offers**: `draft -> pending_owner -> issued -> accepted | declined | expired | superseded`; auto-eligible printing can skip `pending_owner` only when `BINDING_QUOTES_ENABLED && AUTO_QUOTE_ENABLED` and all calibrated eligibility conditions pass. Manual design and special printing require owner approval and `BINDING_QUOTES_ENABLED` plus category gate.
- At most one accepted quotation per stage-request/revision; **M08 records acceptance but M09 introduces the atomic creation of one stage order and one payment obligation**, without duplicating either on retries. `accepted` is terminal for that quote; future changes use a new request/version and audited adjustment/refund process.
- Expiration must be checked against **server time** at acceptance/checkout, even if an expiry worker has not marked the row `expired`.

## Stage order (shared core and separate stage paths)
Core: `awaiting_payment -> payment_under_review -> confirmed`, with `payment_under_review -> awaiting_payment` after evidence rejection. `on_hold`, `refund_pending`, `refunded`, `cancelled` are explicit exceptional states.
- **Design stage:** `confirmed -> completed` only after a scoped, paid design project reaches exact-version customer `approved` and the **contracted design-stage deliverables are satisfied**. For **standalone digitally delivered design**, this requires an authorized `design_deliveries` release. For **design+physical-print**, a customer-approved manufacturing design may complete the design stage without transferring downloadable CAD/STL ownership if the agreed scope does not include digital-file delivery. Any contractually promised digital files still require an authorized release. Design work is tracked separately as `design_projects.designing` / `customer_review`. **No printer or filament prerequisite for the design stage**.
- **Printing stage:** `confirmed -> awaiting_assignment -> queued -> in_production -> quality_control -> ready_for_fulfillment -> fulfilled -> completed`. Enter `awaiting_assignment` only with firm stock reservation and verified payment; enter `queued` only after owner-approved compatible physical assignment (simulation uses explicitly simulation-approved virtual assignment). Quantity-level QC must cover the complete ordered output before `ready_for_fulfillment`.
- `on_hold` is allowed from `awaiting_payment`, `payment_under_review`, `confirmed`, `awaiting_assignment`, `queued`, `in_production` (if safely paused). Record `hold_reason` and `prior_status`; resume only after owner resolves the issue and the **current** payment, inventory, capacity, scope, and assignment guards pass. A paid printing order with insufficient stock stays on hold, not production-ready.
- `refund_pending -> refunded` requires auditable verified refund transactions. Cancellation of a paid stage must pass through the configured refund/dispute process; do not silently drop paid obligations.
- Never apply printing-specific states to a design-stage order.

## Payment state — distinguish objects
- **Obligation**: `unpaid -> under_review -> paid`; `under_review -> unpaid` after rejected evidence; optional `paid -> partially_refunded -> refunded`, `paid -> disputed`, and terminal cancellation through audited refund policy. `paid` requires net verified credits meeting the exact single-currency due amount. Never use UI/receipt status as payment.
- **Attempt**: `initiated -> submitted -> pending_verification -> verified | rejected | failed`; provider webhook success can mark a provider event validated but owner release gate remains separately recorded until explicitly changed by owner-approved policy.
- **Verified payment credit**: immutable credit ledger event referencing a single obligation and unique external transaction key/provider charge ID. Corrections/refunds are separate reversal/refund events. Do not double-credit a reused bank reference or provider charge.
- For digital Telegram Stars, *verified Telegram provider event* is required before financial credit; for permitted physical methods owner verifies external settlement. Customer cannot choose an incompatible method/currency.

## Design project
`brief_received -> scoping -> quoted -> awaiting_payment -> designing -> customer_review -> approved -> delivered`, with `customer_review -> designing` if an in-scope revision is requested. `on_hold`/`cancelled` follow audited policy. Stage payment **must be verified before** `designing` in live mode. An approved design version is immutable. `design_and_print` creates **one** linked print-stage request, idempotently, with FK to that exact approved design version; this does **not** accept the print quote or collect its payment.

## Filament reservation and printing capacity
- Spool reservation: `held -> firm | released | expired`; `firm -> consumed | released` (partial consumption is represented by explicit, balanced movements and remaining reserved quantity). Holds have immutable owner/item/variant and explicit expiry. Promotion must recheck real stock under row locks; firm stock does not silently expire.
- Capacity hold: `held -> confirmed | released | expired | invalidated`. A capacity hold describes **conservative eligible printer-class time/capacity for a bounded window**, not an owner-approved physical assignment. Owner assignment additionally requires a non-overlapping schedule slot on the specific physical printer and a fresh compatibility check. Expiry or loss of machine availability blocks checkout/renewal and triggers audited owner hold after payment, never silent overselling.
- Capacity and spool holds must be acquired/released in a consistent lock order or safe transaction strategy. A refund, cancellation, scope change, timeout, failed job, or final production consumption must explicitly reconcile both kinds of holds.

## Production attempts, QC, fulfillment
- Job: `pending -> queued -> running -> paused -> running -> completed` or `running -> failed`; `pending/queued/paused -> cancelled` only through permitted owner action. Failed job is immutable as a historical attempt. Reprints create **new** jobs linked with `reprint_of_job_id`, only after owner decision. Partial quantity completed must remain accounted for.
- QC: `pending -> passed | failed | rework_required`. An unsuccessful inspection can create an owner-reviewed rework/new attempt; never quietly convert a failed QC into passed.
- Physical fulfillment: `not_started -> preparing -> ready_for_pickup | shipped -> handed_over -> completed`; print-stage order completes only when all required quantities have passed QC and handover/delivery is recorded. Digital design delivery uses separate `design_deliveries` records, **not** a fake physical shipment.

## Required transition tests by milestone
- M03: transition service abstraction, optimistic concurrency/idempotency, negative transition tests.
- M04–M05: draft revisions, design project version approval and idempotent design-to-print request creation.
- M07–M08: offer snapshots, issue/expire/supersede/accept and special review invalidation.
- M09: obligation/attempt/credit ledger, owner verification, reversals and order paid gate.
- M10–M11: stock/capacity holds, races, owner assignment, release/reconciliation.
- M12: attempts, partial results, failures, QC and two distinct stage-completion paths.
- M14: cross-entity end-to-end invariants and property/concurrency tests.
