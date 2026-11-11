# M05 implementation report

Date: 2026-11-11 (Asia/Rangoon). Status: **implemented; stopped for review**.
Branch: `codex/m05-design-intake`, created from accepted M04
`de9ad298806831289bf60f727bb4cc06bb432fe1`. The working tree was clean at start.
The subsequent Owner instruction authorizes committing and pushing this M05
branch. Merge, deployment, live feature enablement and M06 remain unauthorized.
M04 and approved M02/M03 history are preserved.

## Delivered functionality

Customers can create a persisted design-only or combined-service brief, autosave
and resume it, upload private references, remove draft references and submit
without any print item, STL, filament or printer. Fields cover description/use,
dimensions/units/tolerances, manufacturing preferences, desired date, special
requirements and requested digital/printing deliverables.

Owner workspace proposes versioned scope with deliverables, revision policy,
exclusions and digital rights. Customer agreement identifies the exact latest
proposal. Historical scope content and agreement evidence are retained. All are
explicitly simulation agreements with `binding=false`, not real contractual quotes.
Proof work is blocked until Owner explicitly activates a scope-bound simulation
quote-and-paid fixture. It creates no financial ledger, quote amount, paid order,
real work authorization or digital release.

Owner uploads private previews/manufacturing models and publishes immutable
numbered proofs. Customers view authorized images/plain text and approve or
request changes to the exact current version. New proofs clear older approval;
old reviews remain immutable. Manufacturing-only scopes grant no source download;
even scoped future digital rights do not bypass M12 delivery/payment gates.

For combined projects, Owner converts a currently approved manufacturing-ready
version once into a separate printing draft under the same service project.
`source_design_version_id` is immutable and lineage-checked. An explicit Owner
attachment action streams the approved mesh through M04 reservations/storage;
Customer then configures actual print specs and submits. Wrong model bytes,
incomplete specs and duplicate/stale commands fail. Both stages stay independent;
no design fixture/payment authorizes printing. Analysis tasks stay pending.

## Database, security and architecture

- Single Alembic chain: `0001_auth_foundation -> 0002_business_foundation ->
  0003_printing_intake -> 0004_design_intake (head)`. Original revisions remain
  byte-identical to M04. Four necessary tables only: design_projects,
  design_scopes, design_versions, design_reviews. No quotation/order/payment,
  digital-delivery, analysis-result or future milestone tables were created.
- Uploaded files reuse the existing private storage adapter, durable quota
  reservations, bounded streaming/checksums, quarantine, rate limits, lease
  fencing, compensation and cleanup. Purpose/uploader fields distinguish
  customer references, review previews, Owner-only manufacturing models and
  print models. Direct/composite FKs, checks and SQL guards enforce associations.
- Preview/reference types: PNG/JPEG or plain UTF-8 TXT. Pinned Pillow 13.0.0
  verifies/fully decodes bounded raster images in the existing subprocess;
  strict end markers, dimensions/pixels/frame limits and TXT byte/content bounds
  reject malformed/truncated/unsupported input. Model validation remains M04.
  No archive/document execution, public/static serving or source-key disclosure.
- All actions use current authenticated sessions and resource authorization;
  mutations enforce CSRF, Origin, expected version and idempotency. Roles remain
  Customer/Owner only. Core Telegram verification/auth service/routes and identity
  models are unchanged. No mock identity or production authentication bypass.
- Scope/proof/review/convert changes are in domain services. Request locks and
  DB uniqueness serialize races. State, audit, minimized outbox and successful
  command result commit atomically. Published versions/reviews/scope content and
  source lineage are immutable. Changed scopes invalidate fixture/current proof
  approval, without overwriting history or pretending future approvals exist.
- Brief schema v3 hashes exact inputs and active reference provenance. Original
  M04 printing hashes stay compatible; model upload fingerprints deliberately
  retain M04 encoding. A regression reconstructs an old cached response/key and
  confirms successful exact replay with safe new DTO defaults.
- React uses existing auth, shared relative client/components and generated
  contracts. Command retries preserve exact keys in memory, server drafts survive
  reload, private previews are images/escaped text, and no sensitive localStorage
  persistence is introduced. Unfinished files require reselection after reload.

See [ADR 0005](adr/0005-design-intake-and-lineage.md) and the
[design runbook](DESIGN_INTAKE.md) for exact scope, contracts and recovery policy.

