# Business workflows and invariants

## Operating modes
- `simulation`: virtual printer profiles, mock/test inventory, **simulation-only** quotation offers, orders and payment events; cannot collect real funds or release real jobs. Distinguish test estimates from test offers so end-to-end simulations are possible without creating payable claims.
- `staging`: production-like deployment, isolated accounts/data and payment sandbox where available; no real customer billing/printing.
- `production`: live-business capability is independently enabled behind owner-reviewed feature flags once M16 calibrated. Defaults OFF for `BINDING_QUOTES_ENABLED`, `AUTO_QUOTE_ENABLED`, `LIVE_PAYMENTS_ENABLED`, `REAL_PRINTING_ENABLED`. A manual binding quote is also forbidden while `BINDING_QUOTES_ENABLED=false`. A hosted production server may still operate with **business simulation enabled and all live flags OFF** before launch.
- Backend, not frontend, enforces each mode and feature flag. Sensitive flags require restricted owner/ops procedure; do not expose public toggle to circumvent launch gates.

## Lifecycle A — print-only order
1. Register customer from verified Telegram identity; create persisted draft.
2. Upload and privately store STL/3MF/OBJ; run checks; customer confirms model dimensions/units.
3. Collect per-item quantity/material/color/quality/special requirements, delivery or pickup, confirm submitted version.
4. Analyze geometry and slice with approved virtual/real printer profile. If any check fails or is unknown -> `manual_review`.
5. Eligibility engine with versioned rule set; standard pass -> auto-issue **binding offer only when live feature flag and calibrated profiles are on**. Otherwise generate a nonbinding `test_estimate`, or an explicitly marked `simulation_offer` for test order flows; special conditions -> owner review and simulated or (post-launch) manually approved quotation.
6. Customer accepts the **specific eligible unexpired offer version**. In simulation this creates a **simulation order**, never a payable obligation; in live mode it creates an order awaiting actual payment, not production-confirmed.
7. **Before live checkout of a physical-print stage**, revalidate actual inventory, material compatibility, feasible production capacity, final quote version and required approvals. Acquire a transactionally safe **time-limited provisional stock reservation** (or withhold checkout until owner resolves the missing stock/capacity). Do not expose live checkout solely on the strength of an earlier slicer estimate; M09 tests this with a simulated availability adapter and M10 supplies the real ledger-backed implementation. Design-only stages do not require stock/printer reservations.
8. In live mode, customer pays the full stage amount through a **permitted method for the deliverable category**; owner verifies actual funds or verified provider settlement as required by approved payment policy. In simulation record only clearly labeled test payment events; a screenshot alone is never confirmation. Recheck hold validity at checkout/pre-checkout, as applicable.
9. After payment verification, atomically promote/refresh the material and capacity holds to firm/confirmed state for printing. If stock or capacity is no longer sufficient after funds arrive, place the order in explicit **`on_hold`** for customer-approved reschedule/substitution or refund; never proceed on negative inventory or falsely mark production-ready. Propose compatible printer allocation; owner approves actual assignment, then release printing job to queue.
10. Owner records manual production updates; log real material use; QC; fulfillment, customer notification, completion.

## Lifecycle B — design-only / design+print
1. Capture brief, use, reference files, dimensions, acceptance criteria, allowable number of revisions and deliverables.
2. Owner scopes design work first. **Actual design quotation issuance is implemented in M07–M08**, not assumed to exist in M05. Customer accepts the issued design quotation and pays in full before any real design work. M05 may exercise proof/revision UI only with a development-only simulated quote/order/payment fixture; M09 completes stage-specific payment services.
3. Only after stage-specific verified payment (or simulated verification in simulation mode), owner creates a versioned model proof; customer approves exact design version or requests an in-scope revision.
4. For `design+print`, approved design becomes a new **print request** that is analyzed and priced independently. Printing cannot begin on the design payment alone.
5. Separate design and print payment obligations; stage status must be independently queryable/auditable. Design service quotation/order lines do not require a print `request_item`. After the customer approves the exact design version, authorize one idempotently created print request referencing that version. If the signed design scope includes downloadable digital deliverables, release them through private audited `design_deliveries`; never through a fake physical shipment. Combined design+print may instead finish its design stage on customer-approved manufacturing proof when digital-file delivery is not included in the agreed scope.
6. Standalone **digitally delivered design files/services sold inside Telegram require Telegram Stars under Telegram's current digital-goods policy**. Do not present external/manual bank transfer as an in-app replacement. For bundled custom design that culminates in a physical print, document product/payment classification and obtain owner approval **before** live checkout. See `docs/PAYMENTS_COMPLIANCE.md`.

## Lifecycle C — special order review
- `pending` -> `clarification_requested` (wait for customer) | `approved` | `rejected` | `superseded`.
- Review attaches to immutable request specification/version and quote or proposed quote. Changing the model, quantity, material, tolerances, requirements or approved profile requires re-evaluation and potentially a new approval.
- Owner may force review for any order; staff UI isn't a permission source.
- Customer cannot pay for a technically unapproved special request; if a new request revision invalidates an accepted quote, disable old acceptance/payment path.

