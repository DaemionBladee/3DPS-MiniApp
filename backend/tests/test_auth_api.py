import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app.database.models import Session, User
from app.main import create_app
from tests.conftest import make_settings
from tests.signing import CUSTOMER_ID, ORIGIN, OWNER_ID, fields_for, sign_fields, signed_data


async def login(client: AsyncClient, user_id: int = CUSTOMER_ID) -> dict[str, object]:
    response = await client.post("/api/v1/auth/telegram", json={"init_data": signed_data(user_id)})
    assert response.status_code == 200
    result = response.json()
    assert isinstance(result, dict)
    return result


@pytest.mark.asyncio
async def test_health_and_anonymous_auth_denials(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/health")).status_code == 200
    for path in ["/api/v1/auth/me", "/api/v1/auth/csrf", "/api/v1/owner/auth-check"]:
        assert (await client.get(path)).status_code == 401


@pytest.mark.asyncio
async def test_customer_session_secure_cookie_and_hashed_database_storage(client: AsyncClient, app: FastAPI) -> None:
    response = await client.post("/api/v1/auth/telegram", json={"init_data": signed_data()})
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["role"] == "customer"
    assert body["user"]["telegram_id"] == str(CUSTOMER_ID)
    assert body["environment"] == "simulation"
    assert isinstance(body["csrf_token"], str) and len(body["csrf_token"]) >= 32
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("__Host-3dps_session=")
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert "Path=/" in cookie and "Domain=" not in cookie
    raw_token = client.cookies.get("__Host-3dps_session")
    assert raw_token is not None
    async with app.state.session_factory() as db:
        rows = (await db.scalars(select(Session))).all()
        assert len(rows) == 1
        assert rows[0].token_hash == hashlib.sha256(raw_token.encode()).hexdigest()
        assert rows[0].token_hash != raw_token
        assert rows[0].revoked_at is None
        assert rows[0].expires_at.tzinfo is not None
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"] == body["user"]
    assert me.headers.get("cache-control") == "no-store"


@pytest.mark.asyncio
async def test_only_trusted_server_provisioned_telegram_id_is_owner(client: AsyncClient) -> None:
    first = await login(client)
    assert first["user"]["role"] == "customer"
    assert (await client.get("/api/v1/owner/auth-check")).status_code == 403
    owner = await login(client, OWNER_ID)
    assert owner["user"]["role"] == "owner"
    assert (await client.get("/api/v1/owner/auth-check")).status_code == 200


@pytest.mark.asyncio
async def test_frontend_role_injection_is_rejected_and_does_not_create_owner(client: AsyncClient, app: FastAPI) -> None:
    response = await client.post("/api/v1/auth/telegram", json={"init_data": signed_data(), "role": "owner"})
    assert response.status_code == 422
    async with app.state.session_factory() as db:
        assert (await db.scalars(select(User))).all() == []


@pytest.mark.asyncio
async def test_signed_arbitrary_role_field_never_overrides_server_config(client: AsyncClient) -> None:
    fields = fields_for()
    fields["role"] = "owner"
    response = await client.post("/api/v1/auth/telegram", json={"init_data": sign_fields(fields)})
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "customer"


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", [-301, 60])
async def test_api_rejects_expired_or_future_signed_launch(client: AsyncClient, offset: int) -> None:
    response = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": signed_data(timestamp=int(time.time()) + offset)},
    )
    assert response.status_code == 401
    assert "__Host-3dps_session" not in client.cookies


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", ["no-signature", "user=%FF", "user=%GG", "", "auth_date=1&auth_date=2"])
async def test_api_rejects_malformed_launch_without_leaking_input(client: AsyncClient, malformed: str) -> None:
    response = await client.post("/api/v1/auth/telegram", json={"init_data": malformed})
    assert response.status_code in {401, 422}
    assert "input" not in response.json()
    assert "__Host-3dps_session" not in client.cookies


