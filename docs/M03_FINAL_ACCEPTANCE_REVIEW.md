# M03 final acceptance review

Date: 2026-11-11 UTC. Reviewed M03 against AGENTS, STATE_MACHINES,
INTEGRITY_RULES, DEPENDENCY_MATRIX, SECURITY and the actual milestone prompt
`prompts/M03_CORE_DATABASE_API_AND_TRANSACTION_FOUNDATION.md`.
`prompts/M03_BACKEND_FOUNDATION.md` does not exist; no replacement requirements
were invented. Approved M02 base: `08fb8e0353f0364b722aa3a3e07454124b2f1ebc`.

**Local M03 acceptance checks pass. Stop for Owner review. No M04, merge,
production deployment, live quotation/payment or printer operation is approved
or performed.** Repository handoff status is recorded below separately from
local test success; no hosted CI success is inferred.

## Requested confirmations

| Item | Result and evidence |
|---|---|
| 1. M02 authentication/permissions | PASS. Telegram verifier, auth service, configuration, identity/session models and migration 0001 are byte-identical to the approved base. Every original backend test function remains. Full suite retains signature/freshness/replay/session/CSRF/Origin/role negatives; business routes reuse verified Principal/CSRF dependencies. Owner assignment remains server-configured. |
| 2. One Alembic history | PASS. `base -> 0001_auth_foundation -> 0002_business_foundation (head)` is the only chain/head. Fresh install, seeded 0001 upgrade, preservation of users/session token hashes and disposable downgrade/re-upgrade pass. `alembic check` reports no new upgrade operations. No existing revision is rewritten. |
| 3. Ownership/project/stage integrity | PASS. Composite parent/customer/service/mode FK, user FKs, mode/stage/status checks and unique project/stage are enforced by PostgreSQL. Server derives ownership/stage and rejects client trusted fields. Reads and commands check own resource or current Owner. Customer-scoped lists and guessed-ID denials pass. Database integrity is not PostgreSQL row-level security: authenticated resource isolation is enforced by backend policy; administrators/runtime DB access remain trusted. |
| 4. Concurrent commands | PASS for this slice. Actor/action/key transaction advisory locks and a composite idempotency primary key collapse same-command retries across two app instances/DB pools to one project/request/audit/outbox/result. Request row locks and expected versions produce one winner and one 409 for competing commands, including Owner-vs-Customer edit/cancel. Session rotation and revocation races are covered. Different creation keys intentionally represent separate drafts; no semantic deduplication across independently issued keys is claimed. |
| 5. Transaction consistency | PASS. Project/request mutation, audit, outbox and successful idempotency response share one unit of work. Injected audit, outbox and idempotency insertion failures roll back all records. Existing draft outbox failure preserves original notes/version/hash. Failed transitions leave business records unchanged. Audit UPDATE/DELETE fails at DB boundary; no delivery worker is added. |
| 6. Cached response authorization | PASS. Access is rechecked before cached request edit/transition responses, including demoted Owner access (404). Creation responses are actor-scoped; session/account validation precedes every cache lookup. Three new acceptance cases explicitly replay a cached creation with a stale resolved Principal after revocation, expiry or account disablement: all 401, no duplicate/write. |
| 7. API contract drift | PASS. Export actual FastAPI OpenAPI, regenerate TypeScript with the pinned isolated tool, compare both files' SHA-256 before/after: byte-identical. Strict TS and integration requests agree with the API. |
| 8. Automated suites | PASS: backend 180; frontend 58; UI browser 10; real-stack 7 flows with host Uvicorn and the same 7 with the production-mode application image. No API mocks or SQLite fallback. Counts describe distinct suites/runs, not 14 different browser scenarios. |
| 9. Feature isolation | PASS. All binding/auto-quote, policy-approval, payment, physical-printing and development-auth flags are false. Simulation is deliberately true. Packaged Settings reject seven unsafe overrides in each of development/production: 14/14 refusals. Production frontend excludes the mock module even when its build flag is forced true. An explicitly enabled development-only UI preview remains permitted and disconnected. |
| 10. Container build/startup | PASS. Existing pinned Python image and hash-locked requirements build as `3dps-api:m03-acceptance`. Dependency layers were cached; updated application and migration layers were copied. Image `sha256:85a23b14d416030735af4921c60b510a34b68ec098cbe4a2fd7f807f3e8d323b` runs as UID 10001 with `APP_ENV=production`, only synthetic credentials and disposable PostgreSQL. Packaged Alembic upgrade/current reach 0002. Liveness, Owner DB/schema readiness, auth/business browser flows and private `/docs` 404 pass. This is an isolated local test, not a production deployment or Caddy/Telegram-device test. |

