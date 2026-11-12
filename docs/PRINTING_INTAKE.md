# Printing intake runbook

M04 behavior below remains the printing foundation. M05 adds
[design intake](DESIGN_INTAKE.md) and extends migration head to
`0004_design_intake`. For derived combined-stage drafts, Customer can configure
and submit only the approved manufacturing bytes; source downloads remain denied.
The Owner explicitly attaches the source model through this existing upload
infrastructure. No design-stage paid state or delivery right transfers.

M04 implements private printing drafts and submitted requests in simulation.
It reuses M02 sessions and M03 business transactions. See
[ADR 0004](adr/0004-private-printing-intake.md) and
[the implementation report](M04_IMPLEMENTATION_REPORT.md).

## Run and migrate

Use the existing pinned Python/uv and Node/npm environments. No runtime or npm
dependency was added. Configure backend-only values from `.env.example` with a
test bot and development/test database. Keep simulation true and every live/
development-auth flag false. Never put backend secrets in `VITE_*` variables.

```sh
cd backend
uv sync --frozen
.venv/bin/python -m dotenv -f ../.env.local run -- .venv/bin/alembic upgrade head
.venv/bin/python -m dotenv -f ../.env.local run -- .venv/bin/alembic current
.venv/bin/python -m dotenv -f ../.env.local run -- .venv/bin/alembic check
.venv/bin/uvicorn app.main:create_app --factory --env-file ../.env.local --host 127.0.0.1 --port 8000 --no-proxy-headers
```

The ignored root `.env.local` is loaded explicitly; Settings does not auto-read
files. Head is `0003_printing_intake`, following immutable 0001/0002. No automatic
startup migration. Existing M03 rows retain their hashes/relationships. Review
and back up both DB and private storage before applying to retained environments.
Downgrade with intake data is intentionally refused; do not erase history.

Run `cd miniapp && npm ci && npm run dev` separately. Real sessions need a valid
Telegram test launch through one HTTPS gateway and exact `PUBLIC_BASE_URL`.
`VITE_TELEGRAM_MOCK=true` enables isolated UI presentation only; it cannot save
real drafts, provision identities or bypass backend authorization.

Compose mounts `private_uploads:/srv/private_uploads` on the API. Its directory
is created for UID 10001 and mode 0700; blobs use 0600. The bot has no model
volume. Private storage must never be mounted by a static server or gateway.
Local host default is `backend/.local/private_models`; these paths are ignored
and excluded from build context. Do not point `STORAGE_ROOT` at application or
frontend source/static directories. Multiple API instances need one shared
private volume until an object-storage adapter is reviewed.

## Current API contract

Every route below begins `/api/v1`. Reads require a current session and resource
ownership or trusted Owner. Mutations additionally require exact Origin,
`X-CSRF-Token`, `Idempotency-Key` (8–128 ASCII letters/digits/underscore/hyphen)
and an expected request version. JSON bodies are limited to 32 KiB and reject
unknown properties. Owner may inspect customer requests but not edit their specs.

| Method/path | Body or purpose |
|---|---|
| `GET /catalog/printing-options` | Development-only material/color/quality/unit options and file limits |
| `POST /requests` | Existing `{service_type:"printing", customer_notes?}` creates parent + draft |
| `GET /requests` | Existing own-request list; bounded limit/offset |
| `GET /owner/requests?status=submitted&stage_kind=printing` | Owner-only filtered list |
| `GET /requests/{id}/intake` | Current request, active items, file metadata, task status, customer display name |
| `PATCH /requests/{id}/intake` | `{expected_version, customer_notes?, fulfillment_method?, fulfillment_notes?}` |
| `POST /requests/{id}/items` | `{expected_version, specification?}` creates empty/configured item (201) |
| `PATCH /requests/{id}/items/{item}` | `{expected_version, specification}` updates full per-item spec |
| `DELETE /requests/{id}/items/{item}` | JSON `{expected_version}`; deactivate item, queue its blob cleanup |
| `POST /requests/{id}/files?item_id=UUID&expected_version=N` | Raw binary upload described below (201) |
| `GET /files/{id}` | Authorized safe metadata, never storage key |
| `GET /files/{id}/download` | Cleared private bytes, authenticated attachment; no-store/nosniff/sandbox |
| `POST /requests/{id}/submit` | JSON `{expected_version}`; validate and freeze snapshot; tasks stay pending |
| `GET /requests/{id}/analysis` | `not_submitted`, `pending` or `superseded`; `processing_available:false` |

