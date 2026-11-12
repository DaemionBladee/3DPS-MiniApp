# Open decisions and release blockers — do not guess

M02 update (2026-11-11): M01 was reviewed and M02 explicitly authorized. The
technical auth portion of M00-D10 is implemented in
[ADR 0002](adr/0002-telegram-authentication.md): bounded freshness, one-hour
sessions, secure cookies, Origin/CSRF and shared rate counters. Actual test bot
credentials/Owner identity, HTTPS launch and real-client cookie/device evidence
remain outstanding; G1 is not passed. All commercial/hardware/payment decisions
and M03+ schema items retain their previous deadlines.

**Status:** maintained during M00 and updated after every approved decision. Open items below do **not** block scaffolding or simulated tests. They **do** block the specific live features indicated.

| Decision | Safe current assumption | Required before | Owner approval / evidence |
|---|---|---|---|
| Physical printer models, quantity, nozzle/build volumes | Virtual profiles only; no real allocation | M16 live print | Hardware list and calibration tests |
| Calibrated slicer/material/quality profiles | Test-only estimates and simulation offers | Binding print quotes, auto quotes | Profile checksums, repeatability/calibration evidence |
| Filament brands, stock, wastage and actual unit costs | Mock stock fixtures, no real commitments | Binding print quote + production | Spool purchase costs and inventory reconciliation |
| Level-2 auto-quote thresholds | Example numbers in `PRODUCT_SPEC` are not defaults | `AUTO_QUOTE_ENABLED=true` | Explicit limits for count, duration, amount, tolerances, inventory and lead time |
| Actual pricing and rounding policy | Versioned test policy | Any binding quote | Owner-approved margin, labor, overhead, taxes, delivery and rounding |
| Digital design deliverable and payment path | Digital in-Telegram service treated as Stars-required; test checkout only | Live digital design checkout | Confirm classification/provider integration and refund policy under current Telegram rules |
| Combined design+print payment classification | Keep separate design/print stages, disabled live combined checkout | Live combined offering | Explicit category/currency decision, with legal/provider review if needed |
| Physical-goods accepted payment methods | No live checkout; test evidence only | Live physical checkout | Supported payment method, verified settlement process and proof of permission |
| Owner Telegram ID and bot username | No real IDs/tokens in docs or repository | Real Telegram login testing | Secure out-of-band provisioned ID and test bot credentials |
| File limits and retention/privacy policy | Conservative quotas and private test-only files | Public customer uploads | Limits by format, retention, deletion and customer communications |
| Delivery areas, fees, SLA, failed-print/reprint/refund terms | No customer guarantees in test UI | Live ordering | Published terms and owner acceptance |
| Security recovery and backup targets | Disposable test data only | Production hosting | RPO/RTO, backup restoration evidence and incident plan |
| Capacity scheduling/overbooking policy | Conservative mock capacity-hold adapter | Any live physical checkout | Machine availability, blackout windows, reservation expiry and conflicts tested |
| Design delivery acceptance and usage rights | Private, test-only versions and scoped revision policy | Live design quote/delivery | Owner-approved scope, file formats, revision count, IP/licensing, and whether combined design+print includes transferable digital CAD/STL files |
| Provider/bank transaction uniqueness scope | Disposable mock transaction keys | Any live owner payment verification | Define provider/account/reference uniqueness rules and process to resolve ambiguous duplicates |

Rules:
1. Document the selected value, date, rationale, approver and affected milestones in a short ADR; update corresponding docs and tests in the same PR.
2. Never silently assume a legal/Telegram provider classification or enable live flags because a payment test succeeds.
3. Decisions can remain pending while implementing unrelated work. The related release gate stays closed.

## M00 audit review — 2026-11-11

