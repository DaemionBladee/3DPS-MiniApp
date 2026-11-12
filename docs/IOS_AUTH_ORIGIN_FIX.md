# Telegram iOS opaque-Origin authentication compatibility

Date: 2026-11-12 (Asia/Rangoon). Base: committed M07 `ce24842`.
This is an authentication compatibility fix only. M08, database history, Owner
provisioning, live business gates and production deployment are unchanged.

## Cause and security decision

The reported iOS request reached FastAPI with `Origin: null`. The old middleware
rejected it before JSON parsing or Telegram verification, so no identity/session
was created. `GET /auth/me` returning 401 before login was expected. The new
regression reproduced the old login 403 before the fix.

A null Origin is an **opaque origin**, which can also come from sandboxed attacker
frames, data/file documents and privacy features. It is never proof of Telegram,
same-origin access or authorization. No User-Agent, frontend role, client platform
flag, forwarded header or configurable wildcard is used to trust it.

`core/request_security.py` checks browser evidence before route execution:

| Evidence | Policy |
| --- | --- |
| Non-null Origin | Must exactly match configured PUBLIC_BASE_URL. |
| Missing Origin on a mutation | Rejected, even with a trusted Referer/CSRF token. |
| Explicit `Origin: null` login | Only POST /api/v1/auth/telegram; exactly one application/json Content-Type, valid/fresh HMAC proof, shared rate limit and atomic single-use proof required. |
| Explicit `Origin: null` other mutation | Middleware resolves a real, active cookie session and verifies its session-bound CSRF token before any route runs. Existing route authorization/write checks still run. |
| Sec-Fetch-Site present | `same-origin` permitted; cross-site, same-site and unknown values rejected. `none` is permitted only on reads (direct navigation), never mutations. |
| Mutation Fetch Mode / Destination present | Only `cors`/`same-origin` mode and `empty` destination. Navigation, no-cors, frame/image and unknown destinations rejected. |
| Referer present | Must be a well-formed HTTP(S) URL with the configured scheme, hostname and effective port. Prefix matching, userinfo, malformed ports, fragments, controls and parser-repaired input are rejected. |
| Duplicate browser security headers | Rejected; duplicate login Content-Type is rejected too. |

Same-origin evidence is corroboration, never a substitute for a signed login proof
or session CSRF. Contradictory evidence is rejected even if Origin matches or the
caller has valid credentials. Hostile Fetch Metadata also blocks session/CSRF reads.

Some embedded clients omit Referer and Fetch Metadata. For those requests, the
explicit null-origin login fallback relies on the verified single-use Telegram
credential and non-simple JSON request. Authenticated writes rely independently
on a cryptographic token derived from the current cookie session in X-CSRF-Token.
The server grants **no CORS**, including no `Access-Control-Allow-Origin: null` or
credentialed CORS. Ordinary foreign or opaque web pages cannot read the session
CSRF response under the same-origin policy; cross-origin JSON/custom-header requests
require a preflight that is not granted. Simple HTML form bodies cannot use the
JSON login path. This fallback assumes browser same-origin/preflight enforcement;
it does not attempt to authenticate arbitrary HTTP clients by browser headers.

The HMAC verifier, timestamp bounds, normalized replay digest/unique index,
transactional session rotation/revocation, fixed expiry, Secure/HttpOnly/
SameSite=Lax/__Host- cookie and server Owner allowlist are unchanged. Null-origin
compatibility is always protected by these credentials and has no dev bypass flag.

The React AuthProvider still checks the real cookie first, submits raw initData
once, retires attempted proofs and reads roles from FastAPI. The API client keeps
relative paths, mode/credentials same-origin and session CSRF headers; no browser
Origin spoofing, localStorage session, initDataUnsafe identity or insecure cookie
workaround is introduced. The only runtime frontend change is an explanatory comment.

## Logging review

Application auth logs contain fixed rejection codes and successful internal user
UUID/role only. No body, initData, cookie, CSRF, bot token, Referer URL or header
value is logged by the new policy. Validation/DB errors retain sanitized responses.
Tests capture successful and rejected auth logs using canaries. Existing launch
commands keep Uvicorn access logging disabled. External proxy/tunnel/debug logging
must also avoid bodies, cookies, Authorization headers and signed launch material.

## CachyOS rebuild and real-device retest

