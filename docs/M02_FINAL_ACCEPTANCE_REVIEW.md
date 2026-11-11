# M02 final acceptance review

Review date: 2026-11-11 (Asia/Rangoon). Starting commit:
`411f9e6edbe2e112d703559a9bfb3368fd4f64d7`, branch `codex/m02-telegram-auth`.

**Local automated checks pass after the corrections below. Stop for owner
review; M03 is not authorized or implemented.** Hosted CI execution and real
Telegram client/G1 evidence remain unverified. Automatic session pruning is not
implemented and is an explicit retention limitation, not a passed cleanup job.

Reviewed the actual implementation against root `AGENTS.md`, `SECURITY.md`,
`INTEGRITY_RULES.md` and `prompts/M02_TELEGRAM_AUTH.md`, along with the auth
runbook, migration and CI files. No signature, Owner-role or concurrent replay
bypass was reproduced. One frontend recovery defect and a CI trigger gap were
corrected locally. This review does not approve live business features.

## Requested checks

| Item | Result and evidence |
|---|---|
| 1. Documented Telegram signed fields | PASS. Bot-token HMAC removes only `hash`; optional `signature` remains signed. Added full-field tests for `query_id`, `receiver`, `chat`, `chat_type`, `chat_instance`, `start_param`, `can_send_after` and `signature`; tampering with any fails. Valid launches without optional `query_id` succeed. `receiver`/chat/start parameters never select the authenticated identity. Existing malformed/duplicate/Unicode/timestamp/wrong-token tests remain. The independent pinned Aiogram signature checker agrees. This is the bot-token HMAC protocol, not third-party Ed25519 verification. |
| 2. Concurrent replay | PASS. Six URL/order/encoding/hash-case variants of one proof race across two independent app instances: exactly one 200, five 409s, one user and one session. PostgreSQL proof uniqueness and transaction rollback are authoritative. Failed replacement/replay does not revoke a previously valid cookie session. |
| 3. Legitimate recovery | CORRECTED and PASS. Backend fresh-launch tests cover logout, expiry, administrative revocation, invalid proof and replayed proof. Frontend retries now restore cookies first and may submit an unseen current launch; a previously attempted/logout proof is never resubmitted by that provider. A genuinely fresh SDK proof can recover a retained WebView. Stale request failures cannot overwrite newer identity; concurrent recovery coalesces an in-flight login. See the ambiguous-response limitation below. |
| 4. HTTPS proxy/cookie/CSRF/Origin | PASS for the tested topology: production React -> loopback HTTPS gateway -> HTTP FastAPI -> PostgreSQL. The real cookie is Secure/HttpOnly/Lax/root-path and unavailable to JS. Missing, `null` and wrong Origin login attempts are rejected without consuming a valid proof. Correct CSRF with wrong Origin and correct Origin with wrong CSRF both fail. Logout revokes the old cookie server-side. Host/forwarded hints cannot replace configured Origin. This is not deployed Caddy or real Telegram device evidence. |
| 5. Owner provisioning | PASS. Only trusted server allowlist selects Owner; empty allowlist grants none. Client role fields, signed arbitrary role fields, `initDataUnsafe`, receiver/chat fields, URL hints and DB role edits cannot grant privileges. Removing the trusted Owner entry demotes an existing session on its next request. |
| 6. Customer isolation | PASS. Customer gets 403 from the actual Owner endpoint and cannot open its UI. Anonymous access gets 401. Self-user fixture rejects another UUID with 404. Future request/file/order resources do not exist yet; their isolation is not claimed. |
| 7. PostgreSQL migrations and cleanup | Migration/expiry/revocation PASS; automatic session pruning NOT IMPLEMENTED. Fresh upgrade, seeded-head re-upgrade, unique/FK/role constraints and disposable downgrade/recovery pass. Current head is `0001_auth_foundation`; Alembic detects no metadata drift. Logout and expiry deny access while retaining proof history. Rate-counter cleanup does not delete session records. No retained or production database was changed. |
| 8. Backend/frontend checks | PASS: 131 backend tests, 51 frontend tests, 10 UI browser tests, five actual-stack browser flows; strict types, lint and production build pass. Commands below. |
| 9. GitHub CI | Configuration reviewed and trigger gap corrected; hosted execution UNKNOWN. Original push filters matched only `main`/`DaemionBladee-dev`, so the initial `codex/m02-telegram-auth` push was not eligible for those push triggers. Both workflows now include `codex/**` and `workflow_dispatch`. At review completion these edits were local, not yet pushed. GitHub API requests for runs/checks/PR metadata failed with `Forbidden`; no run count, success, failure or absence is asserted. A separately created PR could have triggered CI, but its existence/status could not be checked. |
| 10. Credentials, mocks and live features | PASS within inspected source/build scope. No real env files, keys, dumps, customer models or credential-pattern matches were found in the source payload; test credentials are synthetic fixtures. Configured credential values are absent from both production artifacts. The mock module is excluded even when its build flag is forced true. Backend has no mock-login endpoint and rejects enabled live/mock-auth flags. Binding quotes, payments and printers remain unavailable. This is not comprehensive credential-history or deployment scanning. |

