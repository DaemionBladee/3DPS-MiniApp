"""Opaque WebView origins never replace Telegram proof or session CSRF evidence."""

import asyncio
import json
import logging
import time
from urllib.parse import parse_qsl, urlencode
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.database.models import Session, User
from app.main import create_app
from tests.conftest import make_settings
from tests.signing import (
    BOT_TOKEN,
    CUSTOMER_ID,
    ORIGIN,
    OWNER_ID,
    fields_for,
    sign_fields,
    signed_data,
)

NULL = {"Origin": "null"}


async def opaque_login(client, user_id=CUSTOMER_ID):
    response = await client.post(
        "/api/v1/auth/telegram", headers=NULL, json={"init_data": signed_data(user_id)}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def no_identity(app):
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(User)) == 0
        assert await db.scalar(select(func.count()).select_from(Session)) == 0


@pytest.mark.parametrize(
    "evidence",
    [
        {},
        {"Sec-Fetch-Site": "same-origin"},
        {"Referer": ORIGIN + "/app?tab=project"},
        {
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": ORIGIN + "/app",
        },
    ],
)
async def test_null_origin_login_accepts_only_verified_proof_with_optional_browser_evidence(
    client, evidence
):
    response = await client.post(
        "/api/v1/auth/telegram", headers=NULL | evidence, json={"init_data": signed_data()}
    )
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "customer"
    cookie = response.headers["set-cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert "Path=/" in cookie and "Domain=" not in cookie
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    "kind", ["forged", "expired", "future", "duplicate", "malformed_user", "malformed"]
)
async def test_null_origin_invalid_proof_creates_no_identity(client, app, kind):
    fields = fields_for(
        timestamp=int(time.time()) + (-301 if kind == "expired" else 60 if kind == "future" else 0)
    )
    if kind == "malformed_user":
        fields["user"] = '{"id":false,"first_name":"Invalid"}'
    raw = sign_fields(fields, bot_token="wrong-bot" if kind == "forged" else BOT_TOKEN)
    if kind == "duplicate":
        raw += "&%75ser=duplicate"
    elif kind == "malformed":
        raw = "user=%GG"
    response = await client.post("/api/v1/auth/telegram", headers=NULL, json={"init_data": raw})
    assert response.status_code == 401
    assert "set-cookie" not in response.headers
    await no_identity(app)


@pytest.mark.parametrize(
    "content_type",
    ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data", "application/jsonp"],
)
async def test_null_origin_login_rejects_simple_form_and_non_json_bodies(client, app, content_type):
    response = await client.post(
        "/api/v1/auth/telegram",
        headers=NULL | {"Content-Type": content_type},
        content=json.dumps({"init_data": signed_data()}),
    )
    assert response.status_code == 415
    await no_identity(app)


@pytest.mark.parametrize("origin", ["null", ORIGIN])
@pytest.mark.parametrize(
    "hostile",
    [
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Sec-Fetch-Site": "none"},
        {"Sec-Fetch-Site": "garbage"},
        {"Sec-Fetch-Mode": "navigate"},
        {"Sec-Fetch-Mode": "no-cors"},
        {"Sec-Fetch-Dest": "iframe"},
        {"Referer": "https://attacker.example/"},
    ],
)
async def test_hostile_browser_evidence_rejects_even_valid_launch_and_consumes_no_proof(
    client, app, origin, hostile
):
    raw = signed_data()
    rejected = await client.post(
        "/api/v1/auth/telegram", headers={"Origin": origin} | hostile, json={"init_data": raw}
    )
    assert rejected.status_code == 403
    assert "access-control-allow-origin" not in rejected.headers
    await no_identity(app)
    assert (
        await client.post("/api/v1/auth/telegram", headers=NULL, json={"init_data": raw})
    ).status_code == 200