@pytest.mark.asyncio
async def test_api_rejects_wrong_signature_and_duplicate_decoded_fields(client: AsyncClient) -> None:
    raw = signed_data()
    pairs = dict(parse_qsl(raw))
    pairs["hash"] = "0" * 64
    forged = await client.post("/api/v1/auth/telegram", json={"init_data": urlencode(pairs)})
    assert forged.status_code == 401
    duplicate = await client.post("/api/v1/auth/telegram", json={"init_data": f"{raw}&%75ser=duplicate"})
    assert duplicate.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["https://attacker.example", "null", "https://testserver.attacker.example"])
async def test_login_origin_is_checked_before_session_creation(client: AsyncClient, origin: str) -> None:
    response = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": signed_data()},
        headers={"Origin": origin},
    )
    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.asyncio
async def test_login_requires_origin_and_json_content_type(client: AsyncClient) -> None:
    del client.headers["Origin"]
    missing_origin = await client.post("/api/v1/auth/telegram", json={"init_data": signed_data()})
    assert missing_origin.status_code == 403
    wrong_content_type = await client.post(
        "/api/v1/auth/telegram",
        content=json.dumps({"init_data": signed_data()}),
        headers={"Origin": ORIGIN, "Content-Type": "text/plain"},
    )
    assert wrong_content_type.status_code in {403, 415, 422}


