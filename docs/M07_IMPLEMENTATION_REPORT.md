# M07 implementation report

Date: 2026-11-12. Branch: `codex/m07-pricing-eligibility`.
Starting history: accepted M06 `e83a8ed49d0e1d00e9c1ca63bd9606e5cc4bfed2`.
Scope: M07 simulation pricing and Level 2 candidate eligibility only. No commit,
push, merge, environment publication or production deployment performed.

## Implemented

- Pure Decimal print and scoped design costing with gross margin, explicit unknown
  inputs, waste/support assumptions, labor/machine/power/overhead, shipping/tax,
  minimum and currency rounding. Persisted cost lines balance exactly to the total.
  Printing uses MMK; design simulation uses integral XTR. No cross-currency sums.
- Owner-published immutable policy versions and expiring simulation availability
  fixtures. No seeded commercial prices, real stock, capacity holds or reservations.
- Fail-closed Level 2 candidate rules for printing-only service, approved material,
  quality/profile, current native metrics, model/quantity/time/cost limits, geometry,
  size, lead time, confirmed requirements, stock and capacity. Design always needs
  Owner review. M06 unchecked self-intersections remain a review condition.
- Immutable `test_estimate` records with simulation mode and false acceptance/live
  authority. Exact request/revision/spec/file/native-result/profile/policy/scope
  provenance; current GET revalidates source, expiry, policy and availability.
- Server-side Customer/Owner authorization, CSRF/Origin, rate limits, version checks,
  idempotency and atomic audit/outbox writes. Customer DTOs exclude internal costs,
  rates and margins. Cached mutation responses contain only authorized pointers.
- Customer printing/design estimate panels; Owner scope/effort basis, breakdown,
  reasons/provenance and explicit simulation policy/fixture workspace. Draft item
  deadline, critical-use/tolerance and requirements confirmations use existing autosave.
  React displays server amounts and rechecks freshness without browser-side pricing
  or sensitive localStorage. Ambiguous retries preserve body and key.
- Reproducible environment install script, start instructions and updated CI harness.

Details: [pricing policy/runbook](PRICING_POLICIES.md),
[ADR 0007](adr/0007-simulation-pricing-and-eligibility.md),
[Cloud setup](CODEX_CLOUD_M07.md).

## Database and migration

New revision `0006_pricing_eligibility` follows `0005_isolated_slicing`; 0001–0005
are unchanged. New tables: pricing_policies, pricing_availability_fixtures,
pricing_estimates and pricing_estimate_lines. Computed amounts use NUMERIC(28,8).
Necessary additions extend item requirement confirmations and checked audit targets.
Existing request/system actor and ownership rules remain intact.

SQL guards enforce simulation/kind/currency, stage/customer/item relationships,
current analysis or design scope, immutable snapshots, no later cost-line appends,
and deferred cost balance. Empty downgrade is supported for disposable recovery;
nonempty M07 state blocks destructive downgrade. Preserve history and use a reviewed
forward migration/backup plan for real deployments.

Test target: task-owned PostgreSQL 16 container `3dps-m07-test`, loopback port 55437,
`3dps_test_m07`; browser tests use separate `3dps_test_browser_m07` and
`3dps_test_browser_m07container` databases. Synthetic credentials/data only.
No production database was accessed.

## Verification evidence

The current collection contains **425 backend cases**, all covered by successful
runs. The initial full run collected 412 cases and finished with 410 passed and
2 native-probe cold-start timeouts. After correcting the bounded test startup
allowance and adding 13 pricing negative cases, final verification was partitioned:
387 current core/pricing cases passed, all 19 sandbox cases passed, and the 19
analysis cases had passed in the full run. No case was skipped. This is not a claim
that a single final `pytest -q` command reported 425 passes.

