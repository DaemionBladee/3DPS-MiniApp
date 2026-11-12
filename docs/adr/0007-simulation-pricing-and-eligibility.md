# ADR 0007 — Immutable nonbinding pricing and scoped eligibility

Date: 2026-11-12 (Asia/Rangoon). Status: implemented for M07 review.
Base: accepted M06 `e83a8ed49d0e1d00e9c1ca63bd9606e5cc4bfed2`.

Keep pricing inside the existing modular monolith. Read authoritative M06 results,
not browser metrics. Design pricing reads scoped effort without printer data.
Use Decimal accounting with NUMERIC persisted amounts, immutable versioned policies,
full provenance snapshots and fail-closed eligibility. Missing data stays unknown.
Customer projections omit internal costs/margins; Owner projections retain them.

Add only the four pricing tables in 0006 after immutable 0001–0005, plus necessary
requirement confirmations and checked audit targets. Serialize configuration and
request evaluation, reuse a source fingerprint, and write audit/outbox/idempotency
atomically. Deferred SQL triggers check complete cost-line balance.

Resolve the M07 portion of M00-D02 with `item_kind=design_service` and nullable
print-item identity; no fake design STL rows. Future quotation-item schema remains
M08 work. Resolve the M07 portion of M00-D04 using canonical `currency_code`, decimal
wire strings and integral XTR totals. MMK printing and XTR design are never summed.

For M00-D03, separate semantic `kind` from operational `mode`: current
`test_estimate` is always `simulation`, `acceptable=false`, `binding_authorized=false`.
M08 `simulation_offer` will also mean simulation operational mode; future
`binding_offer` will require live mode and launch gates. M07 SQL permits only
`test_estimate`/simulation, and immutable records prevent promotion by feature flags.
No offer/acceptance/order/payment tables are precreated. This does not approve
future live commercial or combined payment classification.

Mock availability is versioned and expiring, independently from rate policies. It
has no reservation or live authority. M06 uncertainty such as unchecked
self-intersections remains a review condition. Hardware calibration, tax/shipping
approval, real availability holds, payment classification and target-host worker
isolation remain explicit release prerequisites.

Details and API: [PRICING_POLICIES.md](../PRICING_POLICIES.md).
Environment: [CODEX_CLOUD_M07.md](../CODEX_CLOUD_M07.md).
