# M06 implementation report

Date: 2026-11-12 (Asia/Rangoon). Branch: `codex/m06-isolated-slicing`.
Starting point: accepted M05 `0edbdedd1d875105636f866cb3af86c039f35932`;
the working tree was clean. The subsequent Owner instruction authorizes committing
and pushing this M06 branch to GitHub. Merge, deployment, environment publication,
live feature enablement and M07 remain unauthorized. The approved M02–M05
migrations/history are preserved.

## Delivered behavior

A separately operated trusted controller consumes the durable M04 task queue.
It stages only verified private model bytes and unit/dimension/profile settings,
then runs real pinned PrusaSlicer in a fresh restricted container. STL, Core 3MF
and OBJ receive deterministic geometry analysis; structurally accepted uploads
are not assumed printable. Results retain exact request revision, frozen spec
hash, item/file/checksum, task attempt, analyzer, virtual printer/profile/settings,
engine/executable/image identity, warnings, review reasons and artifact checksums.

Customers see waiting, processing, completed, clarification, review or failure
through authenticated APIs and the existing printing details page. Successful
results show dimensions, topology/volume, per-model estimated grams/duration,
quantity separately and the exact label **Simulation estimate — not a final
quotation.** Supports, batch production time and measured performance are not
fabricated. Owners inspect a paginated task queue, compatibility/specification
results and special-requirement flags, and may reason about bounded, idempotent
simulation retries with compatible approved profiles.

Submitted requests remain frozen. Pending/claimed work does not imply execution;
only verified container startup can enter `analyzing`. Terminal simulation work
stops at printing-stage `manual_review`, even when an estimate exists. Design
state, source-design lineage, file delivery rights and stage payment guarantees
are unchanged. No quotation, payment, physical printer record/control, G-code
release, calibration claim or production design delivery is added.

## Schema and transaction behavior

The single chain is:

```text
0001_auth_foundation -> 0002_business_foundation -> 0003_printing_intake
 -> 0004_design_intake -> 0005_isolated_slicing (head)
```

0005 adds exactly four domain tables: `virtual_printer_models`, `slicer_profiles`,
`model_analyses`, `slicing_runs`. Tasks gain fenced expiring leases, startup/error/
completion fields, attempt budgets, retry availability, profile selection and a
current result pointer. Optional dimension triples/tolerance extend items;
canonicalization omits these fields when no targets exist, preserving old hashes
and snapshots. Existing user audit actors remain unchanged; checked system actors
allow genuine background audit attribution without impersonating a customer.

A short PostgreSQL advisory lock plus request/task locks and `SKIP LOCKED` claims
at most two unexpired deliveries per database. UUID tokens, expiry checks and SQL
triggers fence stale result insertion and completion. Three automatic attempts
use bounded exponential backoff; deterministic failures do not automatically retry.
Reasoned Owner reschedules can extend the budget only to six total attempts.
Immutable historical analyses/runs remain after reruns; only a current succeeded
pointer with matching spec/revision/file can be authoritative.

Result publication, exact profile/result audit references, task/request state, audit and notification outbox commit in
one transaction. Publication failure rolls back all of them. Expiry recovery is
repeatable. Normal errors/timeouts remove only the task's container/staged copy;
restart cleanup removes matching old task-owned resources after five minutes.
No ready model files or retained history are pruned. Outbox delivery remains deferred.

## Worker isolation and reproducibility

The worker has no PostgreSQL client/application configuration, Telegram token,
session secret, Docker socket, printer credentials or network interface beyond
loopback. Nonroot UID/GID 10001, read-only image/input, dropped capabilities,
no-new-privileges and default seccomp are required. Scratch is noexec/nosuid/nodev
128 MiB `/work` plus 32 MiB `/tmp`. Hard POSIX limits enforce per-process 768 MiB
address space/60 CPU seconds, 32 processes per UID, 64 descriptors and 64 MiB files;
worker alarm is 85 seconds and the trusted execution timeout is 90 seconds.
JSON/log/output sizes are bounded; no writable host output mount exists.