## Corrected issues and changed files

1. **Recovery was blocked by provider-lifetime booleans.** The original
   `loginAttempted`/`preventRelogin` flags made “Check connection again” restore
   cookies only. An initial `/auth/me` outage prevented the still-unused launch
   from ever being submitted through retry. A retained provider could also not
   accept a different, genuinely fresh launch after logout/expiry/rejection.
   Replaced these flags with per-proof retirement and keyed pending requests,
   keeping generation guards and cookie-first restoration. Added “Check sign-in
   again” for signed-out Telegram contexts. No role/signature authority moved to
   the frontend, and used/ambiguous proofs remain retired.
2. **CI push filters omitted the development review branch.** Added `codex/**`
   and manual dispatch configuration without changing read-only permissions or
   introducing production secrets. Trigger eligibility is configuration evidence,
   not execution evidence. Manual-dispatch UI availability also depends on the
   workflow being present on the repository's default branch.
3. **Acceptance coverage was incomplete.** Added 16 backend regressions for
   optional fields, fresh relaunch, existing-session preservation and cross-app
   canonical races. Added six frontend recovery/concurrency regressions. One
   visibility-event test initially raced its effect subscription; it now waits
   for that subscription before dispatching the event. The production browser
   integration adds real proxy Origin/CSRF negatives plus fresh-proof recovery
   after logout and rejection.

Application/CI/test changes:

```text
.github/workflows/{authentication.yml,frontend.yml}
backend/tests/test_telegram_verification.py
backend/tests/test_auth_acceptance_regressions.py
miniapp/scripts/test-auth-integration.mjs
miniapp/src/app/PresentationGate.tsx
miniapp/src/features/auth/{AuthProvider.tsx,AuthProvider.test.tsx}
```

This report and the auth runbook/README references are updated. Backend domain
code, dependency declarations, OpenAPI contracts and migration revisions were
not changed. No additional retention policy was invented.

## Actual commands and outcomes

Only synthetic credentials and disposable loopback databases were used. Values
are omitted here; `TEST_DATABASE_URL` referred to `3dps_test_review` and
`TEST_BROWSER_DATABASE_URL` to separate `3dps_test_browser_review`, both on
`127.0.0.1:55432`, in this task's PostgreSQL 16.15 container.