Use the dedicated test bot, development database and existing ignored `.env.local`.
Keep the current Quick Tunnel running so its hostname does not change mid-test.
Set PUBLIC_BASE_URL to the exact HTTPS Mini App origin (scheme/host/optional port,
no path), and keep the bot launch URL consistent. Keep Owner IDs server-side and
all live/mock-auth gates disabled. Never print or paste the env file or token.

From repository root, rebuild/recreate only the API with the reviewed fix:

```sh
docker compose --env-file .env.local config --quiet
docker compose --env-file .env.local build api
docker compose --env-file .env.local up -d --no-deps --force-recreate api
```

This fix requires **no migration command**, DB reset or volume replacement. Do not
run `down -v`. If running FastAPI directly instead, stop that test API and restart:

```sh
cd backend
uv sync --frozen
.venv/bin/uvicorn app.main:create_app --factory --env-file ../.env.local --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
```

For the existing Vite development setup, ensure its backend proxy points to
http://127.0.0.1:8000, and run with real Telegram presentation, not the UI mock:

```sh
cd miniapp
npm ci
VITE_TELEGRAM_MOCK=false npm run dev
```

If Vite rejects the tunnel hostname, add only that exact hostname using Vite's
supported `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` environment variable when
starting the test server; do not enable all hosts. If the tunnel is restarted,
update the exact PUBLIC_BASE_URL, API container environment and bot launch URL.
If using the optional Compose bot service after a URL change, recreate it with
`docker compose --env-file .env.local --profile bot up -d --no-deps --force-recreate bot`.
Expose the frontend origin through the tunnel with /api proxied to the private API;
do not expose PostgreSQL or use a separate browser API origin/CORS workaround.

1. Fully close the old Mini App WebView and reopen it from the dedicated bot for
   fresh signed initData. “Retry” cannot reuse an already attempted/consumed proof.
2. On Telegram iOS, verify initial GET /auth/me 401 → POST /auth/telegram 200 →
   GET /auth/me 200. Check only statuses/rejection codes and header-presence classes;
   do not record bodies, signed data or cookie values.
3. Verify reload restores the cookie without another login; save a simulation draft
   and upload a small test model, confirming session CSRF works with null Origin.
4. Sign out (204), confirm /auth/me 401 and reopen for a fresh login. Verify the
   old proof/session is unusable; do not weaken replay protection for recovery.
5. Test Customer denial of Owner pages/APIs and provisioned Owner access. Test
   expiry/relaunch, light/dark/safe areas and private downloads. Repeat on Telegram
   Android/Desktop to catch client-specific cookie/header differences.

## Remaining client limitations

Cloud tests send the reported headers through a real HTTP client and
HTTPS/FastAPI/PostgreSQL, then verify production React restores the resulting
secure cookie. Chromium controls its browser Origin header; these tests do not
claim that browser routing reproduces WKWebView's opaque-origin behavior. They are not actual Telegram iOS/WKWebView or Cloudflare
Quick Tunnel tests. Real-device verification above remains required.

Clients must retain the secure first-party cookie and execute API requests under
the app's real origin. A genuinely cross-site/no-cors/navigation request or a
foreign/malformed Referer is deliberately denied, even if a WebView emits it.
If iOS sends those headers, or actually enforces an opaque-origin CORS boundary,
this compatibility path cannot safely treat it as same-origin. Correct how the
page/proxy is served and gather redacted header-presence/error-code evidence;
do not allow null CORS, forge browser metadata, disable CSRF/SameSite, reuse proofs
or trust an iOS/Telegram User-Agent. Cookie blocking/storage eviction can still
require a fresh Telegram launch.

## Verification and actual results

All checks used synthetic Telegram signing credentials and disposable PostgreSQL
16 databases (`3dps_test_ios_origin`, `3dps_test_browser_iosorigin*`, and
`3dps_test_browser_ioscontainer`). No production data or real bot was used.