| Check | Actual command / outcome |
| --- | --- |
| Environment | `bash scripts/codex-cloud-install.sh`: frozen uv/npm installs, Python import and TS smoke checks passed; Git status preserved. Node 24.22.1/npm 11.9.0, Python 3.12.14/uv 0.13.5; system Chromium used. |
| Full backend run | `TEST_DATABASE_URL=... M06_TEST_WORKER_IMAGE=sha256:... backend/.venv/bin/python -m pytest -q backend/tests`: 410 passed, 2 cold-start probe failures in 961.45s; corrected as described above. All 19 analysis cases passed. |
| Final core/pricing | Same command with `--ignore=backend/tests/test_analysis.py --ignore=backend/tests/test_worker_sandbox.py`, fresh `3dps_test_m07_final` DB: **387 passed in 201.29s**, including 15 pricing API and 7 migration tests. |
| Final sandbox | `... python -m pytest -q backend/tests/test_worker_sandbox.py`: **19 passed in 116.50s**, including actual CPU kill, credential stripping, network/filesystem, memory/disk/PID probes. |
| Pricing units | `PYTHONPATH=backend backend/.venv/bin/python -m pytest -q backend/tests/test_pricing_engine.py`: 84 passed. |
| Python lint | From backend: `.venv/bin/ruff check app alembic tests scripts ../telegram_bot ../worker`: passed. |
| Python typing | From backend: `.venv/bin/mypy app scripts ../telegram_bot ../worker`: passed, 67 source files. |
| Schema | `alembic upgrade head` on isolated databases, `alembic heads/history/check`: one 0001–0006 chain and no schema drift. Seven migration tests pass, including M07 seeded auth/project/request/hash/audit/outbox/idempotency preservation, empty downgrade/re-upgrade and refusal of nonempty downgrade. |
| Contracts | `PYTHONPATH=backend backend/.venv/bin/python backend/scripts/export_openapi.py`; `npm --prefix tools/api-types run generate`, repeated and SHA-256 compared: reproducible. |
| Frontend | `npm --prefix miniapp run check`: strict TS, ESLint, 108 Vitest tests, production build and mock-isolation artifact check passed. |
| Playwright | `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm --prefix miniapp run test:e2e`: 10 passed. |
| Host real stack | `npm --prefix miniapp run test:auth-integration` with disposable browser DSN, immutable M06 worker image and Chromium: 17 flows passed. Actual TLS gateway, production React, FastAPI, PostgreSQL and native slicer; no API mocks. |
| API container | `docker --host=unix:///var/run/docker.sock build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -f backend/Dockerfile -t 3dps-api:m07 .`: passed; production-mode startup and packaged Alembic head passed. |
| Container real stack | `TEST_CONTAINER_API=true node miniapp/scripts/test-auth-integration.mjs` with separate disposable browser DSN and Chromium: 16 flows passed. Packaged API used; host-native worker flow intentionally separate. |
| Upload recovery | `docker ... exec 3dps-m07-api-test python scripts/cleanup_uploads.py`: passed, 0 stale reservations; ready model data preserved. |
| Diff | `git diff --check`: passed; earlier migrations unchanged. |

Native worker image: `sha256:1d89db118c9bbe57bc375a5357e17929b6ee356494673164002b5e7205a0fd0c`.
PrusaSlicer reports `2.5.0+UNKNOWN` from pinned Debian 2.5.0+dfsg-4;
executable SHA-256 `a771b89fa0b45f4283cd8767db39b07d3800dc8bd4dedb3a1f1c9f544530c533`.

Corrections found during work: decimal upper-bound parsing, rounded-total overflow,
invalid quantity/geometry checks, validation of malformed configuration text,
post-commit cost-line append protection and bounded policy history per stage.
Restored Docker vfs layers intermittently exceeded 20 seconds during stopped
container creation; the creation/probe budget is now 60 seconds. Model execution
wall, process budgets, secret isolation, UID/capability/network restrictions and
fenced result publication remain unchanged. The full-run startup failures are explicitly retained above; the corrected sandbox
rerun is green. No production execution budget was relaxed.

## Remaining limitations and decisions

- All costs/capabilities are hypothetical and uncalibrated. No business rates,
  tax/shipping policy or live payment classification was approved. Combined design
  and printing remain independent stages and currencies.
- Real M06 manufacturing uncertainty requires review; a synthetic pure evaluator
  pass cannot authorize a quotation or live production.
