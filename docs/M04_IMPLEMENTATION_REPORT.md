# M04 implementation report

Date: 2026-11-11 (Asia/Rangoon). Status: **implemented; stopped for review**.
Branch: `codex/m04-secure-printing-intake`, created directly from accepted M03
`3ae6f5c94d9ebbefce2c863c1968a9734ff51078`. No history rewrite, merge, publication,
deployment, live feature enablement or M05/M06 implementation was performed.
The subsequent Owner instruction authorizes committing and pushing the M04
branch. This authorization does not permit merging, deployment or M05/M06 work.

## Delivered behavior

Customers can authenticate using unchanged M02 identity/session verification,
create a printing draft under its existing M03 project, upload multiple private
STL/Core 3MF/OBJ models, autosave per-model specs and fulfillment preferences,
reload/resume committed drafts and submit once. Backend options are clearly
labeled development-only; uncertain choices require later Owner review. Owner
can list submitted printing requests, inspect specs/special requirements and
download cleared models. Pending analysis is explicitly unavailable for execution.

The actual requested prompt and acceptance paths were verified, including
`prompts/M04_SECURE_CUSTOMER_PRINTING_INTAKE.md` and
`docs/M03_FINAL_ACCEPTANCE_REVIEW.md` (without a literal backslash). Root AGENTS,
roadmap, architecture, data model, state/integrity/dependency contracts, security,
API/frontend specs and M03 implementation/tests were inspected first. The accepted
M03 code was extended, retaining its original M02/M03 regression test functions.

## Schema, transactions and security

- One Alembic history: `base -> 0001_auth_foundation ->
  0002_business_foundation -> 0003_printing_intake (head)`. Original revisions
  and Telegram verifier/auth service/auth routes/identity models are unchanged.
- Exactly three new tables: `request_items`, `uploaded_files`, `processing_tasks`.
  Request fields cover fulfillment, spec schema version and immutable submitted
  snapshot/revision/time. Composite FKs enforce request/customer/stage/item/file
  lineage; unique task tuple prevents duplicate request/revision/file/kind work.
  Only `pending`/`superseded` task states are supported. No speculative future
  domain tables, worker execution, analysis outputs or payable records were added.
- Uploads reserve durable quota before private I/O. Short DB locks protect actor,
  session, request and global quotas; stream/validation runs without holding those
  locks. Opaque keys, private quarantine, bounded byte/hash streaming, structural
  content checks, archive limits, subprocess resource limits and safe attachment
  promotion are enforced. No public/static file route or storage key exposure.
- Upload completion rechecks session, request version and lease. Every relevant
  read checks current authorization. CSRF/Origin and DB-backed mutation/upload/
  private-read rate counters are enforced. Only configured server identities can
  be Owner; Customer cannot access Owner APIs or another customer's request/file.
- Canonical backend spec v2 binds sorted items/specs, exact file IDs/SHA/format/
  bytes and preferences. Meaningful edits advance revision/version and supersede
  older task references; unchanged specs do not. Original M03 hashes are retained
  as v1 until edited. File provenance retains original upload revision.
- Submission verifies complete settings, confirmed units (including 3MF units),
  cleared/ready/current files and actual stored bytes. Status, frozen snapshot,
  pending tasks, audit, minimized outbox event and idempotency response commit
  atomically. Exact retries create no duplicate tasks/audits/transitions. Stale
  versions and conflicting keys fail. SQL triggers freeze submitted data and
  validated-file provenance. M03 generic transitions cannot bypass submission.
- Failed storage/validation/DB work preserves committed drafts. Recovery never
  deletes a committed ready blob after an ambiguous commit. Expired/delete-pending
  reservations stay quota-charged until actual deletion. CLI recovery is bounded
  and never prunes ready files. UI pauses stale/ambiguous queued mutations until
  exact retry or explicit reload; no sensitive browser localStorage persistence.

See [ADR 0004](adr/0004-private-printing-intake.md) for decisions and
[PRINTING_INTAKE.md](PRINTING_INTAKE.md) for wire contracts/configuration/recovery.

## Actual checks and results