## Actual commands and results

All PostgreSQL/data/blob tests used task-owned disposable loopback resources:
`3dps_test_m05`, fresh `3dps_test_m05_final`, host browser
`3dps_test_browser_m05`, container browser `3dps_test_browser_m05container`.
Only synthetic credentials/files were used. DSN/secret values are not reproduced.
Python 3.12.14, PostgreSQL 16.15, Node 24.22.1/npm 11.9.0 and system Chromium
were available. Package installs preserved managed proxy/CA trust. No production
data or external real business operation was accessed.

| Directory / actual command | Result |
|---|---|
| `backend`: `UV_CACHE_DIR=/tmp/3dps-m05-uv-cache uv add 'pillow==13.0.0'`; `uv export --frozen --no-dev --no-emit-project --output-file requirements.txt` | PASS; pinned lock + hash-exported runtime dependency; no other version upgrade |
| `backend`: `TEST_DATABASE_URL=<loopback test DSN> .venv/bin/pytest -q --tb=short` | **286 passed in 70.90s**, including all 260 M02–M04 regressions and 26 new cases |
| `backend`: `TEST_DATABASE_URL=<test DSN> .venv/bin/pytest tests/test_migrations.py -q --tb=short` | **5 passed in 10.39s**, also included in full suite |
| `backend`: `.venv/bin/ruff check app alembic tests scripts ../telegram_bot` | PASS |
| `backend`: `.venv/bin/mypy app scripts ../telegram_bot` | PASS, **42 source files** |
| `backend`: `DATABASE_URL=<disposable DSN> .venv/bin/alembic upgrade head`, `heads`, `history`, `check` | Fresh upgrade PASS; only **0004** head; **No new upgrade operations detected** |
| `backend`: `PYTHONPATH=. .venv/bin/python scripts/export_openapi.py`; `tools/api-types`: `npm run generate`; root: `sha256sum --check .local/m05-contract-before.sha256` | PASS; regenerated OpenAPI and TypeScript byte-identical on repetition |
| `miniapp`: `npm run check` | PASS: strict TS, zero-warning ESLint, **87 tests in 8 files**, Vite production build and forced-mock artifact exclusion |
| `miniapp`: `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e` | **10 passed in 9.6s**, responsive/theme/navigation and production permission/mock negatives |
| `miniapp`: `TEST_BROWSER_DATABASE_URL=<host browser DSN> PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium node scripts/test-auth-integration.mjs` | **14/14 real-stack flows PASS**, host FastAPI + production React + HTTPS + real PostgreSQL |
| Root: explicit local-socket `docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -f backend/Dockerfile -t 3dps-api:m05-review .` | PASS; final image `sha256:eea71ae820ac0087740df7c704d126162f64529b2da350c66698df616440bf47` |
| Root: `docker run --rm --network 3dps-m05-review --env-file .local/m05-container.env 3dps-api:m05-review alembic upgrade head` | PASS on fresh separate container-test DB |
| Root: `docker run --detach --name 3dps-m05-api-review --network 3dps-m05-review --publish 127.0.0.1:18002:8000 --mount type=volume,src=3dps-m05-private,dst=/srv/private_uploads --env-file .local/m05-container.env 3dps-api:m05-review` | PASS; API startup and migration checks work in production mode with safe flags |
| Root: `docker exec 3dps-m05-api-review alembic current` / `alembic check`; Settings/UID/Pillow probe | **0004** head, no metadata drift, UID **10001**, root **0700**, Pillow **13.0.0**, simulation true, unsafe flags false |
| `miniapp`: `TEST_CONTAINER_API=true TEST_BROWSER_DATABASE_URL=<container browser DSN> PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium node scripts/test-auth-integration.mjs` | **14/14 flows PASS** with the final production-mode API and React build |
| Root: remove/recreate task API with its named private volume; Python DB/storage checksum/mode probe and health request | PASS: **14 private blobs** and **1 immutable proof version** retained; all blobs checksum-verified, mode **0600**, UID10001; health OK |
| Root: `docker exec 3dps-m05-api-review python scripts/cleanup_uploads.py` | PASS: **0** expired/delete-pending rows removed; ready files preserved |
| Root: `git diff --exit-code de9ad29 -- <0001/0002/0003, Telegram verifier, auth routes/service, identity models>` | PASS; approved history/auth files preserved |
| Root: `node --check miniapp/scripts/design-integration.mjs`; `node --check miniapp/scripts/test-auth-integration.mjs`; `git diff --check` | PASS at contract verification |