- Simulation stock/capacity is expiring evidence without reservations. M10/M11
  real ledgers, holds, scheduling and assignment are still prerequisites for live work.
- The worker's aggregate cgroup CPU/RAM/PID enforcement remains unverified in Cloud.
  Process budgets, bounded tmpfs and other sandbox probes are tested; production
  hostile-workload isolation requires target-host verification and stronger isolation
  review as documented in M06.
- Telegram phone/device UI and the intended VPS/Caddy configuration remain external
  checks. Local HTTPS gateway tests are not a claim of real-device or VPS testing.
  Externally verify iOS/Android/Desktop launch, reload/expiry recovery, safe areas,
  authorized downloads, separate stage totals and CSRF/Origin through approved staging
  HTTPS, using a test bot/database. No staging deployment is authorized by this report.
- GitHub Actions is updated to run pricing with existing regression/real-stack
  checks. No M07 push or hosted CI execution was triggered or verified in this task.
- Owner policy configuration currently uses a labeled technical JSON editor.
  Backend validation is authoritative; a richer guided editor can be reviewed later.

## Milestone boundary

M08 may introduce reviewed versioned simulation offers/acceptance and notifications
only after M07 review. This implementation adds no offer acceptance, payable orders,
obligations, money collection, digital release, real design work, printer control or
new slicer operation. Test estimates cannot be promoted by toggling flags.
All production gates remain disabled. Temporary API container/private volume and
synthetic container env file were removed after testing; the task-owned loopback
PostgreSQL test service remains available for review. Stop for M07 review.

## Changed files

- `.github/workflows/authentication.yml`
- `README.md`
- `backend/alembic/env.py`
- `backend/alembic/versions/0006_pricing_eligibility.py`
- `backend/app/analysis/sandbox.py`
- `backend/app/api/business.py`
- `backend/app/api/intake_schemas.py`
- `backend/app/api/pricing.py`
- `backend/app/api/pricing_schemas.py`
- `backend/app/database/business_models.py`
- `backend/app/database/intake_models.py`
- `backend/app/database/pricing_models.py`
- `backend/app/main.py`
- `backend/app/pricing/__init__.py`
- `backend/app/pricing/configuration.py`
- `backend/app/pricing/eligibility.py`
- `backend/app/pricing/engine.py`
- `backend/app/pricing/policies.py`
- `backend/app/pricing/sources.py`
- `backend/app/services/pricing.py`
- `backend/app/services/specifications.py`
- `backend/openapi.json`
- `backend/tests/test_analysis.py`
- `backend/tests/test_migrations.py`
- `backend/tests/test_pricing_api.py`
- `backend/tests/test_pricing_engine.py`
- `backend/tests/test_worker_sandbox.py`
- `docs/API_CONTRACTS.md`
- `docs/ARCHITECTURE.md`
- `docs/CODEX_CLOUD_M07.md`
- `docs/DATA_MODEL.md`
- `docs/DEPENDENCY_MATRIX.md`
- `docs/FRONTEND_SPEC.md`
- `docs/M07_IMPLEMENTATION_REPORT.md`
- `docs/OPEN_DECISIONS.md`
- `docs/PRICING_POLICIES.md`
- `docs/SECURITY.md`
- `docs/adr/0007-simulation-pricing-and-eligibility.md`
- `miniapp/scripts/pricing-integration.mjs`
- `miniapp/scripts/test-auth-integration.mjs`
- `miniapp/src/features/design/DesignPage.tsx`
- `miniapp/src/features/pricing/OwnerPricingWorkspace.tsx`
- `miniapp/src/features/pricing/PricingPanel.test.tsx`
- `miniapp/src/features/pricing/PricingPanel.tsx`
- `miniapp/src/features/printing/PrintForms.tsx`
- `miniapp/src/features/printing/PrintRequestPage.tsx`
- `miniapp/src/features/printing/test-fixtures.ts`
- `miniapp/src/lib/api/schema.d.ts`
- `miniapp/src/pages/OwnerDashboard.tsx`
- `miniapp/src/styles.css`
- `scripts/codex-cloud-install.sh`