## Actual commands and final results

Commands are relative to repository root unless a directory is indicated.
Test DSNs below use only task-owned loopback PostgreSQL on port 55433,
`3dps_test_m03_acceptance`, `3dps_test_browser_m03acceptance`, and
`3dps_test_browser_container`. No production data or credentials were used.
Docker commands selected the local Unix socket after clearing inherited
endpoint/context/TLS selectors; they kept managed proxy/CA trust intact.

| Command | Final result |
|---|---|
| `backend`: `TEST_DATABASE_URL=<test DSN> .venv/bin/pytest -q --tb=short` | **180 passed in 20.40s**, including all three migration tests |
| `backend`: `.venv/bin/ruff check app alembic tests scripts ../telegram_bot` | PASS |
| `backend`: `.venv/bin/mypy app scripts ../telegram_bot` | PASS, 25 source files |
| `backend`: `.venv/bin/alembic heads` / `history` | One head 0002, down-revision 0001 |
| `backend`: `DATABASE_URL=<test DSN> .venv/bin/alembic upgrade head` / `check` | Fresh upgrade PASS; no metadata drift |
| `backend`: `PYTHONPATH=. .venv/bin/python scripts/export_openapi.py`; `tools/api-types`: `npm run generate` | PASS; SHA-256 comparison confirms byte-identical generated artifacts |
| `miniapp`: `npm run check` | PASS: strict TS, ESLint, **58 tests**, production build and forced-mock production exclusion |
| `miniapp`: `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e` | **10 passed in 9.7s** |
| `miniapp`: `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium TEST_BROWSER_DATABASE_URL=<host browser test DSN> node scripts/test-auth-integration.mjs` | **7/7 flows PASS**, host Uvicorn |
| `docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -f backend/Dockerfile -t 3dps-api:m03-acceptance .` | PASS; CA build secret is not an image layer |
| `docker run --rm --network 3dps-m03-acceptance --env-file .local/m03-container-acceptance.env 3dps-api:m03-acceptance alembic upgrade head` | PASS; only disposable container-test DB |
| `docker run --detach --name 3dps-m03-acceptance-api --network 3dps-m03-acceptance --publish 127.0.0.1:18002:8000 --env-file .local/m03-container-acceptance.env 3dps-api:m03-acceptance` | PASS after attaching the bridge for host-only test access; API stays bound to loopback |
| `docker exec 3dps-m03-acceptance-api alembic current` | `0002_business_foundation (head)` |
| `miniapp`: `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium TEST_CONTAINER_API=true TEST_BROWSER_DATABASE_URL=<container browser test DSN> node scripts/test-auth-integration.mjs` | **7/7 flows PASS**, packaged API in production mode |
| `docker exec ... python -c <safe Settings/UID and flag-rejection probes>` | UID 10001; simulation true; seven safe flags false; 14/14 unsafe configurations rejected |
| Root: M02 sensitive-file byte comparison and original-test-function AST inventory | PASS; preserved approved authentication/history |
| `miniapp`: `node --check scripts/test-auth-integration.mjs` / `npm run lint` | PASS after harness updates |
| Root: `git diff --check` | PASS |

The initial backend run was **88 passed / 89 setup errors** because the new
internal-only Docker network did not publish the host test port. PostgreSQL
itself was healthy. Connecting the task-owned DB to the bridge restored the
loopback binding; the final 180-case suite passes. No failing test was skipped.

The first container browser run passed its first four flows, then failed a new
assertion aimed at `/docs` on the SPA gateway rather than the private API. That
URL serves the frontend fallback. The probe now targets private loopback API
`/docs` (404 in production), and editing targets its exact draft form so repeated
runs tolerate earlier disposable records. Final container run passes all seven.
These were test setup/probe corrections; no M02 or M03 application/security
implementation was changed in this acceptance pass.