Docker used the managed local Unix socket with endpoint/context/TLS selectors
cleared; proxy/CA policy stayed intact. The CA is a build secret, not an image
layer. Container networking/published ports were restricted to disposable local
integration resources; no application was deployed to a production service.
Temporary M05 API/PostgreSQL containers, private volume/network and synthetic
container env file were removed after verification.

Migration tests cover fresh installs, auth preservation, seeded M04 file/item/
request/session preservation, empty-M05 downgrade/re-upgrade retaining M04 data,
and intentional refusal of populated M05 downgrade. Recovery requires reviewed
forward migration or private-volume + database restore, not dropped history.

New domain/integration tests cover design-only zero items, reference privacy and
malformed content, replaced failed uploads, removal/cleanup, Owner/Customer and
cross-customer command isolation, current CSRF/Origin/version checks, simulation
fixture guards, retained scope agreements/immutable scope content, exact proof
review, newer-version approval invalidation, concurrent approval/revision races,
immutable reviews/proofs, idempotent/concurrent conversion, duplicate printing
prevention, source lineage immutability, wrong manufacturing-byte rejection,
independent print specifications/pending tasks, and atomic outbox rollback.
Frontend tests cover brief autosave/reload, model-free submit, exact scope/version
commands, explicit fixture confirmation, unchanged retry keys, queue links,
combined creation and escaping proof markup. Existing upload/auth/regression
negatives remain in the full suites.

## Corrections and review evidence

The first migration draft exposed asyncpg's single-statement restriction; SQL
functions/triggers are now applied as separate statements. New test assertions
needed nested transactions around intentional DB constraint failures. A malformed
TXT rejection uses the documented 415 status; the test expectation was corrected.
Image truncation/extra trailing data, stale proofs, wrong source bytes and failed
storage work remain fail-closed rather than being accepted to satisfy tests.

Compatibility review preserved M04's exact model-upload fingerprint encoding and
added a retained-key/old-cached-DTO replay regression. Reference submission ignores
fully cleaned rejected attempts while still requiring current references to be
cleared; valid replacements no longer poison a draft. Removed committed uploads
cannot mutate their historical provenance and require a new upload command.

The first production-container browser attempts selected the next file before
the previous upload's authenticated refresh completed. The backend rejected the
stale version; the harness now waits for the next input to be enabled. The final
14-flow container run passes without API mocks. Production artifacts were checked
with the development mock flag deliberately enabled and exclude its module.

Customer mobile and Owner desktop screenshots were generated and visually
inspected at `miniapp/test-results/m05-customer-mobile.png` and
`m05-owner-desktop.png` (ignored synthetic test artifacts). The public-facing
workflow distinguishes scope proposals, simulation agreement, proof approval,
source privacy and independent printing progress. No real device result is
inferred from these images.

## CI and external limitations

Backend CI now runs the expanded **14-flow** harness for host and production
container APIs, retaining real PostgreSQL suites, migration/schema/contract checks
and private-volume cleanup. The frontend workflow retains checks/Playwright.
**Hosted GitHub Actions execution was not observed during implementation
verification.** Local success is not a claim of green hosted CI. The subsequent
Owner-authorized branch push can trigger the configured workflows; no hosted
result is claimed here. No PR, merge or production deployment is authorized by
that handoff instruction.

- Real Telegram Android/iOS/Desktop, BotFather launch, intended Caddy HTTPS,
  WebView image/text upload/cancel/retry, cookies/session expiry, autosave/relaunch,
  proof rendering and safe-area/keyboard behavior remain external verification.
  The runbook supplies a test-bot procedure; Chromium is not G1 device evidence.
- Supported reference/document profile is intentionally conservative. PDF/SVG/
  Office files and extended model formats are rejected. Safe export guidance is
  explicit. No model geometry, slicing, manufacturability or calibrated price is
  claimed by structural validation or Owner manufacturing-ready marking.
- Validator subprocesses are bounded and clear credentials/descriptors but share
  the API UID/filesystem/network namespaces. Stronger OS isolation, parser corpus
  hardening and public-intake review remain prerequisites before M06/public use.