**Cloud limitation:** requested aggregate Docker cgroup memory/CPU/PID limits were
not reflected inside this rootless environment. Its parent limits were visible
instead. Actual POSIX memory/CPU/process attacks and tmpfs exhaustion are tested;
these do **not** prove an aggregate container resource ceiling. Target-host cgroup
verification and VM/microVM isolation review remain prerequisites for exposure to
hostile public uploads. No production isolation/deployment claim is made.

Pinned native package: Debian `prusa-slicer=2.5.0+dfsg-4`; actual CLI version
`2.5.0+UNKNOWN`. Actual native executable SHA-256:
`a771b89fa0b45f4283cd8767db39b07d3800dc8bd4dedb3a1f1c9f544530c533`.
The CLI was inspected and exercised rather than assuming unsupported flags.
The approved immutable worker image tested for final verification is:
`sha256:1d89db118c9bbe57bc375a5357e17929b6ee356494673164002b5e7205a0fd0c`.
The image records its Debian package inventory. Transitive apt packages are not
snapshot-pinned, so rebuilds are not claimed byte-identical; a changed build needs
a new profile revision/image approval. Four conservative PLA/PETG standard/fine
profiles are uncalibrated by SQL constraint and simulation-only.

Raw 3MF settings never reach native slicing. Bounded geometry normalization applies
only explicit units and translation; no fit scaling or reorientation. An explicit
repair/export check rejects topology/geometry-changing native repairs. Signed
volume is evaluated near the mesh origin for numerical stability. Uncertain volume
is null. Real slicing output must include valid positive grams/time and complete
G-code; its raw hash and a hash excluding only the generated timestamp header are
recorded, and the artifact is discarded. Repeated fixture tests compare metrics
and canonical checksums; fine profiles have separate provenance and duration.
See [profile details](SLICER_PROFILES.md) and [operations/recovery](WORKER_OPERATIONS.md).

## Actual verification

| Check | Actual result |
|---|---|
| Full backend pytest with real immutable worker image and PostgreSQL | **324 passed in 401.80 seconds**, no skips |
| Added public-profile numeric serialization/checksum regression | **1 passed in 1.47 seconds**; 325 distinct passing backend cases across these runs |
| Final audit profile/result provenance checks | **3 passed in 34.13 seconds**, including actual isolated STL publication, lease recovery and no profile fallback |
| Ruff, including worker, migrations, tests, scripts and bot | Passed |
| Strict Mypy | Passed, **57 source files** |
| Alembic upgrades, seeded preservation, guarded downgrade/re-upgrade | Passed against disposable PostgreSQL; revisions 0001–0005 form one head |
| Alembic schema check | **No new upgrade operations detected** |
| OpenAPI / TypeScript regeneration twice and content-hash comparison | **No drift** |
| Frontend strict TypeScript, ESLint, production build | Passed (`npm run check`) |
| Vitest / React Testing Library | **98 passed**, 9 files |
| Playwright | **10 passed in 11.3 seconds** |
| Real-stack production React + HTTPS + FastAPI + PostgreSQL + real worker | **15 flows passed** |
| Real-stack production application-container API + HTTPS + PostgreSQL | **14 flows passed** |
| Worker/application image build and application startup | Passed; API UID 10001, storage 0700, no Docker socket or worker package |
| Production artifact with development mock flag deliberately forced true | Passed: mock module excluded |
| Hosted GitHub Actions / real Telegram devices | **Not observed / external verification pending** |

No skipped real-sandbox test is counted as a pass. The profile checksum regression
was added after the full run and specifically verifies preservation of integer and
boolean configuration values through public serialization. Final audit metadata
retains exact immutable profile/result IDs so reruns cannot erase failed-attempt
provenance; its targeted tests are in addition to the full-suite evidence.