## Changes made during final review

- Added three cached-creation stale-session/account regression cases.
- Extended the existing Node real-stack harness with `TEST_CONTAINER_API=true`
  to test the packaged application at its fixed loopback port. This is not a
  backend setting or production login path. Added Customer/Owner readiness
  assertions and the private production-docs probe.
- Extended backend CI to build the image, migrate/start a production-mode
  disposable container, run the seven browser flows and clean it up. The
  existing host backend/frontend suites and generated-contract drift checks
  remain. Hosted CI is **not observed or claimed green** here.
- Added this review and updated the runbook/historical-report link. No migration
  revision, auth implementation, business service or future milestone changed.

## Remaining risks and milestone boundaries

- Android/iOS/Desktop Telegram, BotFather launch and intended deployed HTTPS
  proxy remain external checks; local TLS gateway evidence does not close G1.
- Notification outbox is durable/pending only. Delivery/routing belongs to M08,
  retries/reporting to M13. Retention of audit/idempotency/outbox and M02 proof/
  session records is unresolved; no unsafe pruning was introduced.
- Application policies enforce customer isolation, not PostgreSQL RLS. Production
  least-privilege DB roles, trigger-administrator trust and backup/restore are
  still release work. Privileged DB owners can disable triggers/truncate tables.
- Business writes do not yet have a separate per-actor abuse throttle. Authentication
  has its existing DB-backed rate limit and JSON command bodies are bounded;
  deployment-level API quotas/hardening remain required before public traffic.
- Idempotency protects exact actor/action/key retries, not independently generated
  keys after a full WebView reload. Client keys remain in memory only. Reload/
  inspect persisted drafts before issuing a new creation after ambiguity.
- Only M03's `draft` and terminal `cancelled` request states are enabled.
  Submission stays blocked until file/scope validation exists. Combined print
  derivation, project status aggregation, full intake, uploads, workers,
  quotations, payable orders, payments, inventory and printer controls are absent.
- Production frontend/packaged API tests are local automated evidence. Hosted
  Actions, production deployment/monitoring and live-release gates are not
  certified by these results.

## Repository and pull-request handoff

Dedicated branch: `codex/m03-business-foundation`, based directly on approved
M02 commit `08fb8e0353f0364b722aa3a3e07454124b2f1ebc`. Target review base:
`codex/m02-telegram-auth`; this presents M03 alone because remote `main` still
points to the initial commit. This is a stacked review, preserving M02 ancestry
without a rebase, squash, force-push or merge.

The prepared PR title is **M03: Add transactional business backend foundation**.
Its description covers simulation draft APIs/UI, ownership/version/idempotency,
atomic audit/outbox, migration safety, complete checks and deferred boundaries.
Prepared description: `.local/m03-pr-body.md` (ignored local artifact). Git
publication uses `git push --set-upstream origin codex/m03-business-foundation`;
the final handoff verifies the remote branch SHA and M02 ancestry.

GitHub API access is currently blocked by the environment proxy:
`curl https://api.github.com/repos/DaemionBladee/3DPS-MiniApp` fails the CONNECT
tunnel with HTTP 403. Git transport to the selected repository is available.
`gh auth status` cannot validate the current token through that blocked route;
this is not evidence that the credential itself is invalid. No PR number or
hosted CI result is claimed. There are no GitHub connector/desktop browser
control tools offered in this executor to complete an authenticated web fallback.

Review branch: https://github.com/DaemionBladee/3DPS-MiniApp/tree/codex/m03-business-foundation

Prepared comparison/PR creation page:
https://github.com/DaemionBladee/3DPS-MiniApp/compare/codex%2Fm02-telegram-auth...codex%2Fm03-business-foundation?expand=1

Creating the PR through `gh pr create --draft --base codex/m02-telegram-auth
--head codex/m03-business-foundation --title "M03: Add transactional business
backend foundation" --body-file .local/m03-pr-body.md` requires access to
`api.github.com`. The runtime networking instructions require an approved
configuration change for an explicitly blocked destination. No proxy bypass,
environment publication, merge or deployment is attempted.
