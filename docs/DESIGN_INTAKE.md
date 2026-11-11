# M05 design intake runbook

M05 adds persistent design briefs, simulation scope/proof review and exact
approved-version conversion into a separate printing draft. It preserves M02
sessions and M04 private storage. See [ADR 0005](adr/0005-design-intake-and-lineage.md)
and [M05_IMPLEMENTATION_REPORT.md](M05_IMPLEMENTATION_REPORT.md).

## Run and migrate

Use the existing pinned Node/npm and Python/uv environments. M05 adds pinned
Pillow 13.0.0 in `backend/uv.lock` and hash-exported `requirements.txt`; it verifies
reference/proof images inside the resource-bounded subprocess. No npm dependency
was added. Configure an ignored root `.env.local` with test-only credentials and
a private development database, following [AUTHENTICATION.md](AUTHENTICATION.md).
Settings does not auto-read files; load configuration explicitly.

```sh
cd backend
uv sync --frozen
.venv/bin/python -m dotenv -f ../.env.local run -- .venv/bin/alembic upgrade head
.venv/bin/python -m dotenv -f ../.env.local run -- .venv/bin/alembic check
.venv/bin/uvicorn app.main:create_app --factory --env-file ../.env.local --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
```

Head is `0004_design_intake`, following 0003/0002/0001 without rewriting them.
Back up DB and private storage before applying to retained environments. M05
populated downgrade refuses; use reviewed recovery. Compose's private volume
and all existing quota/cleanup controls remain in use. Simulation must stay true;
all live and development-auth flags remain false. Production configuration does
not authorize real work: no public deployment is performed by this milestone.
Run `cd miniapp && npm ci && npm run dev` behind the configured same-origin HTTPS
gateway for real test Telegram authentication. UI mock grants no API identity.

## Customer and Owner workflow

1. Customer opens `/app/requests/design`, selects Custom Design or Design +
   Printing and creates a durable design-stage draft. Existing request lists link
   to `/app/design-requests/{requestId}`; legacy drafts have an explicit initialize
   action. New design projects open at `/app/design-projects/{id}`.
2. Brief fields cover description/intended use, dimensions/units/tolerances,
   manufacturing/material preferences, desired date, special needs and requested
   deliverables. Autosave persists to PostgreSQL; uncertain dimensions/tolerances
   can say “Not sure” for Owner review. Date is a preference, not a promised SLA.
   Upload optional private references, then review and submit. No print items,
   STL, filament or printer is required. Committed data survives reload.
3. Owner opens the dashboard Design Review workspace or `/owner/designs/{id}`.
   Propose scope with deliverables, revision limit, exclusions and digital rights.
   Customer agrees to the exact latest proposal. It is explicitly non-binding
   simulation scope; real contractual quotation belongs to M08.
4. Owner explicitly confirms “simulation with no real funds” and activates the
   scope-bound quote-and-paid **fixture**. Before this action proof uploads and
   publication fail. This fixture creates no real or simulated financial ledger,
   quote amount, payable order or payment service. Future live designing must
   require its own verified advance payment, not this field.
5. Owner uploads a safe preview and optional private manufacturing STL/Core 3MF/
   OBJ, then publishes an immutable numbered proof. Customer views the authorized
   preview and approves or requests revisions to that exact current version.
   Revision feedback is required. New proof publication clears old approval;
   old scope/proof/review history remains. Scope revision limit counts published
   versions after the first, not arbitrary paid authorizations.
6. For combined service only, Owner creates one linked printing draft after an
   approved manufacturing-ready version. It has one incomplete print item. Owner
   then explicitly attaches the approved manufacturing model through the private
   M04 storage flow. Customer completes real printing specs in the existing wizard
   and submits; source SHA must match. Printing starts in draft and progresses
   independently. It receives no design-stage paid state or production permission.

Standalone design requires digital delivery in requested/agreed scope; combined
service requires printing with optional digital rights. **No digital delivery is
implemented**: only review previews can be read by the customer. Manufacturing
models and their derived print copies remain non-downloadable to the customer,
even when a scope includes future delivery rights. Owner access is authenticated.
Approved manufacturing-only design stays `approved`; no fake `delivered` state
or file entitlement is created. M12 must define its completion/handoff policy.

## File policy and recovery

Reference and proof previews support **PNG, JPEG and plain UTF-8 TXT**. Drawings
must be exported as permitted raster images/text. PDF/SVG/Office/HTML/RTF and
reference archives are rejected. Images require real decoding/verification,
correct end markers, one frame, maximum 8000 pixels per dimension / 16 million
pixels. TXT is bounded to 1 MiB and rendered as escaped text. Models reuse the
M04 conservative STL/Core 3MF/OBJ validators; no analysis/slicing is executed.
The existing per-file/request/customer/global quota, rate and subprocess limits
apply; total receiving and delete-pending bytes remain charged until deletion.

Raw bytes use opaque keys in private incoming/quarantine/ready directories, with
0600 blobs and 0700 directories. No static serving or public URL exists. Every
metadata/download request rechecks access. Unpublished proof and manufacturing
metadata/downloads are denied to customers; published preview does not grant
source-file rights. Source keys and server secrets never reach React.