Upload uses **raw bytes**, `Content-Type: application/octet-stream`,
`X-File-Name` (percent-encoded UTF-8 plain name), `X-File-Size` (positive byte
count), `X-Content-SHA256` (lowercase 64-hex checksum), CSRF and idempotency
headers. It is not multipart. The route reserves quota before reading the body.
The server verifies actual count, digest and content, never trusting extension
or MIME alone. Exact completed-key replay consumes/verifies the body and checks
current access without attaching twice. A different file under that key is 409.
Retry failed uploads with the same key after recovery; different bytes need a
new key. Only one current model per item; remove the draft item to replace it.

Per-item spec: description, quantity (1–1000), material_key, color_key,
quality_key, unit_key, unit_confirmed, special_requirements. Fulfillment uses
pickup/delivery **preferences**, not a commercial delivery promise. Submission
requires at least one complete item, compatible catalog choices and confirmed
units. For 3MF, units must match the file declaration. Every current model must
be validated, ready and byte-verifiable. Generic M03 `/transitions` cannot
bypass this guard. Design-stage intake/derivation remains deferred to M05.

Errors: 401 expired/missing session; 403 CSRF/Origin/Owner violations (or 404 for
inaccessible resource); 409 stale version/key/state; 413 byte cap; 415 unsupported
format/reference/profile; 422 malformed/incomplete specification/model; 429 rate
or storage quota; 503 storage/database unavailable. Errors have safe code/message/
correlation_id; never raw file contents or credentials.

## Storage limits and validation

| Setting | Default |
|---|---|
| `UPLOAD_MAX_BYTES` | 25 MiB per file (hard configurable ceiling 100 MiB) |
| `REQUEST_STORAGE_BYTES` / `REQUEST_FILE_LIMIT` | 100 MiB / 10 files |
| `USER_STORAGE_BYTES` / `USER_FILE_LIMIT` | 500 MiB / 100 files |
| `TOTAL_STORAGE_BYTES` / `TOTAL_FILE_LIMIT` | 2 GiB / 10000 files |
| `MAX_INFLIGHT_UPLOADS` | 2 globally across shared DB |
| `UPLOAD_TIMEOUT_SECONDS` / `UPLOAD_LEASE_SECONDS` | 60 / 120 seconds |
| `VALIDATION_TIMEOUT_SECONDS` / `VALIDATION_CPU_SECONDS` | 15 wall / 5 CPU seconds |
| `ARCHIVE_ENTRY_LIMIT` | 64 entries |
| `ARCHIVE_EXPANDED_BYTES` / `ARCHIVE_ENTRY_BYTES` | 64 MiB total / 16 MiB per entry |
| `ARCHIVE_RATIO_LIMIT` | 100:1 per entry |
| `INTAKE_RATE_LIMIT` / `UPLOAD_RATE_LIMIT` | 120 mutations / 10 uploads per actor per 60 seconds |

Private download/metadata reads also use a separate 120-per-actor window. Limits
are enforced server-side; proxy body/connection/time limits still need review
before public traffic. Quotas count receiving, quarantined and delete-pending
reservations until successful physical deletion, including removed/cancelled
models where applicable. Files from cancelled drafts are retained, not silently
purged. `request_file_limit` also bounds active item creation.

STL supports binary and strict ASCII triangles. OBJ accepts bounded mesh records
and rejects external materials/textures, calls and unsupported commands. Export
an untextured standalone mesh before upload. 3MF currently accepts one Core
model part (`3D/3dmodel.model`) plus standard OPC relationships/content types;
optional known directories are allowed. Embedded textures, thumbnails, foreign
extensions and extra model parts are rejected. ZIP paths, symlinks, counts,
ratios, decompression, XML, units, transforms and object references are checked.
No archive is extracted. Common slicer project archives may need a clean Core
3MF export. “Format checked” does not imply scale, watertightness, quality,
printability, analysis completion or a price.

Validation uses a cleared-environment resource-bounded subprocess, with no
inherited bot token/DSN/descriptors and no network fetch logic. It shares the
API container UID/kernel/filesystem/network namespaces. It is **not** a full
OS security sandbox. Stronger worker/container/VM isolation and adversarial
hardening remain prerequisites for M06 and public intake release.

## Failure recovery and maintenance

Database reservations name every normally created blob before filesystem I/O.
Short transactions fence upload completion/cleanup using lease, state and key.
Expired/failed uploads cannot attach or submit. Cleanup never selects committed
ready files, including after an ambiguous DB commit. Failed unlink keeps the
reservation charged until a retry succeeds. Ready-blob SHA/size is rechecked
before submission and download; missing/tampered files fail closed.

Run bounded cleanup using the **same private root and database** as the API:

```sh
cd backend
PYTHONPATH=. .venv/bin/python -m dotenv -f ../.env.local run -- .venv/bin/python scripts/cleanup_uploads.py
# Compose alternative after reviewed image/migrations:
docker compose --env-file .env.local run --rm --no-deps api python scripts/cleanup_uploads.py
```

A run handles at most 100 expired/delete-pending reservations. Upload attempts
and item removal also trigger bounded cleanup. Schedule the CLI periodically
in the chosen nonproduction/staging environment; no permanent scheduler is
created in Codex Cloud. Do not recursively prune ready storage or delete by
filename/mtime. DB outages retain durable charged reservations for later recovery.
Retained-ready-file deletion, retention windows, consent, encryption, backup/
restore and object storage need explicit operational decisions before release.

Draft changes use optimistic versions and canonical backend hashes. Failed
changes preserve committed specs. Submission status, frozen snapshot, per-model
pending tasks, audit, outbox and result are one transaction. Exact retries
cannot create duplicate tasks/events; stale versions conflict. Submitted specs
cannot be reopened through M04. M06 must honor exact file/revision/hash and
supersession; no future approval table is invented here.

## Checks in Codex Cloud / local development

Use only disposable loopback databases named `3dps_test*`; tests intentionally
refuse missing, remote or non-test targets. Database fixtures create/drop only
their own migration databases and truncate only the selected disposable target.

```sh
cd backend
TEST_DATABASE_URL='<disposable loopback asyncpg DSN>' uv run --frozen pytest -q --tb=short
uv run --frozen ruff check app alembic tests scripts ../telegram_bot
uv run --frozen mypy app scripts ../telegram_bot
DATABASE_URL='<disposable DSN>' uv run --frozen alembic upgrade head
DATABASE_URL='<disposable DSN>' uv run --frozen alembic check
PYTHONPATH=. uv run --frozen python scripts/export_openapi.py
cd ../tools/api-types
npm ci
npm run generate
cd ../../miniapp
npm ci
npm run check
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e
```

Omit the executable override when Playwright's versioned Chromium is installed.
Regenerate OpenAPI/types twice and compare hashes; CI uses `git diff --exit-code`
against committed artifacts. Build actual production React before running the
real-stack harness against an **already migrated** separate browser DB:

```sh
npm run build
TEST_BROWSER_DATABASE_URL='<loopback DSN /3dps_test_browser_SUFFIX>' \
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium \
node scripts/test-auth-integration.mjs
```

This runs a temporary loopback HTTPS gateway, host API and synthetic launch data
signed outside the browser. Only Telegram's presentation SDK is intercepted;
all API/DB operations are real. It checks M02/M03 plus mobile multi-model intake,
autosave/reload, submit, private access and Owner inspection. Container mode
(`TEST_CONTAINER_API=true`) uses an already-running disposable production-mode
API at loopback 18002 with matching test settings; caller owns cleanup. CI builds/
migrates/starts that container and executes the same flows. Hosted CI results
must be observed separately; local success does not certify Actions execution.

## External verification and next boundaries

With an explicitly configured **test bot**, HTTPS staging and private test data,
exercise Android, iOS and Desktop Telegram: launch/login, theme/safe area, file
picker for STL/OBJ/Core 3MF, progress/cancel/retry, slow/offline upload, session
expiry, autosave/reload/relaunch, pending submission, and private download support.
Use two customer accounts and the server-provisioned Owner. Verify intended
Caddy proxy Origin/CSRF/cookie behavior, body/time limits, and storage persistence
across container recreation/backup restore. Real Telegram WebView download
handling may require a later approved adapter; desktop Chromium evidence is not
a real-device pass or G1 acceptance.

M05 must add design briefs/scope/version lineage without widening mesh-upload
permissions accidentally. M06 must introduce isolated task execution, leases,
retries and analysis output with exact provenance; pending must remain distinct
from running/success. No slicing or commercial/live operations are introduced by
this intake implementation.

## M06 analysis continuation

Submitted M04 tasks can now be claimed by the separately operated trusted worker.
A pending task still does not imply running analysis. The customer details page
polls actual authorized status and displays per-model simulation results or review
reasons. Optional target dimensions in millimeters augment explicit unit confirmation.
Submitted specifications remain frozen; clarification is an Owner/customer review,
not a silent edit or model repair. The Owner processing queue exposes safe failure
and special-requirement indicators with reasoned bounded retries. Existing derived
M05 printing drafts retain their exact approved source-design lineage and undergo
the same file/spec/task checks. No design-source delivery right is changed.