The owner approved the M00 architecture baseline in the M01 start instruction
(2026-11-11 client date), resolving **M00-D09** as baseline direction. D01–D08
remain open until their affected contracts are reconciled; D10's frontend
tooling is recorded in `miniapp/package.json`, lockfile and `.node-version`,
while backend/auth parameters are now implemented in ADR 0002 for M02 review.
Actual test-account provisioning and G1 device evidence remain pending. The initial
checkout contained only a title README. The v1.4 contracts were recovered from
the instruction archive at development commit
`d758653d940124760e5cd7e9b02071a9ba3ce805`; they describe requirements, not
implemented capabilities. See [the baseline](IMPLEMENTATION_BASELINE.md) and
[proposed ADR 0001](adr/0001-project-baseline.md) for provenance and evidence.
Existing launch-blocking rows above remain unresolved and unchanged.

| ID / decision | Evidence / discrepancy | Proposed safe handling pending review | Required before / evidence to close |
|---|---|---|---|
| M00-D01 — Active payable stage-order predicate | `INTEGRITY_RULES` lineage says active **paid**; AGENTS, API, DATA_MODEL and integrity race tests require active **payable**. | Preserve the stricter one-active-payable-order invariant; no index/status predicate invented now. | M09 order schema: approve active statuses (including unpaid and held obligations), lock/index strategy and audited replacement/refund behavior; test competing quote versions. |
| M00-D02 — Typed design quotation items | Integrity requires `quotation_items.item_kind=design_service`; DATA_MODEL quotation-item field list omits `item_kind`, while order items include it. | Genuine design-service lines, nullable print-item FK and immutable scope; no fake STL rows. | M07/M08 quotation migration: reconcile discriminator/check constraints and no-print-item tests. |
| M00-D03 — Semantic mode mapping | General entity mode is `simulation/live`; quotation `mode` is `simulation_offer/binding_offer`. Literal equality across the lineage is impossible. | ADR proposes typed mapping from offer kind to operational mode, with immutable records and no promotion. Do not rename fields silently. | Affected M07–M09 schemas/DTOs: approve exact types, constraints and mapping; prove cross-mode rejection. M03 should not precreate these tables. |
| M00-D04 — Canonical currency wire field | API conventions/data model specify `currency_code`; quotation JSON example uses `currency`. | Propose `currency_code` for canonical DTOs; decimal strings and integral XTR policy remain unchanged. | First affected OpenAPI/generated quote types, by M07/M08: align docs/sample/schema and contract tests. |
| M00-D05 — Assignment and physical fulfillment transition tables | BUSINESS_RULES lists assignment statuses without a complete normative table; its delivery list includes `cancelled` but lacks STATE_MACHINES' `completed`. | Keep state machines separate; no inferred owner-assignment, completion or cancellation bypass. | M11 assignments / M12 delivery: actor/guard/version/hold-release tables and negative tests, including cancelled delivery. |
| M00-D06 — Refund, reversal and late hold paths | STATE_MACHINES specifies `on_hold` entry only through production; integrity requires resolution after reversal/chargeback. Refund entry/resume, partial outcomes and post-QC/fulfilled behavior are incomplete. | Retain financial history and stop automatic release/progression on ambiguous funds; do not rewrite completed history or silently refund. | M09 financial transitions, extended before M12 completion: owner-approved exception table, obligations/credits/refunds reconciliation and tests. |
| M00-D07 — Combined manufacturing-only design terminal state | Design project chain ends `approved -> delivered`; order/integrity rules allow scoped manufacturing handoff without digital-file transfer. | No fabricated `design_deliveries` or entitlement. Keep approved design separate from order completion until terminal semantics are approved. | M05 design-state modeling, validated again at M12: define manufacturing handoff vs digital delivery terminal meaning and tests for both scopes. |
| M00-D08 — M01 backend-health acceptance boundary | M01 prompt requests health only **if backend is running**; actual repository has no backend, and M02/M03 own it. | M01 tests client unavailable-state handling and relative proxy configuration; health connectivity remains unrun until an actual API exists. | M00/M01 review: accept frontend-only scope; M03 proves `/api/v1/health` and frontend connectivity. No toy backend in M01. |
| M00-D09 — Baseline architecture and migration approval — RESOLVED for direction | Owner explicitly approved M00 and authorized M01 in chat on 2026-11-11 (client date). | ADR 0001 accepted as baseline; no live or M02 authorization. | PostgreSQL UUID support/session design still require M02 evidence; D01–D08 keep their own review deadlines. |
| M00-D10 — Development pins and auth parameters — technical portion implemented | M01 frontend lockfile and M02 Python/DB pins, auth persistence and tests now exist; the earlier audit inventory remains historical. | ADR 0002 records M02 security defaults, one Alembic chain and disposable PostgreSQL validation. Live gates remain off. | Review M02 technical choices; securely provision actual test bot/Owner identity and complete the G1 device checklist externally. |