Customers can remove their own draft references; removal updates revision and
queues lease-safe deletion. Submitted references and published proof provenance
are frozen. Upload failures preserve prior committed data and quota reservations
recover through the existing bounded CLI; see [PRINTING_INTAKE.md](PRINTING_INTAKE.md).
Re-select unfinished files after reload; retry keys/File objects remain in memory.
After ambiguous creation, inspect saved projects before issuing a new create key.

The validator clears inherited credentials/descriptors and enforces resource
limits, but shares the API container's UID/network/filesystem namespaces. It is
not a complete OS sandbox. Stronger isolation/adversarial hardening, retention,
encryption and DB/private-volume backup restore remain public-release work.

## API contract

All routes start `/api/v1`. Existing `/requests` creates service projects and
initial stages. Reads need current authenticated ownership or trusted Owner;
mutations also need exact Origin, session CSRF, `Idempotency-Key` and
`expected_version` (the design stage request version, except print attachment).
Inputs reject unknown fields, JSON is bounded to 32 KiB and mutations are audited
with atomic outbox/idempotency records. Refer to exported `backend/openapi.json`
and generated `miniapp/src/lib/api/schema.d.ts` for exact field schemas.

| Method/path | Behavior |
|---|---|
| `GET /requests/{id}/design` | Current design for an authorized design-stage request |
| `POST /requests/{id}/design` | Explicit initialization of a legacy draft, `{expected_version}` |
| `GET /design-projects?limit=20&offset=0` | Own list, or all for current Owner; bounded pagination |
| `GET /design-projects/{id}` | Brief, scope/version history, safe files and linked-stage progress |
| `PATCH /design-projects/{id}/brief` | Customer draft autosave `{expected_version, brief}` |
| `POST /design-projects/{id}/submit` | Freeze valid brief/current reference snapshot; no STL needed |
| `POST /requests/{id}/design/files?purpose=...&expected_version=N` | Raw private upload; purposes `design_reference`, `design_proof`, `design_manufacturing` |
| `POST /design-projects/{id}/remove-reference` | Customer draft removal `{expected_version, file_id}` |
| `POST /owner/design-projects/{id}/scopes` | Propose immutable scope `{expected_version, scope, reason}` |
| `POST /design-projects/{id}/scope-agreements` | Exact latest scope `{expected_version, scope_id}` |
| `POST /owner/design-projects/{id}/simulation-fixture` | Explicit `{expected_version, confirm_simulation:true, reason}` |
| `POST /owner/design-projects/{id}/versions` | Publish exact preview/model IDs, readiness and release notes |
| `POST /design-projects/{id}/reviews` | Exact current version, `approved`/`changes_requested`, feedback |
| `POST /owner/design-projects/{id}/create-print-request` | Exact approved design-version conversion, idempotent |
| `POST /owner/design-projects/{id}/attach-print-model` | Attach approved bytes through M04; expected **printing** request version |
| `GET /files/{id}` / `/files/{id}/download` | Existing authenticated file service with purpose/publication policy |

Uploads use raw `application/octet-stream`, percent-encoded `X-File-Name`,
`X-File-Size`, lowercase `X-Content-SHA256`, CSRF and command key, as in M04.
The server derives customer, uploader and role; no ownership/role fields are
accepted from the client. References may be uploaded only to own drafts; only
Owner can upload proofs/manufacturing models after the explicit fixture.
History is bounded (100 scope proposals / 100 published proofs per project),
with quota limits normally reached earlier. M04 model upload fingerprints and
old cached response DTOs remain compatible.

Errors: 401 expired/missing session; 403 Owner/CSRF/Origin/forbidden source release;
404 inaccessible resource; 409 stale version/scope/proof/lineage/idempotency;
413 byte cap; 415 unsupported content; 422 incomplete/invalid brief/spec/file;
429 rate/quota/history limits; 503 storage/database unavailable. A failed command
leaves committed domain state unchanged. Concurrent reviews/conversion serialize
under request locks; uniqueness constraints backstop duplicate stages/reviews.

## Tests and external verification

Use disposable loopback `3dps_test*` databases only. Existing commands in the
printing/authentication runbooks still apply: backend pytest/Ruff/Mypy, Alembic
upgrade/check, OpenAPI/TS generation with drift checks, `miniapp npm run check`,
Playwright and the real-stack Node harness. The harness now runs **14 flows**:
previous 10 plus complete M05 design-to-print intake through actual HTTPS,
FastAPI and PostgreSQL. Container mode tests the production API image with the
same synthetic credentials; callers own temporary services/data cleanup.

Real Telegram Android/iOS/Desktop testing remains external: test-bot launch,
cookies/CSRF through intended Caddy HTTPS, image/text upload/cancel/retry, slow
connections/session expiry, autosave/relaunch, safe proof rendering, exact-version
review and two-customer isolation. Check mobile keyboard/safe-area behavior and
private download support. Desktop Chromium is not G1/device acceptance. Hosted
CI execution must be observed separately from local success.

M06 must add isolated task execution with exact model/request/hash provenance;
M07/M08 add design pricing/quotations, M09 verified stage funds, and M12 authorized
delivery/completion. None is implemented or enabled by M05.
