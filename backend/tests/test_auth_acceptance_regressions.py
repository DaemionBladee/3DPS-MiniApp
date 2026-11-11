"""M02 review regressions for legitimate recovery and shared auth boundaries."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app.database.models import Session, User
from app.main import create_app
from tests.conftest import make_settings
from tests.signing import CUSTOMER_ID, ORIGIN, fields_for, sign_fields, signed_data


@pytest.mark.asyncio
@pytest.mark.parametrize("previous_state", ["logged_out", "expired", "revoked", "invalid_proof", "replayed_proof"])
async def test_fresh_legitimate_launch_recovers_without_duplicate_or_orphaned_identity(
    client: AsyncClient, app: FastAPI, previous_state: str
) -> None:
    original_proof = signed_data()
    original = await client.post("/api/v1/auth/telegram", json={"init_data": original_proof})
    assert original.status_code == 200
    original_cookie = client.cookies.get("__Host-3dps_session")
    assert original_cookie is not None

    if previous_state == "logged_out":
        logout = await client.post(
            "/api/v1/auth/logout", headers={"X-CSRF-Token": original.json()["csrf_token"]}
        )
        assert logout.status_code == 204
        replay = await client.post("/api/v1/auth/telegram", json={"init_data": original_proof})
        assert replay.status_code == 409
    elif previous_state in {"expired", "revoked"}:
        async with app.state.session_factory() as db:
            if previous_state == "expired":
                await db.execute(
                    update(Session).values(
                        created_at=datetime.now(UTC) - timedelta(hours=3),
                        expires_at=datetime.now(UTC) - timedelta(hours=2),
                    )
                )
            else:
                await db.execute(update(Session).values(revoked_at=datetime.now(UTC)))
            await db.commit()
        # Session invalidation must not erase still-fresh proof replay history.
        replay = await client.post("/api/v1/auth/telegram", json={"init_data": original_proof})
        assert replay.status_code == 409
    elif previous_state == "invalid_proof":
        fields = dict(parse_qsl(signed_data()))
        fields["hash"] = "0" * 64
        failure = await client.post("/api/v1/auth/telegram", json={"init_data": urlencode(fields)})
        assert failure.status_code == 401
    else:
        replay = await client.post("/api/v1/auth/telegram", json={"init_data": original_proof})
        assert replay.status_code == 409

    current = await client.get("/api/v1/auth/me")
    if previous_state in {"invalid_proof", "replayed_proof"}:
        # Invalid replacement attempts must not revoke the original session.
        assert current.status_code == 200
        assert current.json()["csrf_token"] == original.json()["csrf_token"]
        assert client.cookies.get("__Host-3dps_session") == original_cookie
    else:
        assert current.status_code == 401

    fresh = await client.post("/api/v1/auth/telegram", json={"init_data": signed_data()})
    assert fresh.status_code == 200
    assert fresh.json()["user"]["id"] == original.json()["user"]["id"]
    assert fresh.json()["user"]["role"] == "customer"
    assert fresh.json()["csrf_token"] != original.json()["csrf_token"]
    assert client.cookies.get("__Host-3dps_session") != original_cookie
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    old_cookie = await client.get(
        "/api/v1/auth/me", headers={"Cookie": f"__Host-3dps_session={original_cookie}"}
    )
    assert old_cookie.status_code == 401
    async with app.state.session_factory() as db:
        users = (await db.scalars(select(User))).all()
        sessions = (await db.scalars(select(Session))).all()
        assert len(users) == 1
        assert len(sessions) == 2
        assert sum(session.revoked_at is None for session in sessions) == 1
        assert len({session.init_data_hash for session in sessions}) == 2


@pytest.mark.asyncio
async def test_canonical_proof_replay_is_atomic_across_independent_app_instances(clean_database: str) -> None:
    settings = make_settings(clean_database)
    first_app = create_app(settings)
    second_app = create_app(settings)
    fields = fields_for()
    fields["user"] = json.dumps({"id": CUSTOMER_ID, "first_name": "Synthetic Person"})
    original = sign_fields(fields)
    decoded = list(parse_qsl(original))
    uppercase_hash = [(key, value.upper() if key == "hash" else value) for key, value in decoded]
    variants = [
        original,
        urlencode(list(reversed(decoded))),
        original.replace("+", "%20"),
        original.replace("user=", "%75ser="),
        original.replace("%7B", "%7b").replace("%7D", "%7d"),
        urlencode(uppercase_hash),
    ]
    async with first_app.router.lifespan_context(first_app), second_app.router.lifespan_context(second_app):
        async with (
            AsyncClient(transport=ASGITransport(app=first_app), base_url=ORIGIN, headers={"Origin": ORIGIN}) as first,
            AsyncClient(transport=ASGITransport(app=second_app), base_url=ORIGIN, headers={"Origin": ORIGIN}) as second,
        ):
            replies = await asyncio.gather(
                *(
                    (first if index % 2 else second).post("/api/v1/auth/telegram", json={"init_data": raw})
                    for index, raw in enumerate(variants)
                )
            )
        assert [reply.status_code for reply in replies].count(200) == 1
        assert [reply.status_code for reply in replies].count(409) == len(variants) - 1
        async with first_app.state.session_factory() as db:
            assert len((await db.scalars(select(User))).all()) == 1
            assert len((await db.scalars(select(Session))).all()) == 1


@pytest.mark.asyncio
async def test_proxy_hints_never_replace_exact_public_origin_or_trusted_host(clean_database: str) -> None:
    public_origin = "https://miniapp.example:8443"
    application = create_app(make_settings(clean_database, public_base_url=public_origin))
    forwarded = {
        "X-Forwarded-Host": "attacker.example",
        "X-Forwarded-Proto": "http",
        "Forwarded": 'for=203.0.113.8;host="attacker.example";proto=http',
    }
    proof = signed_data()
    async with application.router.lifespan_context(application):
        async with AsyncClient(transport=ASGITransport(app=application), base_url=public_origin) as http:
            for wrong_origin in ["http://miniapp.example:8443", "https://miniapp.example"]:
                rejected = await http.post(
                    "/api/v1/auth/telegram",
                    json={"init_data": proof},
                    headers={"Origin": wrong_origin, "X-Forwarded-Host": "miniapp.example:8443"},
                )
                assert rejected.status_code == 403
            forbidden_host = await http.post(
                "/api/v1/auth/telegram",
                json={"init_data": proof},
                headers={"Origin": public_origin, "Host": "attacker.example", "X-Forwarded-Host": "miniapp.example:8443"},
            )
            assert forbidden_host.status_code == 400
            valid = await http.post(
                "/api/v1/auth/telegram",
                json={"init_data": proof},
                headers={"Origin": public_origin, **forwarded},
            )
            assert valid.status_code == 200
            assert (await http.get("/api/v1/auth/me")).status_code == 200