| Check | Actual command and result |
| --- | --- |
| Reproduction | Before the fix, the new valid-null-Origin login test failed with actual 403 instead of expected 200. |
| Auth/Origin suite | `TEST_DATABASE_URL=... backend/.venv/bin/python -m pytest -q backend/tests/test_request_security.py backend/tests/test_ios_auth_origin.py backend/tests/test_auth_api.py backend/tests/test_auth_acceptance_regressions.py backend/tests/test_auth_rate_limits.py backend/tests/test_telegram_verification.py`: **178 passed**, including fresh/forged/expired/duplicate/malformed proofs, replay races, cookies/CSRF, Owner and log canaries. |
| Business regression | `TEST_DATABASE_URL=... M06_TEST_WORKER_IMAGE=sha256:... backend/.venv/bin/python -m pytest -q backend/tests --ignore=backend/tests/test_analysis.py --ignore=backend/tests/test_worker_sandbox.py`: **467 passed in 227.79s**, covering M02–M07 API/domain/migration tests and actual native slicing in the M07 pricing integration test. |
| Browser-header unit rerun | `PYTHONPATH=backend backend/.venv/bin/python -m pytest -q backend/tests/test_request_security.py`: **31 passed** after tightening duplicate-header assertions. These overlap the 467. |
| Ruff | From backend: `.venv/bin/ruff check app alembic tests scripts ../telegram_bot ../worker`: passed. |
| Mypy | From backend: `.venv/bin/mypy app scripts ../telegram_bot ../worker`: passed, **68 source files**. |
| Frontend | `npm --prefix miniapp run check`: strict TypeScript, ESLint, **108 Vitest tests**, production build and production mock-exclusion artifact check passed. ESLint also passed after final HTTP test-harness changes. |
| Playwright | `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm --prefix miniapp run test:e2e`: **10 passed**. |
| HTTPS real stack | `TEST_BROWSER_DATABASE_URL=... PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm --prefix miniapp run test:auth-integration`, with M06_TEST_WORKER_IMAGE unset: **18 flows passed**, including two new real opaque-header HTTP + production React cookie-restoration/Owner flows. No API responses are mocked. |
| Container | `docker --host=unix:///var/run/docker.sock build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -f backend/Dockerfile -t 3dps-api:ios-origin-test .`: passed. Production-mode packaged API startup passed. |
| Container HTTPS real stack | `TEST_CONTAINER_API=true TEST_BROWSER_DATABASE_URL=... PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium node miniapp/scripts/test-auth-integration.mjs`: **18 flows passed**, including the opaque-header flows. |
| Schema/contracts | `alembic heads/check`: unchanged **0006_pricing_eligibility** head, no schema drift. OpenAPI export and TypeScript regeneration matched their pre-fix SHA-256 hashes. All migrations and auth/session/Telegram-verification source files are unchanged. |
| Live gates | Packaged API: production mode, simulation true; development auth, binding quotes, auto quotes, payment approval, live payments and real printing all false. |
| Source checks | `git diff --check`: passed. No request/header/body diagnostics were added to runtime logging. |

The full 19-case analysis and 19-case worker-sandbox modules were not rerun for
this middleware fix; the excluded paths are explicit above. A host browser attempt
with the extra M06 worker CLI flow failed during CLI startup; the independent
pinned-image registry probe/profile-registration retry passed. The final 18-flow
host/container runs deliberately omit that separate worker CLI flow. Parser,
worker execution limits and worker code were not changed to make this fix pass.
The M07 regression still performed actual slicing/provenance checks successfully.

An initial browser harness tried to override Chromium-controlled Origin through
routing; an on-wire gateway counter showed that was not reliable. It was replaced
with real opaque-header HTTP requests and browser cookie restoration, rather than
claiming a simulated WKWebView had been verified. Real iOS/Cloudflare/CachyOS and
VPS/Caddy checks remain external. GitHub CI has not been triggered or checked;
no commit, push, merge, publication or deployment was authorized for this fix.

Temporary API container/private volume and synthetic environment file are removed
after tests. The pre-existing loopback PostgreSQL test container remains available.
Stop for review; do not begin M08.

## Changed files

- `backend/app/core/request_security.py`
- `backend/app/main.py`
- `backend/tests/test_auth_api.py`
- `backend/tests/test_ios_auth_origin.py`
- `backend/tests/test_request_security.py`
- `docs/AUTHENTICATION.md`
- `docs/IOS_AUTH_ORIGIN_FIX.md`
- `docs/SECURITY.md`
- `docs/adr/0002-telegram-authentication.md`
- `miniapp/scripts/ios-auth-integration.mjs`
- `miniapp/scripts/test-auth-integration.mjs`
- `miniapp/src/lib/api/client.ts`