The disposable PostgreSQL container uses loopback port 55436, synthetic test
credentials and database names beginning `3dps_test`; no production data is used.
Docker commands clear endpoint/context/TLS selectors and use the managed local
Unix socket. Build proxy and CA trust remain enabled; the CA is a build secret.

```sh
# From backend, with the explicit disposable TEST_DATABASE_URL and immutable image:
M06_TEST_WORKER_IMAGE=sha256:1d89db118c9bbe57bc375a5357e17929b6ee356494673164002b5e7205a0fd0c \
  TEST_DATABASE_URL=<disposable-loopback-3dps_test_m06_reviewed> .venv/bin/pytest -q
.venv/bin/ruff check app alembic tests scripts ../worker ../telegram_bot
.venv/bin/mypy app scripts ../worker ../telegram_bot
DATABASE_URL=<disposable-test-url> .venv/bin/alembic upgrade head
DATABASE_URL=<disposable-test-url> .venv/bin/alembic check
DATABASE_URL=<disposable-test-url> .venv/bin/alembic heads
DATABASE_URL=<disposable-test-url> .venv/bin/alembic history
PYTHONPATH=. .venv/bin/python scripts/export_openapi.py
npm --prefix ../tools/api-types run generate

# From miniapp:
npm run check
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e
M06_TEST_WORKER_IMAGE=<immutable-worker-image> \
  PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium \
  TEST_BROWSER_DATABASE_URL=<disposable-3dps_test_browser_m06reviewed> npm run test:auth-integration
TEST_CONTAINER_API=true PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium \
  TEST_BROWSER_DATABASE_URL=<disposable-container-browser-db> node scripts/test-auth-integration.mjs

# From repository root, with the inherited proxy and CA build secret in Cloud:
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -f worker/Dockerfile -t 3dps-slicer:m06 .
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -f backend/Dockerfile -t 3dps-api:m06 .
```

These are the executed command forms with disposable DSNs abbreviated; placeholders avoid
turning disposable credentials into setup recommendations. Host browser tests use
the real worker CLI, PostgreSQL and production React over a temporary HTTPS proxy.
Container browser tests separately verify the packaged API/private volume with
pending M04 tasks; that mode does not claim a second native-worker browser run.
The production API container runs UID 10001, private storage mode 0700, and has
no Docker socket or worker package. Final packaged API image SHA-256:
`1fb6d5210462e2fb34c15989f2c0b85b635e3dc350451bd372115693ac29e6fb`.
Its FastAPI lifespan startup connected to PostgreSQL and prepared private storage successfully. Private upload cleanup completed with zero expired reservations. Task-owned API/PostgreSQL
containers, private test volume/network and the synthetic env file were removed
after verification; built images and ignored test evidence remain for local review.

Tests cover real format processing, profile repeatability, dimensions/units,
embedded 3MF settings/external resources/traversal, malformed/open geometry,
credential/network/filesystem/resource denial, real worker timeout/cleanup,
concurrent claims, lease expiry/recovery/stale fences, duplicate delivery,
publication rollback, immutable history, Owner/customer/isolation/CSRF/Origin,
retry budget/idempotency/replay authorization, orphan staging cleanup and all
existing M02–M05 regression suites. Empty physical-printer inventory is tested.
Frontend checks include all status views, provenance/uncertainty, Owner controls,
original retry-body/key reuse, autosave/reload regressions and mock isolation.

Corrections during verification: container source permissions initially blocked
UID 10001; image files now have readable/traversable immutable permissions. An
M04 regression exposed missing task-success/result coupling; SQL now requires a
real result/start/completion and fences successful completion. Shared profile
configuration was moved into the backend and copied into the worker at build
time so ordinary API startup needs no worker package/Python-path workaround.
Public profile serialization now preserves numeric types so its configuration checksum can be verified. Background audit events retain immutable profile/result references across reruns. Customer target dimensions do not alter legacy canonical hashes. Owner ambiguous
retry preserves the original body/key. A test-port collision was resolved by
removing the task-owned prior API container before the final host run.

## CI and external limits

