# Codex Task M02 — Telegram auth, sessions, and two-role authorization

**Prerequisite:** M01 foundation and a reviewed backend API contract.

Read `AGENTS.md`, `docs/SECURITY.md`, `docs/API_CONTRACTS.md`, `docs/DEPENDENCY_MATRIX.md`, and the existing auth code before editing.

## Implement
1. Bot launch button/menu URL and a development/testing setup for HTTPS Mini App access.
2. Send **raw** Telegram `initData` from React to FastAPI.
3. Verify Telegram HMAC server-side using bot token, strict parse, integrity and time checks; tests include tampered, expired, missing and duplicate fields.
4. Create **minimal SQLAlchemy/Alembic migrations** for users and hashed/revocable server sessions (plus auth DB test fixtures); create/retrieve user by verified Telegram ID. Owner provisioned only from trusted server configuration/database migration, never open signup. M03 extends these same migrations and models.
5. Secure opaque server-side session, HttpOnly/Secure cookie, logout/revocation, CSRF checks for mutating APIs.
6. `/api/v1/auth/me` response with current role and capabilities; two role-specific frontend views.
7. Protect an owner-only test endpoint and user-scoped auth fixtures; denial tests. Full cross-customer request/file isolation tests belong to M04/M09 when those resources exist.
8. Ensure mock auth never works when production configured.
9. If Codex Cloud cannot expose an HTTPS address to a phone or run Postgres/Docker, run available unit/integration tests and document external phone-test steps as **pending**, not passed.

## Acceptance
Automated HMAC/session/CSRF/owner-only endpoint tests pass; no token or initData leaks in logs. **Record real Telegram phone tests as PASS only if run with actual bot/HTTPS/devices; otherwise PENDING with a clear G1 validation procedure.** Stop after M02.