| Working directory / command | Actual result |
|---|---|
| `backend/`: `.venv/bin/pytest -q` with `TEST_DATABASE_URL` | **131 passed**, no skips; final parent run 11.48s. The suite includes migration upgrade/seed/recovery and constraints in its own uniquely named disposable databases. |
| `backend/`: `.venv/bin/ruff check app alembic tests scripts ../telegram_bot` | PASS. |
| `backend/`: `.venv/bin/mypy app scripts ../telegram_bot` | PASS, strict, 17 source files. |
| `backend/`: `.venv/bin/alembic current` with each review DB's `DATABASE_URL` | `0001_auth_foundation (head)` for both databases. |
| `backend/`: `.venv/bin/alembic check` on the review DB | PASS: `No new upgrade operations detected.` |
| `miniapp/`: `npm run test -- src/features/auth/AuthProvider.test.tsx` | Final focused run: 15 passed. Earlier run exposed the visibility subscription timing issue; no assertion was disabled. |
| `miniapp/`: `npm run check` | PASS: strict TypeScript, zero-warning ESLint, **51 tests in 4 files**, production Vite build and forced-mock artifact exclusion. |
| `miniapp/`: `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e` | **10 passed**, no retries/skips. Includes responsive shells, role isolation and UI auth fixtures. |
| `miniapp/`: `TEST_BROWSER_DATABASE_URL=… PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:auth-integration` | **Five flows passed** against production React, actual FastAPI and PostgreSQL through HTTPS, with no API response mocks. Only the external Telegram presentation SDK is intercepted. |
| Repository: `git diff --check` and current source/bundle inspection | PASS at final code validation: no exposed env/key/model/dump payload; blank secret examples and disabled live flags; no mock module marker or configured credential value in either production artifact. |
| `gh api --method GET repos/DaemionBladee/3DPS-MiniApp/actions/runs -f head_sha=411f9e6edbe2e112d703559a9bfb3368fd4f64d7 …` | Failed, exit 1: outbound request reported `Forbidden`. No runs returned for inspection. |
| `gh api repos/DaemionBladee/3DPS-MiniApp/commits/411f9e6edbe2e112d703559a9bfb3368fd4f64d7/check-runs …` and PR-head metadata query | Same `Forbidden` failure. No hosted check conclusion was observed. No credential values were printed. |

The current official Telegram web documentation fetch was also blocked before an
HTTP response. Signature evidence therefore consists of the supplied normative
contract, inspected code and independent pinned Aiogram agreement, not a claim
to have fetched updated official documentation successfully during this review.

## Remaining limitations and review conditions

- **Real Telegram/G1 remains pending.** Native Android/iOS/Desktop launch,
  BotFather URL, actual bot credentials, deployed HTTPS/cookie/SameSite behavior
  and client-specific lifecycle behavior require the external checklist in
  [AUTHENTICATION.md](AUTHENTICATION.md). The tested local proxy does not replace
  actual Caddy/staging/device evidence.
- **Hosted CI remains unverified.** After the review changes are approved/pushed,
  inspect Actions/Checks through an authorized GitHub connection or the repository
  UI. Existing injected Git authentication worked for the earlier push; the
  failed API metadata request does not establish missing Git credentials or
  justify extracting/replacing them. No hosted pass is claimed here.
- **Session cleanup is retention-only.** Expired/revoked sessions cannot authorize
  requests but remain as replay tombstones. There is no session-pruning command
  or scheduler. A future reviewed purge must preserve proof uniqueness throughout
  its entire possible freshness window; session TTL can be shorter than that
  window, so deleting merely on `expires_at` would be unsafe. Approve privacy,
  evidence and retention requirements before implementing a purge.
- **Ambiguous delivered-login recovery is conservative.** If a login commits but
  its cookie never reaches the browser, the proof is consumed. Retry first
  checks for the cookie; otherwise a distinct signed launch is required. This
  preserves one-time replay protection. A launch without `query_id` that is
  byte-identical within the same timestamp second is likewise the same proof,
  not distinguishable new evidence; reopen with a fresh auth date/launch.
- **Trusted proxy/rate policy is unchanged.** Forwarded client addresses are not
  trusted, so users behind one gateway share rate buckets. Edge timeouts and
  wider deployment/retention policy remain separate reviews; no public or live
  feature was enabled to complete these tests.

Corrections were left uncommitted for review. The owner subsequently requested
their commit and push to the existing `codex/m02-telegram-auth` branch. This
does not establish a hosted CI result or authorize M03. No production data,
real bot messaging, environment publication or M03 work was performed.
