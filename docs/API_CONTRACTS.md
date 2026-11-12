# HTTP API contract — proposal for FastAPI + React

## Implemented M05 design contract

Actual design endpoints, payloads, private-file purposes and simulation guards
are specified in [DESIGN_INTAKE.md](DESIGN_INTAKE.md) and exported OpenAPI/types.
Design projects are created with design-stage requests; legacy drafts initialize
explicitly. Brief/scope/proof/review/conversion commands reuse existing session,
CSRF, Origin, expected-version and idempotency conventions. Owner publishes proofs
and derives one linked printing draft; customer reviews exact current versions.
The delivery/quotation/payment endpoints below remain unimplemented plans.


M02 authentication, M03 project/request APIs and M04 private printing intake
are implemented. The actual OpenAPI export is `backend/openapi.json`; generated
React types are `miniapp/src/lib/api/schema.d.ts`. The exact M04 wire contract,
including raw binary upload headers, is in [PRINTING_INTAKE.md](PRINTING_INTAKE.md).
The future design, quotation, payment and production routes below remain plans.

## Cross-cutting conventions
- Prefix all application routes with `/api/v1` and serve from same HTTPS origin as Mini App.
- Authentication: server-side Telegram verified `initData` -> secure session cookie. No Telegram bot token in frontend.
- Response body uses typed Pydantic schemas; money values serialized as decimal strings; timestamp ISO 8601 with offsets; opaque IDs to frontend.
- Pagination: bounded lists only. M03 uses `limit` (1–100), `offset` (0–10000), `items` and `next_offset`; see ADR 0003. Future cursor/filter contracts must be explicit.
- Errors: documented `application/problem+json` or consistent JSON error schema (`code`, `message`, `details`, `correlation_id`); avoid leaking internals.
- For side effects, expect `Idempotency-Key` for financial/approval/transition commands and CSRF defenses for all cookie-authenticated mutations (including uploads). On conflict/stale version return 409, unauthorized 401, forbidden 403, not-found 404. Return 422 for schema validation failures, 413 for oversize uploads when applicable.
- **Quotations, orders, and payment obligations explicitly store `mode`, `stage`, `currency_code`, and permitted `payment_category`.** Payment attempts/verifications/refunds inherit and must validate these attributes through their immutable obligation relationship; do not duplicate mutable financial fields unnecessarily. The backend rejects cross-mode transitions, and no simulation record can be promoted by flipping an environment flag. **One project+stage may have at most one active payable order; duplicate quote-version acceptance conflicts. Verified external transaction keys are unique across obligations.** See `docs/PAYMENTS_COMPLIANCE.md` and `docs/INTEGRITY_RULES.md`.
- Authorization is checked per resource and per operation, not just per route prefix. `owner` may still act as a customer but cannot impersonate arbitrary users without explicit audit workflow.

## Auth and configuration
| Method | Endpoint | Purpose | Access |
|---|---|---|---|
| POST | `/api/v1/auth/telegram` | Verify raw initData, create session | Telegram context |
| GET | `/api/v1/auth/me` | Current user role, permissions, runtime mode | Authenticated |
| GET | `/api/v1/auth/csrf` | Obtain/refresh CSRF token for current cookie session if using synchronizer token approach | Authenticated |
| POST | `/api/v1/auth/logout` | Revoke session | Authenticated |
| GET | `/api/v1/catalog/materials` | Available materials/colors/quality presets | Authenticated |
| GET | `/api/v1/health` | Liveness (no secrets) | Public |
| GET | `/api/v1/ready` | M03 DB/schema readiness (no credentials) | Owner; internal gateway policy for deployment |

## Customer requests and uploads
| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/requests` | Atomically create parent `service_project` and first `service_request` stage (`printing` or `design`), returning both opaque IDs |
| GET | `/api/v1/requests` | List owned requests |
| GET | `/api/v1/requests/{id}` | Retrieve owned request |
| PATCH | `/api/v1/requests/{id}` | Update draft, optimistic version |
| POST | `/api/v1/requests/{id}/files` | Upload a model/reference tied to draft |
| GET | `/api/v1/files/{id}/download` | Authorized private download/stream |
| POST | `/api/v1/requests/{id}/submit` | Validate and submit draft |
| GET | `/api/v1/requests/{id}/analysis` | Safe analysis status and warnings |

M04 creates durable `pending` processing-task records; M06 activates isolated analysis workers. Before M06, do not report a task as `analyzing` merely because it is queued. For large files consider pre-authorized short-lived private uploads with completed-upload verification. Do not expose backend storage keys to clients. User supplied filenames are for display only.

## Design projects
A customer creates `service_type=custom_design` or `design_and_print` via the standard request API. The backend records a parent service project; the owner creates staged design work once the brief is accepted.
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/design-projects` | List owned / owner-scoped projects |
| GET | `/api/v1/design-projects/{id}` | Status, deliverable versions |
| POST | `/api/v1/owner/design-projects` | Open owner-scoped project from submitted design brief, if not created automatically |
| POST | `/api/v1/design-projects/{id}/reviews` | Approve exact proof or request revision (idempotent/versioned) |
| GET | `/api/v1/design-projects/{id}/deliveries` | Authorized access to digitally delivered files after payment/version gates |
| POST | `/api/v1/owner/design-projects/{id}/versions` | Publish new design proof (owner) |
| POST | `/api/v1/owner/design-projects/{id}/deliveries` | Release customer-approved design version/files after design-stage verification |
| POST | `/api/v1/owner/design-projects/{id}/create-print-request` | Idempotently derive one printing-stage request referencing approved design version |