@pytest.mark.asyncio
async def test_logout_requires_csrf_and_revokes_the_session(client: AsyncClient, app: FastAPI) -> None:
    body = await login(client)
    raw_token = client.cookies.get("__Host-3dps_session")
    assert (await client.post("/api/v1/auth/logout")).status_code == 403
    assert (await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "wrong"})).status_code == 403
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    token = body["csrf_token"]
    assert isinstance(token, str)
    logout = await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": token})
    assert logout.status_code == 204
    assert "Max-Age=0" in logout.headers["set-cookie"]
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    async with app.state.session_factory() as db:
        row = await db.scalar(select(Session))
        assert row is not None and row.revoked_at is not None
    assert raw_token is not None
    client.cookies.set("__Host-3dps_session", raw_token, domain="testserver.local", path="/")
    assert (await client.get("/api/v1/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_valid_csrf_cannot_bypass_wrong_origin(client: AsyncClient) -> None:
    body = await login(client)
    token = body["csrf_token"]
    assert isinstance(token, str)
    response = await client.post(
        "/api/v1/auth/logout", headers={"Origin": "https://attacker.example", "X-CSRF-Token": token}
    )
    assert response.status_code == 403
    assert (await client.get("/api/v1/auth/me")).status_code == 200


@pytest.mark.asyncio
async def test_csrf_is_bound_to_the_cookie_session(client: AsyncClient) -> None:
    first = await login(client)
    second = await login(client)
    first_token = first["csrf_token"]
    second_token = second["csrf_token"]
    assert isinstance(first_token, str) and isinstance(second_token, str)
    assert first_token != second_token
    response = await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": first_token})
    assert response.status_code == 403
    assert (await client.get("/api/v1/auth/csrf")).json()["csrf_token"] == second_token


@pytest.mark.asyncio
async def test_expired_and_admin_revoked_sessions_are_rejected(client: AsyncClient, app: FastAPI) -> None:
    await login(client)
    async with app.state.session_factory() as db:
        await db.execute(
            update(Session).values(
                created_at=datetime.now(UTC) - timedelta(hours=3),
                expires_at=datetime.now(UTC) - timedelta(hours=2),
            )
        )
        await db.commit()
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    await login(client)
    async with app.state.session_factory() as db:
        await db.execute(update(Session).values(revoked_at=datetime.now(UTC)))
        await db.commit()
    assert (await client.get("/api/v1/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_secure_cookie_is_not_sent_on_plain_http(client: AsyncClient) -> None:
    await login(client)
    response = await client.get("http://testserver/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_proof_cannot_be_replayed_even_with_encoding_variants(client: AsyncClient) -> None:
    raw = signed_data()
    first = await client.post("/api/v1/auth/telegram", json={"init_data": raw})
    assert first.status_code == 200
    await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": first.json()["csrf_token"]})
    replay = urlencode(list(reversed(parse_qsl(raw)))).replace("%7B", "%7b")
    response = await client.post("/api/v1/auth/telegram", json={"init_data": replay})
    assert response.status_code in {401, 409}
    assert (await client.get("/api/v1/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_identity_fixture_enforces_cross_customer_ownership(client: AsyncClient) -> None:
    first = await login(client, CUSTOMER_ID)
    first_id = first["user"]["id"]
    assert (await client.get(f"/api/v1/auth/users/{first_id}")).status_code == 200
    await login(client, CUSTOMER_ID + 1)
    assert (await client.get(f"/api/v1/auth/users/{first_id}")).status_code == 404
    assert (await client.get(f"/api/v1/auth/users/{uuid4()}")).status_code == 404


@pytest.mark.asyncio
async def test_disabled_users_cannot_keep_access(client: AsyncClient, app: FastAPI) -> None:
    await login(client)
    async with app.state.session_factory() as db:
        await db.execute(update(User).values(active=False))
        await db.commit()
    assert (await client.get("/api/v1/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_database_role_edits_do_not_grant_owner_privileges(client: AsyncClient, app: FastAPI) -> None:
    await login(client)
    async with app.state.session_factory() as db:
        await db.execute(update(User).values(role="owner"))
        await db.commit()
    assert (await client.get("/api/v1/owner/auth-check")).status_code == 403
    assert (await client.get("/api/v1/auth/me")).json()["user"]["role"] == "customer"


@pytest.mark.asyncio
async def test_removing_trusted_owner_configuration_demotes_existing_session(
    client: AsyncClient, clean_database: str
) -> None:
    await login(client, OWNER_ID)
    raw_token = client.cookies.get("__Host-3dps_session")
    assert raw_token is not None
    replacement = create_app(make_settings(clean_database, owner_telegram_ids=""))
    async with replacement.router.lifespan_context(replacement):
        async with AsyncClient(
            transport=ASGITransport(app=replacement),
            base_url=ORIGIN,
            headers={"Origin": ORIGIN, "Cookie": f"__Host-3dps_session={raw_token}"},
        ) as reconfigured:
            assert (await reconfigured.get("/api/v1/owner/auth-check")).status_code == 403
            assert (await reconfigured.get("/api/v1/auth/me")).json()["user"]["role"] == "customer"


@pytest.mark.asyncio
async def test_login_rotates_and_revokes_previous_cookie_session(client: AsyncClient) -> None:
    await login(client)
    old_token = client.cookies.get("__Host-3dps_session")
    assert old_token is not None
    await login(client)
    assert client.cookies.get("__Host-3dps_session") != old_token
    assert (await client.get("/api/v1/auth/me", headers={"Cookie": f"__Host-3dps_session={old_token}"})).status_code == 401


@pytest.mark.asyncio
async def test_concurrent_replay_creates_one_user_and_one_session(client: AsyncClient, app: FastAPI) -> None:
    raw = signed_data()
    responses = await asyncio.gather(
        *(client.post("/api/v1/auth/telegram", json={"init_data": raw}) for _ in range(4))
    )
    assert [response.status_code for response in responses].count(200) == 1
    assert [response.status_code for response in responses].count(409) == 3
    async with app.state.session_factory() as db:
        assert len((await db.scalars(select(User))).all()) == 1
        assert len((await db.scalars(select(Session))).all()) == 1


@pytest.mark.asyncio
async def test_production_has_no_mock_login_endpoint(clean_database: str) -> None:
    production = create_app(make_settings(clean_database, app_env="production"))
    async with production.router.lifespan_context(production):
        async with AsyncClient(
            transport=ASGITransport(app=production), base_url=ORIGIN, headers={"Origin": ORIGIN}
        ) as http:
            for path in ["/api/v1/auth/mock", "/api/v1/auth/dev-login"]:
                response = await http.post(path, json={"role": "owner", "telegram_id": OWNER_ID})
                assert response.status_code == 404
            assert (await http.get("/api/v1/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_validation_errors_and_auth_logs_do_not_echo_signed_launch(client: AsyncClient, caplog: pytest.LogCaptureFixture) -> None:
    marker = "DO_NOT_ECHO_UNTRUSTED_INITDATA"
    raw = marker + signed_data()
    response = await client.post("/api/v1/auth/telegram", json={"init_data": raw, "role": "owner"})
    assert response.status_code == 422
    assert marker not in response.text
    assert marker not in caplog.text