GitHub CI now builds the pinned slicer image and runs actual sandbox/security
checks with PostgreSQL, lint/types, migration/schema/contract checks, frontend and
real-stack host/container tests. **Hosted GitHub Actions execution was not observed
or claimed.** The subsequent Owner-authorized branch push may trigger the configured
workflows; a successful push does not establish a successful hosted CI run.

Real Telegram Android/iOS/Desktop must still verify launch/session cookies,
expiry/relaunch during polling, theme/safe areas/keyboard, uploaded-model privacy,
long analysis/review messages and mobile Owner retry controls through the intended
Caddy HTTPS gateway and a test bot/database. Chromium's synthetic signed launches
are integration evidence, not real-device or BotFather verification.

Self-intersections, structural strength, support/overhang feasibility, material
stock, batch packing and measured hardware performance are not certified. Existing
M04/M05 structural upload subprocesses retain their earlier bounded host-namespace
limitations; M06 fully separates native slicing/geometry execution but does not
claim a wholesale public-intake parser hardening release. Storage encryption,
retention, backup/restore and deployment supervision remain operational gates.

M07 prerequisites: consume only current authoritative analysis/spec/profile
provenance; independently evaluate eligibility, special requirements, uncertainty,
manual design-pricing basis and simulation cost policies. Real costing requires
actual calibrated hardware/material data and the later live release gates.
No quotation/payment authorization may be inferred from these estimates.
**Stop after M06 for review.**

## Changed files

60 files (generated contracts included):

```text
.github/workflows/authentication.yml
README.md
backend/README.md
backend/alembic/env.py
backend/alembic/versions/0005_isolated_slicing.py
backend/app/analysis/__init__.py
backend/app/analysis/orchestrator.py
backend/app/analysis/profile_config.py
backend/app/analysis/registry.py
backend/app/analysis/sandbox.py
backend/app/analysis/tasks.py
backend/app/api/analysis.py
backend/app/api/analysis_schemas.py
backend/app/api/business.py
backend/app/api/intake.py
backend/app/api/intake_schemas.py
backend/app/database/analysis_models.py
backend/app/database/business_models.py
backend/app/database/intake_models.py
backend/app/domain/types.py
backend/app/main.py
backend/app/services/analysis.py
backend/app/services/specifications.py
backend/openapi.json
backend/scripts/process_tasks.py
backend/tests/analysis_fixtures.py
backend/tests/test_analysis.py
backend/tests/test_migrations.py
backend/tests/test_worker_sandbox.py
docs/API_CONTRACTS.md
docs/ARCHITECTURE.md
docs/DATA_MODEL.md
docs/FRONTEND_SPEC.md
docs/M06_IMPLEMENTATION_REPORT.md
docs/OPEN_DECISIONS.md
docs/PRINTING_INTAKE.md
docs/SECURITY.md
docs/SLICER_PROFILES.md
docs/WORKER_OPERATIONS.md
docs/adr/0006-isolated-simulation-analysis.md
miniapp/scripts/analysis-integration.mjs
miniapp/scripts/test-auth-integration.mjs
miniapp/src/features/analysis/AnalysisPanel.test.tsx
miniapp/src/features/analysis/AnalysisPanel.tsx
miniapp/src/features/analysis/ProcessingQueue.tsx
miniapp/src/features/analysis/TaskRetry.tsx
miniapp/src/features/printing/OwnerPrintingQueue.tsx
miniapp/src/features/printing/PrintForms.tsx
miniapp/src/features/printing/PrintRequestPage.test.tsx
miniapp/src/features/printing/PrintRequestPage.tsx
miniapp/src/features/printing/test-fixtures.ts
miniapp/src/features/requests/RequestWorkspace.tsx
miniapp/src/lib/api/schema.d.ts
miniapp/src/pages/OwnerDashboard.tsx
miniapp/src/styles.css
worker/Dockerfile
worker/__init__.py
worker/geometry.py
worker/limits.py
worker/main.py
```