## Quotations, orders and payment
`test_estimate` is view-only; a `simulation_offer` can only create a simulated order and mock payment; only `binding_offer` can create a live obligation after `BINDING_QUOTES_ENABLED` and all applicable release gates. Never expose a payment action on a `test_estimate`.
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/quotations` | List authorized offers with explicit mode and stage |
| GET | `/api/v1/requests/{id}/estimates` | Read nonbinding test estimates |
| GET | `/api/v1/quotations/{id}` | Quote and expiry/specs, no private cost detail for customer |
| POST | `/api/v1/quotations/{id}/accept` | Accept exact current version; idempotent |
| POST | `/api/v1/quotations/{id}/decline` | Decline |
| POST | `/api/v1/quotations/{id}/request-change` | Request revision |
| GET | `/api/v1/orders` | Orders accessible to current identity |
| GET | `/api/v1/orders/{id}` | Order status/timeline/payment obligation |
| POST | `/api/v1/orders/{id}/payment-attempts` | Submit permitted physical-goods payment evidence/reference **only for a checkout-eligible obligation with currently valid stock/capacity hold for printing**, or explicitly mocked simulation payment. Receipt evidence cannot bypass checkout gating; **never a manual receipt workaround for in-Telegram digital goods** |
| POST | `/api/v1/orders/{id}/checkout` | Revalidate mode, stage/category, approved quote and payment policy; for physical goods first establish/revalidate **real spool and printer-capacity holds** (M09 mocks do not permit live checkout). Start approved category-specific checkout; for live Telegram Stars create an invoice/link tied to one immutable obligation. Idempotent |
| GET | `/api/v1/orders/{id}/payments` | Own payment state |

## Owner operations
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/owner/dashboard` | Pending counts, recent orders |
| GET | `/api/v1/owner/reviews` | Filter/paginate special reviews |
| GET | `/api/v1/owner/requests` | Owner-scoped submitted requests (include design briefs) |
| POST | `/api/v1/owner/quotations` | Issue manual quotation or simulation offer against immutable spec/approval and pricing snapshots |
| GET | `/api/v1/owner/reviews/{id}` | Full review, flagged reasons and cost basis |
| POST | `/api/v1/owner/reviews/{id}/decision` | approve/clarify/revise/reject with reason/version |
| GET | `/api/v1/owner/payments` | Unverified attempts |
| POST | `/api/v1/owner/payments/{id}/verify` | Owner verifies real funds with audit reason |
| POST | `/api/v1/owner/payments/{id}/reject` | Reject evidence |
| GET | `/api/v1/owner/inventory` | Materials, spools, reservations |
| GET | `/api/v1/owner/capacity-holds` | Current printer-class capacity holds, expiry and conflicts |
| GET | `/api/v1/owner/payment-credits` | Immutable verified payment-credit/reversal reconciliation |
| POST | `/api/v1/owner/inventory/adjustments` | Audited movement |
| GET | `/api/v1/owner/printers` | Virtual and physical assets |
| GET | `/api/v1/owner/jobs` | Production board |
| POST | `/api/v1/owner/jobs/{id}/assignments` | Owner approves recommended assignment |
| POST | `/api/v1/owner/jobs/{id}/status` | Transition job state |
| POST | `/api/v1/owner/jobs/{id}/failures` | Record failure + waste |
| POST | `/api/v1/owner/failures/{id}/decision` | Approve reprint / other remediation |
| POST | `/api/v1/owner/jobs/{id}/quality-checks` | QC decision |
| GET | `/api/v1/owner/reports/summary` | Accounting dashboard aggregate |