These contract-completion items have implementation deadlines; the earlier live
policy decisions have release deadlines. Neither is approval to implement later
milestones in M00. Pricing, rounding values, actual printers, legal classification,
provider availability, production credentials and live switches remain undecided.

## M04 implementation choices awaiting review — 2026-11-11 (Asia/Rangoon)

M03 was accepted by the M04 start instruction. [ADR 0004](adr/0004-private-printing-intake.md)
records the implemented private intake slice; none of these choices enables a
live service or closes G1. Existing commercial decisions remain open.

| Item | Safe implemented behavior | Evidence needed before expansion |
|---|---|---|
| Upload quotas and supported profile | Conservative limits; standalone STL/OBJ and one-part Core 3MF; development-only catalog | Owner review of quotas, clean-export guidance and intended real model corpus before public intake |
| Retention and deletion | Ready/cancelled model files retained and charged; expired/failed uploads cleaned with durable reservations | Retention/consent/deletion policy, encryption, backup/restore and approved cleanup schedule before public customer data |
| Validation isolation | Cleared-environment resource-bounded stdlib subprocess; no model execution or network-fetch code | Stronger UID/mount/network or VM isolation and adversarial security review before M06/public exposure |
| Submitted corrections | Submitted snapshot/items are frozen; no reopening/overwrite endpoint | Explicit clarification/successor-revision workflow and stale downstream invalidation before later approvals |
| Real Telegram uploads/downloads | Desktop Chromium HTTPS tests pass; real WebViews unverified | Android/iOS/Desktop test-bot evidence, gateway limits and download compatibility before G1/public launch |

## M05 review notes — 2026-11-11 (Asia/Rangoon)

M04 acceptance is explicit in the M05 start instruction. ADR 0005 records the
implemented simulation-only scope/proof path and exact manufacturing lineage.
M00-D07 remains open: approved manufacturing-only design is not silently marked
delivered or completed, and M12 must define the audited handoff terminal meaning.
Digital rights are explicit scope fields but confer no M05 source release.
Supported references are PNG/JPEG/plain TXT; other document types need a reviewed
validator/profile. Existing public-upload isolation, retention, encryption,
backup/restore and real-device requirements remain open. The explicit test-only
quote/paid fixture cannot satisfy future M08/M09 quote or payment guards.

## M06 review additions (2026-11-12, Asia/Rangoon)

- Public native-worker release remains blocked on target-host cgroup delegation
  and measured aggregate CPU/RAM/PID enforcement, plus VM/microVM isolation review.
  Cloud's hard POSIX/tmpfs tests do not prove those aggregate ceilings.
- Virtual PLA/PETG profiles are approved only for simulation. Actual hardware,
  material density/flow/speed calibration, support/manufacturability review and
  measured throughput remain unavailable and block live pricing/production.
- The pinned engine/image has exact runtime provenance; transitive apt packages
  are recorded rather than snapshot-pinned. Future security/dependency updates
  require a new tested image and profile revision, never replacement of old runs.
- Submitted-request edits/reopen, customer clarification messaging, batch packing,
  reliable support-material breakdown, self-intersection/strength certification
  and calibrated costing remain outside M06. No inferred approval substitutes for
  M07–M16 guards. Real Telegram device presentation still needs external checks.

## M07 implementation boundary

M07 resolves only its own portions of M00-D02/D03/D04 through [ADR 0007](adr/0007-simulation-pricing-and-eligibility.md): typed design-service lines, immutable test_estimate/simulation mapping and currency_code. Future offer schema and live combined-service payment classification still require review. No commercial rates, tax policy or physical calibration is approved by hypothetical test configuration.