All data used was synthetic, in task-owned loopback PostgreSQL 16.15 databases.
Final main database: `3dps_test_m04_final`, host/container browser databases:
`3dps_test_browser_m04` / `3dps_test_browser_m04container`. No production data,
real bot credentials or live network business operation was used. DSNs below
are intentionally represented by placeholders rather than copying credentials.

| Working directory / actual command | Result |
|---|---|
| `backend`: `TEST_DATABASE_URL=<loopback test DSN> .venv/bin/pytest -q --tb=short` | **260 passed in 58.68s**; all M02/M03 regressions retained, 80 additional M04 cases |
| `backend`: `TEST_DATABASE_URL=<test DSN> .venv/bin/pytest tests/test_migrations.py -q --tb=short` | **4 passed in 8.06s**; also included in full suite |
| `backend`: `.venv/bin/ruff check app alembic tests scripts ../telegram_bot` | PASS |
| `backend`: `.venv/bin/mypy app scripts ../telegram_bot` | PASS, **37 source files** |
| `backend`: `DATABASE_URL=<disposable DSN> .venv/bin/alembic upgrade head`, `heads`, `current`, `history`, `check` | Fresh upgrade PASS; only head **0003**; **No new upgrade operations detected** |
| `backend`: `PYTHONPATH=. .venv/bin/python scripts/export_openapi.py`; `tools/api-types`: `npm run generate`; root: `sha256sum --check .local/m04-contract-before.sha256` | PASS; repeated export/regeneration byte-identical for OpenAPI and TS declarations |
| `miniapp`: `npm run check` | PASS: strict TS, zero-warning ESLint, **78 tests in 7 files**, production Vite build and forced-mock production exclusion |
| `miniapp`: `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e` | **10 passed in 11.8s**, final UI version; navigation/themes at 320/390/768/1440px and production permissions/mock isolation |
| `miniapp`: `TEST_BROWSER_DATABASE_URL=<host browser DSN> PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium node scripts/test-auth-integration.mjs` | **10/10 real-stack flows PASS**; production React + ephemeral HTTPS + host FastAPI + PostgreSQL; no API mocks |
| Root: explicit local-socket `docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -f backend/Dockerfile -t 3dps-api:m04-review .` | PASS; image `sha256:3405d0a63cdb879fbe23943574ceac89789e075f299d86782b438f70944af9a8` |
| Root: `docker run --rm --network 3dps-m04-review --env-file .local/m04-container.env 3dps-api:m04-review alembic upgrade head` | PASS on fresh separate container-test DB |
| Root: `docker run --detach --name 3dps-m04-api-review --network 3dps-m04-review --publish 127.0.0.1:18002:8000 --mount type=volume,src=3dps-m04-private,dst=/srv/private_uploads --env-file .local/m04-container.env 3dps-api:m04-review` | PASS; startup and `/api/v1/health` return OK; task bridge attachment provides loopback-only test access |
| `miniapp`: `TEST_CONTAINER_API=true TEST_BROWSER_DATABASE_URL=<container browser DSN> PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium node scripts/test-auth-integration.mjs` | **10/10 flows PASS**, repeated after final UI fixes; packaged production-mode API |
| Root: `docker exec 3dps-m04-api-review alembic current` / `alembic check` and Python Settings/UID/mode probe | **0003 head**, no drift, UID **10001**, private root **0700**, simulation true, all unsafe flags false |
| Root: remove/recreate only task API container with same named volume; Python DB/storage checksum probe; health request | PASS: **4 committed model blobs** survive recreation, each SHA/size verified, mode **0600**, UID10001; health OK |
| Root: `docker exec 3dps-m04-api-review python scripts/cleanup_uploads.py` | PASS; **0** expired/delete-pending rows, ready models preserved; injected crash/deletion failure cases covered in pytest |
| Root: `git diff --exit-code 3ae6f5c -- <0001/0002/auth routes/auth service/identity models/core Telegram verifier>` | PASS: approved auth/history files unchanged |
| Root: `node --check miniapp/scripts/test-auth-integration.mjs`; `git diff --check`; `docker compose config --quiet` with synthetic development environment | PASS |