## Lifecycle D — failed job
- Running job marked `failed` with reason, images if useful, units completed, consumed/wasted grams, downtime, operator=owner.
- Owner chooses `reprint`, `change_profile`, `reassign`, `hold`, `cancel_remaining` or contact customer as appropriate. No automatic retries.
- Reprints are new linked production attempts; preserve original job and waste history. Do not mark whole order failed merely because one print fails.
- QC decision recorded before fulfillment.

## Independent state machines (not one universal status)
| Entity | Typical statuses |
|---|---|
| Request | `draft`, `submitted`, `analyzing`, `manual_review`, `awaiting_customer`, `ready_for_quote`, `quoted`, `closed`, `cancelled` |
| Design | `brief_received`, `scoping`, `quoted`, `awaiting_payment`, `designing`, `customer_review`, `approved`, `delivered`, `on_hold`, `cancelled` |
| Quotation | Binding: `draft`, `pending_owner`, `issued`, `accepted`, `declined`, `expired`, `superseded`. Simulation offer uses `test_issued`, `test_accepted`, `test_declined`, `test_expired`, `test_superseded` |
| Order | Shared: `awaiting_payment`, `payment_under_review`, `confirmed`, `on_hold`, `refund_pending`, `refunded`, `cancelled`, `completed`. **Printing only:** `awaiting_assignment`, `queued`, `in_production`, `quality_control`, `ready_for_fulfillment`, `fulfilled` |
| Payment obligation | `unpaid`, `under_review`, `paid`, `partially_refunded`, `refunded`, `disputed` (attempts separately `initiated`, `submitted`, `pending_verification`, `verified`, `rejected`, `failed`) |
| Assignment | `not_started`, `suggested`, `pending_owner`, `approved`, `reassigned`, `cancelled` |
| Production job | `pending`, `queued`, `running`, `paused`, `completed`, `failed`, `cancelled` |
| QC | `pending`, `passed`, `failed`, `rework_required` |
| Delivery | `not_started`, `preparing`, `shipped`, `ready_for_pickup`, `handed_over`, `cancelled` |

See **`docs/STATE_MACHINES.md`** for authoritative actor/guard/transition rules. `on_hold` and refund states are required, not optional UI labels. No status string updates bypassing domain services.

## Transactional invariants
- Quotation and eligibility result refer to exact request/specification revision, model checksum, slicer profile/version and pricing-policy version.
- Only valid **issued, not expired or superseded** offers can be accepted; all `binding_offer` creation paths (including manual owner issuance) require `BINDING_QUOTES_ENABLED` and category-specific launch approval; acceptance is atomic/idempotent and mode-specific. `test_estimate` cannot be accepted; `simulation_offer` creates a simulation order only; `binding_offer` can create a real payment obligation only after live gates. Accepted values/specs are immutable snapshots.
- Payment may be released only by owner using a server-checked command; verified provider settlement and owner review remain distinguishable audit steps. Net immutable credited funds in the correct currency must cover the stage's full required amount before proceeding. Each verified external charge/bank transaction may credit **exactly one** obligation; guard against double-credit across multiple attempts/orders. Never mix MMK and Telegram Stars as if they were the same currency.
- A payment screenshot does not equal verified funds. Rejected payment evidence doesn't cancel customer's ability to resubmit.
- Inventory available-to-promise = on-hand usable quantity minus active unexpired reservations; maintain an append-only movement journal. Use DB locking/transaction isolation to prevent oversell. Holds reference item/spool/variant; capacity holds additionally protect bounded suitable printer-class windows. Explicitly expire/release provisional holds, preserve firm holds while a paid printing order awaits assignment, and test payment attempts that outlive the hold.
- An assignment must reference a real physical printer when in real-production mode, be compatible with model/material/profile, and be owner-approved. Virtual printers only for simulation/slicing.
- All transitions log actor, timestamps, reason, old/new status and relevant idempotency key. Guard quantity-level QC before physical fulfillment, and use separate digital-delivery records for approved design output.
- If backend state and Telegram message differ, backend state wins; bot retries/outbox correct messages.
- No public customer can see internal cost, margin, other customers' designs, payment references or admin notes.

## API concurrency and notification behavior
- Require idempotency keys for accept quote, verify payment, create order, approve assignment, approve reprint, and inventory reservation changes.
- Use optimistic versioning (`version`/`updated_at`) or transactional row locks for competing changes; return conflict (HTTP 409) on stale data.
- Outbox records business events transactionally; notification worker retries without sending duplicates as far as provider semantics allow.

## Decisions needing calibration before live launch
Actual machines/material compatibility; target gross margin; spool pricing and procurement; quote threshold; job size/duration threshold; customer delivery SLA; charge/revision policy for designs; returns/refunds; physical-vs-digital product/payment classification, Telegram Stars implementation where required; tax and local legal compliance. Record owner signoff before changing production defaults.
