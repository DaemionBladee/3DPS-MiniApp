import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.main import create_app
from tests.conftest import make_settings
from tests.signing import ORIGIN


@pytest.mark.asyncio
async def test_failed_login_rate_limit_is_shared_across_app_instances(clean_database: str) -> None:
    settings = make_settings(clean_database, auth_rate_limit=2)
    first_app = create_app(settings)
    second_app = create_app(settings)
    async with first_app.router.lifespan_context(first_app), second_app.router.lifespan_context(second_app):
        async with (
            AsyncClient(transport=ASGITransport(app=first_app), base_url=ORIGIN, headers={"Origin": ORIGIN}) as first,
            AsyncClient(transport=ASGITransport(app=second_app), base_url=ORIGIN, headers={"Origin": ORIGIN}) as second,
        ):
            assert (await first.post("/api/v1/auth/telegram", json={"init_data": "bad-one"})).status_code == 401
            assert (await first.post("/api/v1/auth/telegram", json={"init_data": "bad-two"})).status_code == 401
            limited = await second.post(
                "/api/v1/auth/telegram",
                json={"init_data": "bad-three"},
                headers={"X-Forwarded-For": "203.0.113.5"},
            )
            assert limited.status_code == 429
            assert int(limited.headers["retry-after"]) > 0
            assert "__Host-3dps_session" not in second.cookies


@pytest.mark.asyncio
async def test_concurrent_failed_logins_cannot_race_the_attempt_limit(clean_database: str) -> None:
    application = create_app(make_settings(clean_database, auth_rate_limit=2))
    async with application.router.lifespan_context(application):
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url=ORIGIN, headers={"Origin": ORIGIN}
        ) as client:
            responses = await asyncio.gather(
                *(client.post("/api/v1/auth/telegram", json={"init_data": f"bad-{number}"}) for number in range(6))
            )
    statuses = [response.status_code for response in responses]
    assert statuses.count(401) == 2
    assert statuses.count(429) == 4


@pytest.mark.asyncio
async def test_expired_rate_window_allows_new_attempt_without_storing_ip(clean_database: str) -> None:
    application = create_app(make_settings(clean_database, auth_rate_limit=1))
    async with application.router.lifespan_context(application):
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url=ORIGIN, headers={"Origin": ORIGIN}
        ) as client:
            assert (await client.post("/api/v1/auth/telegram", json={"init_data": "bad-one"})).status_code == 401
            assert (await client.post("/api/v1/auth/telegram", json={"init_data": "bad-two"})).status_code == 429
            engine = create_async_engine(clean_database, hide_parameters=True)
            try:
                async with engine.begin() as connection:
                    key = await connection.scalar(text("SELECT key_hash FROM auth_rate_limits LIMIT 1"))
                    assert isinstance(key, str) and len(key) == 64
                    assert "127.0.0.1" not in key
                    await connection.execute(
                        text("UPDATE auth_rate_limits SET window_start = now() - interval '2 hours'")
                    )
            finally:
                await engine.dispose()
            assert (await client.post("/api/v1/auth/telegram", json={"init_data": "bad-three"})).status_code == 401