Docker commands used the managed local Unix socket with endpoint/context/TLS
selectors cleared; session proxy/CA policy was preserved. The CA was a build
secret, not an image layer. Only task-owned databases/containers/volume/network
were modified; temporary test services and their private volume were removed
after verification. No environment configuration or production service was published.

The 10 real-stack flows include the previous seven M02/M03 flows, plus complete
mobile multiple-model upload/autosave/reload/submission, customer isolation/private
byte-exact download, and Owner queue/spec/special-requirements/download/pending
inspection. Screenshots were generated and visually checked at
`miniapp/test-results/m04-customer-mobile.png` and `m04-owner-desktop.png`
(ignored test artifacts, synthetic fixtures only). Visual inspection prompted
card spacing and nested Owner workspace-label corrections.

Required security/integrity coverage is present: valid STL/3MF/OBJ, malformed/
truncated/empty/oversize files, archive traversal/expansion/CRC/unsafe references,
cross-customer/Owner denial, CSRF/Origin/session checks, multiple models, concurrent
quota reservations and draft edits, idempotent/concurrent submission, duplicate
task DB constraint, stale versions, DB/file lineage, missing/tampered blobs,
expired sessions during stream/submission, supersession, frozen snapshots,
storage/DB/outbox failures and crash/ambiguous-commit cleanup. Frontend tests cover
autosave/reload, submission, conflict/retry and upload progress/cancel/same-key
retry. Production artifact tests force the mock flag on and verify its exclusion.

During verification, missing test/runtime configuration correctly refused an
early pytest/cleanup invocation. A newly added migration seed initially used a
JSON literal parsed as a SQL bind; it now uses safe spacing and passes. New UI
tests needed a standard WebCrypto stub and precise selectors. Final checks have
no failures or skipped PostgreSQL substitutes. Implementation review also fixed
ambiguous-commit cleanup, quota-release timing and queued stale-change handling;
regression cases now cover them.

## CI status

`.github/workflows/authentication.yml` retains real PostgreSQL tests, migration
metadata, generated-contract drift, host-browser integration and production
container build/start/browser checks; it now exercises the expanded M04 harness.
Container CI now mounts private storage and runs bounded cleanup; Compose also
forwards the documented quota/validation limits. The existing frontend workflow
runs the frontend checks/Playwright suite.
**Hosted GitHub Actions was not executed or observed during implementation
verification.** Local test success is not a claim of green hosted CI. The
subsequent Owner instruction authorizes branch push, which can trigger the
configured workflows. No hosted result is claimed here; no PR, merge or
deployment is authorized by that handoff instruction.

## Remaining limitations and decisions

1. Real Telegram Android/iOS/Desktop clients, BotFather test-bot launch and the
   intended Caddy deployment remain external verification. Chromium loopback
   HTTPS is not G1 device acceptance. WebView file-picker/download behavior,
   slow network/expiry/relaunch, themes/safe areas and gateway limits need the
   test procedure in PRINTING_INTAKE.md.
2. Structural validators intentionally accept a conservative subset. OBJ
   materials/textures and extra/extended 3MF parts are rejected; clean standalone
   mesh exports are required. No watertightness, dimensions/volume, calibrated
   scale, manufacturability, pricing or successful-analysis claim is made.
3. Subprocess credential/environment/resource isolation is implemented, but
   UID/filesystem/network namespaces are shared with the API container. Stronger
   OS/worker isolation and adversarial parser review remain required before
   public intake and M06; model parsing must not be treated as a complete sandbox.
4. Local storage assumes one shared private volume. Object storage, encryption,
   backups/restore, retained-file deletion/privacy/retention and periodic CLI
   scheduling require operational review. Ready/cancelled files remain charged;
   no unsafe ready-file garbage collector or retention policy was invented.
5. Submitted corrections/reopening are deliberately unavailable. Later work
   must define successor revisions with frozen history and exact downstream
   approval invalidation. No analysis/approval tables exist to invalidate today.
6. UI command keys and unfinished File objects live only in memory. Reload
   restores committed backend drafts; interrupted transfers require reselection.
   After an ambiguous create and full reload, inspect saved requests before
   creating again with a new key. Distinct command keys intentionally represent
   distinct creation attempts; semantic cross-key deduplication is not claimed.
