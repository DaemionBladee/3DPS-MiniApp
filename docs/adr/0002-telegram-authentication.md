# ADR 0002 — Telegram identity and database-backed session boundary

- Date: 2026-11-11 (Asia/Rangoon)
- Status: Implemented for M02; milestone review pending
- Scope: Authentication only; no M03 domain schema or live-operation permission

M01 is reviewed. Its presentation-only mocks and UI shells are preserved.
Server authority is introduced through one FastAPI modular-monolith foundation
and the initial shared Alembic chain. This selects technical security defaults,
not pricing, hardware, provider or commercial policy values.

Decisions:

1. Verify raw Telegram launch data with official bot-token HMAC-SHA256. Strict
   decoding and unique fields/JSON keys precede identity creation. Use 300-second
   freshness and at most 30-second future tolerance; bounded input. Compare MACs
   in constant time. Test against the independent Aiogram implementation.
2. Store users and opaque hashed/revocable sessions in PostgreSQL with UUIDs,
   one-time normalized launch-proof uniqueness and UTC timestamps. Initial
   revision is `0001_auth_foundation`; no create_all or M03 tables. Add only
   auth rate counters alongside these two tables so invalid attempts are counted
   atomically across workers; an in-memory or successful-session-only limiter
   would not satisfy the security requirement.
3. Provision Owner only from trusted `OWNER_TELEGRAM_IDS`, default empty; no
   first-user or frontend grant. Recompute effective role per request. Preserve
   self-resource checks even for Owner in the scoped auth fixture.
4. Always use `__Host-3dps_session`, Secure/HttpOnly/Lax/root-path/no-Domain;
   one-hour fixed default expiry. Never put session IDs in localStorage.
   Require exact configured Origin for mutations/login and session-bound CSRF
   for authenticated writes. Login is the narrow pre-session exception to CSRF,
   still guarded by Origin, JSON, rate limit and Telegram signature.
5. React restores the cookie before sending a fresh proof, coalesces StrictMode
   initialization, treats only API roles as authority, and clears private cache
   on session loss/logout. No backend development login exists. The M01 mock is
   an explicitly enabled, production-excluded UI presentation with no server user.
6. Export actual Pydantic/OpenAPI schemas and generate frontend types with a
   locked isolated toolchain. The TypeScript-5-only generator runs separately
   from the existing TypeScript 6 app; do not force incompatible peer installs.
7. Keep all live flags off and fail startup if live/mock-auth modes are requested.
   Use pinned private PostgreSQL/non-root API containers for development/testing.
   Do not start a real bot or modify BotFather without configured test credentials.

Consequences: replayed launch data needs a fresh Telegram launch, including after
logout. Rate buckets intentionally trust the transport peer only; proxy
aggregation and real-client cookie behavior need external evidence. Retention
and broader deployment hardening remain explicit later work. See the tested
[auth runbook](../AUTHENTICATION.md) and [M02 report](../M02_IMPLEMENTATION_REPORT.md).

## 2026-11-12 compatibility addendum

The exact-Origin rule above now has a narrow, credential-protected path for an
explicit opaque `Origin: null` from embedded clients. JSON login still requires
fresh, single-use Telegram HMAC evidence; every other opaque-origin mutation must
pass session-bound CSRF in middleware as well as existing route authorization.
Untrusted non-null origins, hostile Fetch Metadata, foreign Referer, absent write
Origin and permissive/null CORS remain forbidden. This does not alter HMAC,
replay/session SQL, cookie attributes, Owner provisioning or migration history.
Rationale, fallback assumptions and device-test limitations:
[IOS_AUTH_ORIGIN_FIX.md](../IOS_AUTH_ORIGIN_FIX.md).