@pytest.mark.parametrize(
    "evidence", [{}, {"Sec-Fetch-Site": "same-origin", "Referer": ORIGIN + "/app"}]
)
async def test_null_origin_mutations_require_csrf_even_with_same_origin_evidence(client, evidence):
    session = await opaque_login(client)
    path = "/api/v1/requests"
    for token in (None, "incorrect-csrf"):
        response = await client.post(
            path,
            headers=NULL
            | evidence
            | {"Idempotency-Key": uuid4().hex}
            | ({"X-CSRF-Token": token} if token else {}),
            json={"service_type": "printing"},
        )
        assert response.status_code == 403
        assert response.json()["code"] == "csrf_invalid"
    accepted = await client.post(
        path,
        headers=NULL
        | evidence
        | {"Idempotency-Key": uuid4().hex, "X-CSRF-Token": session["csrf_token"]},
        json={"service_type": "printing"},
    )
    assert accepted.status_code == 201
    assert accepted.json()["request"]["mode"] == "simulation"


@pytest.mark.parametrize("origin", ["null", ORIGIN, "https://attacker.example"])
@pytest.mark.parametrize("site", ["cross-site", "same-site"])
async def test_hostile_origin_or_metadata_cannot_be_overridden_by_valid_csrf(client, origin, site):
    session = await opaque_login(client)
    rejected = await client.post(
        "/api/v1/auth/logout",
        headers={"Origin": origin, "Sec-Fetch-Site": site, "X-CSRF-Token": session["csrf_token"]},
    )
    assert rejected.status_code == 403
    assert (await client.get("/api/v1/auth/me", headers=NULL)).status_code == 200


async def test_explicit_untrusted_origin_rejected_with_valid_csrf_and_no_metadata(client):
    session = await opaque_login(client)
    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "https://attacker.example", "X-CSRF-Token": session["csrf_token"]},
    )
    assert response.status_code == 403
    assert (await client.get("/api/v1/auth/me")).status_code == 200


async def test_null_origin_cookie_restoration_owner_auth_and_rotation(client, app):
    first = await opaque_login(client)
    token = client.cookies.get("__Host-3dps_session")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url=ORIGIN,
        headers={**NULL, "Cookie": f"__Host-3dps_session={token}"},
    ) as restored:
        assert (await restored.get("/api/v1/auth/me")).json() == first
        assert (await restored.get("/api/v1/auth/csrf")).json()["csrf_token"] == first["csrf_token"]
        assert (await restored.get("/api/v1/owner/auth-check")).status_code == 403
    second = await opaque_login(client)
    assert second["csrf_token"] != first["csrf_token"]
    assert client.cookies.get("__Host-3dps_session") != token
    assert (
        await client.get(
            "/api/v1/auth/me", headers=NULL | {"Cookie": f"__Host-3dps_session={token}"}
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/logout", headers=NULL | {"X-CSRF-Token": first["csrf_token"]}
        )
    ).status_code == 403
    owner = await opaque_login(client, OWNER_ID)
    assert owner["user"]["role"] == "owner"
    assert (await client.get("/api/v1/owner/auth-check", headers=NULL)).status_code == 200


async def test_null_origin_concurrent_replay_and_logout_do_not_reuse_proof(client, app):
    raw = signed_data()
    responses = await asyncio.gather(
        *(
            client.post("/api/v1/auth/telegram", headers=NULL, json={"init_data": raw})
            for _ in range(4)
        )
    )
    assert sorted(response.status_code for response in responses) == [200, 409, 409, 409]
    session = next(response.json() for response in responses if response.status_code == 200)
    assert (
        await client.post(
            "/api/v1/auth/logout", headers=NULL | {"X-CSRF-Token": session["csrf_token"]}
        )
    ).status_code == 204
    canonical_variant = urlencode(list(reversed(parse_qsl(raw))))
    replay = await client.post(
        "/api/v1/auth/telegram", headers=NULL, json={"init_data": canonical_variant}
    )
    assert replay.status_code == 409
    await opaque_login(client)
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(User)) == 1
        assert await db.scalar(select(func.count()).select_from(Session)) == 2


async def test_null_origin_cannot_create_owner_from_frontend_data(client, app):
    response = await client.post(
        "/api/v1/auth/telegram", headers=NULL, json={"init_data": signed_data(), "role": "owner"}
    )
    assert response.status_code == 422
    await no_identity(app)
    fields = fields_for()
    fields["role"] = "owner"
    accepted = await client.post(
        "/api/v1/auth/telegram", headers=NULL, json={"init_data": sign_fields(fields)}
    )
    assert accepted.json()["user"]["role"] == "customer"