## Example: authentication
`POST /api/v1/auth/telegram`
```json
{"init_data":"<raw Telegram.WebApp.initData>"}
```
On success create secure session cookie. Response:
```json
{"user":{"id":"usr_123","role":"customer","display_name":"Example"},"environment":"simulation","capabilities":["requests.create","orders.read_own"]}
```
Never let the JSON above be a source of server authority; user/role is resolved from verified Telegram ID and database record.

## Example: quotation (customer-safe)
```json
{
  "id": "q_123", "version": 2, "stage": "printing", "mode": "simulation_offer", "payment_category": "physical_goods",
  "status": "test_issued", "currency": "MMK", "total": "17000.00",
  "expires_at": "2026-12-01T10:00:00Z",
  "approval_method": "automatic",
  "items": [{"label": "phone_stand.stl", "quantity": 1, "material": "PLA", "quality": "standard"}],
  "actions": {"can_accept_for_simulation": true, "can_pay_real_money": false, "can_request_changes": true}
}
```
This example is a **simulation offer**, not a payable quote. An endpoint may instead return `test_estimate` (**no accept/pay actions**). Live `binding_offer` quotes require `BINDING_QUOTES_ENABLED` and category-specific checks; changing feature flags must never promote simulation records. Digital-stage live checkout uses `XTR` integral units where Telegram Stars applies.

## Telegram Stars provider event contract (M09)
- For approved digital-stage live checkout, the bot/backend issues an invoice tied to one immutable obligation and validates `pre_checkout_query` before answering it **within 10 seconds** (Telegram requirement): buyer, invoice payload, current obligation, amount, XTR currency, category, mode and expiry. Reject new checkout if stage/quote/approval is stale; never perform slow slicing inside the pre-checkout handler.
- Fulfillment/payment authorization is **not** inferred from opening an invoice, closing the payment UI, or a client callback. Persist a verified `successful_payment` update with Telegram charge ID, amount, currency, buyer and obligation mapping; deduplicate provider updates.
- Maintain the required owner verification/release gate after provider success until the business explicitly approves a different policy. Implement Stars refund events distinctly from manual physical-goods payment evidence.

## Backend event and transaction expectations
- Quote acceptance / payment verification / assignment approval requests include expected record version and idempotency key.
- Domain command commits DB state + audit + notification outbox atomically. **M03 creates the minimal transactional outbox and M08 uses it for first owner alerts; M13 adds mature retry/dead-letter handling, preferences and reporting.** Bot asynchronously pushes Telegram message and Mini App link; duplicate delivery is tolerated without duplicate business state.
- Owners retrieve detailed cost breakdown only via owner endpoints; customers never receive internal profitability fields.
- Implement OpenAPI-generated frontend types (`openapi-typescript` or equivalent) and contract tests for resource ownership and 400/401/403/404/409 errors.

## Implemented M06 simulation analysis

All endpoints use existing server sessions/ownership. Owner mutations additionally
require CSRF, exact Origin, expected request version and `Idempotency-Key`.

| Endpoint | Contract |
|---|---|
| `GET /api/v1/requests/{id}/analysis` | Current waiting/processing/completed/needs-clarification/manual-review/failed status; started unexpired leases alone set `processing_available` |
| `GET /api/v1/requests/{id}/analysis/results` | Current immutable, simulation-labeled results with dimensions, per-model estimates, quantity and exact provenance |
| `GET /api/v1/requests/{id}/items/{item}/analysis` | Same contract for an authorized current item |
| `GET /api/v1/catalog/simulation-profiles` | Bounded authenticated approved active virtual profiles; no editor |
| `GET /api/v1/owner/processing-tasks` | Owner-only bounded paginated queue, safe failure codes, attempts and special-requirement indicators; no lease tokens or paths |
| `POST /api/v1/owner/processing-tasks/{id}/retry` | Reasoned bounded simulation reschedule with optional compatible profile; terminal/current work only |

Print item specifications now accept all-or-none `dimension_x_mm`,
`dimension_y_mm`, `dimension_z_mm` and `dimension_tolerance_mm` (default 0.5),
without changing the default canonical representation of old submissions. Processing
task states extend to pending/leased/succeeded/failed/superseded. Request status may
be analyzing/manual_review while its submitted specification stays frozen. The API
exports no worker shell, arbitrary config, artifact/G-code download or live feature.
OpenAPI and TypeScript declarations are generated from actual FastAPI schemas.

## M07 implementation boundary

Implemented M07 endpoints, payload rules, Customer/Owner projections and freshness semantics are documented in [PRICING_POLICIES.md](PRICING_POLICIES.md). The generated OpenAPI uses currency_code and decimal strings. Planned quotation routes elsewhere in this document remain future work.