- Private storage needs one shared volume. Object storage, encryption, retention/
  deletion policies, ready-file pruning, cleanup scheduling and backup/restore
  remain operational decisions. Ready/cancelled/published files remain retained
  and quota-charged. No unsafe history or ready-blob garbage collection was added.
- Scope/proof replacement is blocked once a combined printing draft exists.
  Later corrections require a reviewed successor/replacement flow preserving
  approvals and independent paid obligations. M00-D07 remains open: manufacturing
  handoff is not fabricated as digital delivery or terminal paid completion.
- Scope digital rights are recorded for future policy, without any M05 release.
  M08/M09 must replace fixture authorization with real quote/payment checks; M12
  must implement paid, exact-version, rights-checked delivery. Fixture fields may
  never be treated as verified funds or live production authority.
- Idempotency keys/File objects remain in component memory. Reload restores
  committed server data; inspect existing projects after ambiguous creation before
  issuing a new create key. Outbox stays pending-only; delivery/routing/retries
  remain later milestones. Backend resource policy is not PostgreSQL RLS;
  privileged DB administrators and backup access remain trusted.

Stop after M05 for review. No M06, Operator, slicer, binding quotation, payment
collection, live design work, digital delivery or physical printer control.

## Changed files

60 files, including this report and generated contracts.

### Backend, dependency locks and migrations

- `backend/alembic/env.py`
- `backend/alembic/versions/0004_design_intake.py`
- `backend/app/api/business.py`
- `backend/app/api/business_schemas.py`
- `backend/app/api/design.py`
- `backend/app/api/design_schemas.py`
- `backend/app/api/intake.py`
- `backend/app/api/intake_schemas.py`
- `backend/app/database/business_models.py`
- `backend/app/database/design_models.py`
- `backend/app/database/intake_models.py`
- `backend/app/intake/validation.py`
- `backend/app/main.py`
- `backend/app/services/design.py`
- `backend/app/services/design_files.py`
- `backend/app/services/intake.py`
- `backend/app/services/requests.py`
- `backend/app/services/specifications.py`
- `backend/app/services/uploads.py`
- `backend/openapi.json`
- `backend/pyproject.toml`
- `backend/requirements.txt`
- `backend/tests/test_design_intake.py`
- `backend/tests/test_migrations.py`
- `backend/uv.lock`

### Frontend and real-stack browser tests

- `miniapp/scripts/design-integration.mjs`
- `miniapp/scripts/test-auth-integration.mjs`
- `miniapp/src/app/App.tsx`
- `miniapp/src/features/design/DesignForms.tsx`
- `miniapp/src/features/design/DesignPage.test.tsx`
- `miniapp/src/features/design/DesignPage.tsx`
- `miniapp/src/features/design/DesignQueue.tsx`
- `miniapp/src/features/design/NewDesignRequest.tsx`
- `miniapp/src/features/design/ProofViewer.tsx`
- `miniapp/src/features/design/test-fixtures.ts`
- `miniapp/src/features/design/types.ts`
- `miniapp/src/features/design/useDesign.ts`
- `miniapp/src/features/printing/NewPrintRequest.tsx`
- `miniapp/src/features/printing/PrintRequestPage.tsx`
- `miniapp/src/features/printing/test-fixtures.ts`
- `miniapp/src/features/requests/RequestWorkspace.tsx`
- `miniapp/src/lib/api/client.ts`
- `miniapp/src/lib/api/schema.d.ts`
- `miniapp/src/pages/CustomerDashboard.tsx`
- `miniapp/src/pages/OwnerDashboard.tsx`
- `miniapp/src/styles.css`

### Configuration and documentation

- `.github/workflows/authentication.yml`
- `README.md`
- `docs/API_CONTRACTS.md`
- `docs/ARCHITECTURE.md`
- `docs/DATA_MODEL.md`
- `docs/DESIGN_INTAKE.md`
- `docs/DEVOPS.md`
- `docs/FRONTEND_SPEC.md`
- `docs/M05_IMPLEMENTATION_REPORT.md`
- `docs/OPEN_DECISIONS.md`
- `docs/PRINTING_INTAKE.md`
- `docs/SECURITY.md`
- `docs/STATE_MACHINES.md`
- `docs/adr/0005-design-intake-and-lineage.md`