7. Outbox events remain durable/pending only. M08 notification routing/delivery
   and M13 retry/reporting are not implemented. DB isolation uses backend policy,
   not RLS; privileged DB administrators remain trusted. Feature/launch decisions
   in OPEN_DECISIONS remain open; all production business gates remain disabled.

## M05/M06 prerequisites and stop boundary

M05 may proceed only after review: design brief/scope/proof/version lineage and
explicit design-to-print derivation need their own migrations/permissions; do
not repurpose mesh-upload permissions as arbitrary references or paid delivery.
M06 needs isolated task claiming/execution/retries, pinned profiles and validated
analysis provenance binding exact file SHA/request revision/spec hash. Current
pending tasks do not authorize analysis completion or quotation eligibility.

No Operator, slicer invocation, quotation, payment, stock reservation, printer
assignment/control or physical operation is introduced. Stop after M04 for
Owner review; no merge/publish/deploy or live enablement is authorized.

## Changed files

66 files, including this report. Generated contracts are included.

### Backend and migrations

- `backend/Dockerfile`
- `backend/alembic/env.py`
- `backend/alembic/versions/0003_printing_intake.py`
- `backend/app/api/business.py`
- `backend/app/api/business_schemas.py`
- `backend/app/api/intake.py`
- `backend/app/api/intake_schemas.py`
- `backend/app/core/config.py`
- `backend/app/database/business_models.py`
- `backend/app/database/intake_models.py`
- `backend/app/domain/types.py`
- `backend/app/intake/__init__.py`
- `backend/app/intake/catalog.py`
- `backend/app/intake/rate_limits.py`
- `backend/app/intake/storage.py`
- `backend/app/intake/validation.py`
- `backend/app/main.py`
- `backend/app/services/intake.py`
- `backend/app/services/requests.py`
- `backend/app/services/specifications.py`
- `backend/app/services/transactions.py`
- `backend/app/services/uploads.py`
- `backend/openapi.json`
- `backend/scripts/cleanup_uploads.py`
- `backend/tests/conftest.py`
- `backend/tests/model_fixtures.py`
- `backend/tests/test_migrations.py`
- `backend/tests/test_model_validation.py`
- `backend/tests/test_printing_intake.py`

### Frontend and browser tests

- `miniapp/e2e/foundation.spec.ts`
- `miniapp/scripts/test-auth-integration.mjs`
- `miniapp/src/app/App.test.tsx`
- `miniapp/src/app/App.tsx`
- `miniapp/src/components/layout/AppShell.tsx`
- `miniapp/src/features/printing/NewPrintRequest.tsx`
- `miniapp/src/features/printing/OwnerPrintingQueue.tsx`
- `miniapp/src/features/printing/PrintForms.tsx`
- `miniapp/src/features/printing/PrintRequestPage.test.tsx`
- `miniapp/src/features/printing/PrintRequestPage.tsx`
- `miniapp/src/features/printing/test-fixtures.ts`
- `miniapp/src/features/printing/types.ts`
- `miniapp/src/features/printing/usePrintIntake.ts`
- `miniapp/src/features/requests/RequestWorkspace.test.tsx`
- `miniapp/src/features/requests/RequestWorkspace.tsx`
- `miniapp/src/lib/api/client.ts`
- `miniapp/src/lib/api/schema.d.ts`
- `miniapp/src/lib/api/upload.test.ts`
- `miniapp/src/pages/CustomerDashboard.tsx`
- `miniapp/src/pages/OwnerDashboard.tsx`
- `miniapp/src/styles.css`

### Configuration, CI and documentation

- `.dockerignore`
- `.env.example`
- `.github/workflows/authentication.yml`
- `README.md`
- `compose.yaml`
- `docs/API_CONTRACTS.md`
- `docs/ARCHITECTURE.md`
- `docs/BUSINESS_FOUNDATION.md`
- `docs/DATA_MODEL.md`
- `docs/DEVOPS.md`
- `docs/FRONTEND_SPEC.md`
- `docs/M04_IMPLEMENTATION_REPORT.md`
- `docs/OPEN_DECISIONS.md`
- `docs/PRINTING_INTAKE.md`
- `docs/SECURITY.md`
- `docs/adr/0004-private-printing-intake.md`
