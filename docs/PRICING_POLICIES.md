# M07 simulation pricing and eligibility

M07 creates only **NON-BINDING TEST ESTIMATES**. They have no acceptance action,
financial obligation or production authority. No policies are seeded by migrations
or startup. An authenticated Owner must explicitly publish hypothetical simulation
configuration. Example rates and thresholds are invented software-test data;
PRODUCT_SPEC examples are not commercial defaults.

## Deterministic calculation

Decimal inputs use plain nonnegative decimal strings, at most eight fractional
places. Binary floats, exponents, nonfinite and negative inputs are rejected.
The engine uses Decimal precision 50, rounds persisted component amounts HALF_UP
to eight fractional places, and stores amounts in PostgreSQL NUMERIC(28,8).
Printing is MMK/physical_goods. Scoped design simulation is XTR/digital_goods;
XTR totals are integral. There is no conversion or combined cross-currency total.
Combined-service payment classification still requires the payment-policy decision.

Print costs include measured filament multiplied by quantity, material unit rate,
waste allowance, explicitly assumed support allowance, serial machine hours,
electricity, overhead, setup and per-item postprocessing labor. A support allowance
is not a fabricated support-material measurement. Quantity scaling assumes serial
prints; it does not claim batch packing or physical scheduling.

Apply risk to base costs, then gross margin as `risked_cost / (1 - gross_margin)`.
This is gross margin, not markup. Apply minimum-charge top-up, shipping and tax,
then currency-specific rounding. Policies select positive integral MMK steps and
HALF_UP or CEILING; XTR always uses step 1. A signed rounding-adjustment component
makes the component sum exactly equal the final total. Per-component and total
bounds prevent unsupported amounts becoming complete prices.

Design costs use the current Owner-authored scope, estimated hours, included
revision count × effort per revision, complexity multiplier, hourly rate,
deliverable fee and usage-rights fee, then risk/margin/minimum/tax/rounding.
Design does not query printing items, filament, profiles or slicer results. An
unapproved scope can be estimated but remains explicitly under review. Pricing
never agrees to a scope or grants delivery rights.

Missing rates, shipping/tax assumptions, unknown material or current native
metrics produce an incomplete estimate with a null total, never a zero price.
Core rates and initial design effort must be positive. Optional zero rates such
as tax, supports and delivery/rights fees require an explicit zero-cost reason.
Pickup shipping is explicitly zero. Risk, margin and minimum are explicit policy
parameters, not inferred defaults. All unknown components remain visible to Owner.

## Fail-closed Level 2 candidate evaluator

The evaluator requires printing-only service; complete pricing; explicit approved
material, quality and exact profile IDs; model/quantity/duration/total limits;
current authoritative M06 provenance; confirmed units and dimensions; confirmed
requirements, noncritical use and ordinary tolerances; adequate lead time; valid
closed geometry, build fit and no unresolved warnings. Special notes or unknown
requirements force review. Missing threshold configuration is unknown, never pass.

Stock and capacity use independently versioned **simulation fixtures** with TTLs.
They aggregate required grams including allowances and serial seconds per profile.
Missing, expired, insufficient or zero availability cannot pass. Fixtures do not
create reservations, inventory or scheduling records. They cannot authorize checkout.

The M06 `self_intersections_not_checked` warning remains unresolved and forces
review. Simulation/uncalibrated presentation warnings alone are acknowledged
assumptions. A pure fully verified synthetic unit fixture can pass candidate rules;
real M06 results do not falsely gain manufacturability certification. Every result,
including candidate pass, has `binding_authorized=false` and `acceptable=false`.

## Immutable history and freshness

Alembic 0006 follows 0005 without rewriting 0001–0005. The only new tables are
pricing_policies, pricing_availability_fixtures, pricing_estimates and
pricing_estimate_lines. Policies and fixtures are immutable versions with an active
pointer. Estimates and cost lines are immutable. SQL enforces stage/currency/mode,
request/customer/item relationships, current analysis/scope provenance and deferred
cost-line balance. Pricing audit targets extend the existing audit table without
changing earlier request/system events.

A request lock plus pricing configuration advisory lock serializes mutations.
The same unexpired current source fingerprint is reused across concurrent commands.
Idempotency payload conflicts return 409. Audit, outbox, result and idempotency writes
commit together; failures leave no partial estimate. Cached evaluation responses
contain only pointers and recheck current resource and role authorization.

Snapshots include request version/revision/spec hash, file checksum, native analysis
and run IDs, engine executable/image/profile configuration, policy and fixture
versions, scope/rights/effort and evaluation day. Every read revalidates current
sources. Expiry, superseded result, changed scope/policy/fixture/profile/request or
calendar-dependent deadline invalidates current pricing. Historical amounts remain
private to Owner and are never returned as a current Customer total.

## Mini App and API

Customer and Owner printing/design detail pages show separate stage estimates.
Customers see totals, simulation notices and high-level review assumptions. Internal
costs, rates, margins, policy and detailed provenance remain Owner-only per
BUSINESS_RULES. React displays decimal strings without calculating prices or storing
request/pricing/authentication data in localStorage. It polls freshness and hides
cached amounts during validation, errors and expiry. Ambiguous mutations retry the
original body and idempotency key; explicit reload permits a new command.

Owner dashboard → Load pricing workspace → select stage → explicitly load the
hypothetical template → review/edit policy JSON and reason → publish a simulation
version. Decimal values are JSON strings; null means unknown. The same workspace
publishes stock/capacity fixture JSON, separately from the pricing policy. No
commercial policy is activated automatically. Large policy editors are a technical
Owner tool for this milestone; there is no customer-facing configuration JSON.

- `GET /api/v1/owner/pricing/configuration`
- `GET /api/v1/owner/pricing/hypothetical-policy?stage_kind=printing|design`
- `POST /api/v1/owner/pricing/policies`
- `POST /api/v1/owner/pricing/availability-fixtures`
- `POST /api/v1/requests/{id}/estimates` (printing; design requires Owner)
- `POST /api/v1/owner/requests/{id}/estimates`
- `GET /api/v1/requests/{id}/estimates` (customer-safe latest)
- `GET /api/v1/owner/requests/{id}/estimates` (private latest)
- `GET /api/v1/owner/requests/{id}/estimates/{estimate_id}` (private history)

Mutations require authenticated session, Origin, CSRF and idempotency. Config
publication includes expected configuration version and reason; evaluation includes
expected request version and Owner-only design basis when applicable. No endpoint
accepts an authoritative frontend price, role, profile result or paid status.
OpenAPI and generated TypeScript are the executable contracts.

## Recovery and milestone boundary

Use backup/forward migration for production recovery. Empty M07 state can be
removed by guarded downgrade in a disposable database; nonempty pricing or new
confirmation fields block destructive downgrade. Preserve immutable history.

M08 may introduce separately typed simulation_offer issuance and acceptance. A
future binding_offer must map to live operational mode through approved launch
and payment gates; a test_estimate cannot be updated into either offer kind.
M09 payment obligations, M10 stock holds and M11 capacity/assignment do not exist
here. No orders, quote acceptance, payments, model release, slicer execution from
pricing APIs or physical printer control is added.

Cost components can be inserted only in the transaction creating their estimate;
SQL rejects later appends, including zero-valued additions. A currency rounding
step cannot push an otherwise valid total past the accounting ceiling.