async def test_null_origin_remains_rate_limited(clean_database):
    app = create_app(make_settings(clean_database, auth_rate_limit=2))
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=ORIGIN, headers=NULL
        ) as client:
            for expected in (401, 401, 429):
                response = await client.post(
                    "/api/v1/auth/telegram", json={"init_data": "bad-proof"}
                )
                assert response.status_code == expected
            assert "retry-after" in response.headers
            await no_identity(app)


async def test_null_origin_does_not_enable_cors_or_form_preflight(client):
    response = await client.options(
        "/api/v1/auth/telegram",
        headers={
            **NULL,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code in {403, 405}
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-credentials" not in response.headers


async def test_hostile_metadata_blocks_cookie_and_csrf_reads(client):
    await opaque_login(client)
    for path in ("/api/v1/auth/me", "/api/v1/auth/csrf"):
        assert (
            await client.get(path, headers=NULL | {"Sec-Fetch-Site": "cross-site"})
        ).status_code == 403


async def test_opaque_mutations_are_protected_even_without_route_csrf_dependency(client, app):
    touched = []

    @app.post("/api/v1/test-unprotected-mutation")
    async def fixture():
        touched.append(True)
        return {"status": "ok"}

    session = await opaque_login(client)
    assert (await client.post("/api/v1/test-unprotected-mutation", headers=NULL)).status_code == 403
    assert touched == []
    assert (
        await client.post(
            "/api/v1/test-unprotected-mutation",
            headers=NULL | {"X-CSRF-Token": session["csrf_token"]},
        )
    ).status_code == 200
    assert touched == [True]


async def test_proof_cookie_csrf_and_secrets_never_enter_logs(client, caplog):
    caplog.set_level(logging.INFO)
    fields = fields_for()
    fields["query_id"] = "PRIVATE_LAUNCH_CANARY"
    raw = sign_fields(fields)
    response = await client.post("/api/v1/auth/telegram", headers=NULL, json={"init_data": raw})
    assert response.status_code == 200
    cookie = client.cookies.get("__Host-3dps_session")
    csrf = response.json()["csrf_token"]
    rejected = await client.post(
        "/api/v1/auth/logout",
        headers=NULL
        | {"Referer": "https://attacker.example/PRIVATE_REFERER_CANARY", "X-CSRF-Token": csrf},
    )
    assert rejected.status_code == 403
    for secret in (raw, "PRIVATE_LAUNCH_CANARY", "PRIVATE_REFERER_CANARY", cookie, csrf, BOT_TOKEN):
        assert secret not in caplog.text
    assert "init_data" not in caplog.text


async def test_null_origin_login_rejects_ambiguous_content_type(client, app):
    response = await client.post(
        "/api/v1/auth/telegram",
        headers=[
            ("Origin", "null"),
            ("Content-Type", "application/json"),
            ("Content-Type", "text/plain"),
        ],
        content=json.dumps({"init_data": signed_data()}),
    )
    assert response.status_code == 415
    await no_identity(app)


@pytest.mark.parametrize("state", ["expired", "revoked"])
async def test_null_origin_mutation_rejects_expired_or_revoked_session_even_with_csrf(
    client, app, state
):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    session = await opaque_login(client)
    async with app.state.session_factory() as db, db.begin():
        values = (
            {"revoked_at": datetime.now(UTC)}
            if state == "revoked"
            else {
                "created_at": datetime.now(UTC) - timedelta(hours=3),
                "expires_at": datetime.now(UTC) - timedelta(hours=2),
            }
        )
        await db.execute(update(Session).values(**values))
    response = await client.post(
        "/api/v1/requests",
        headers=NULL | {"X-CSRF-Token": session["csrf_token"], "Idempotency-Key": uuid4().hex},
        json={"service_type": "printing"},
    )
    assert response.status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=NULL)).status_code == 401
