"""Fail-closed database fixtures: no SQLite substitute and no production targets."""

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.main import create_app
from tests.signing import BOT_TOKEN, ORIGIN, OWNER_ID, SESSION_SECRET

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def guarded_test_database_url() -> str:
    raw = os.environ.get("TEST_DATABASE_URL", "")
    if not raw:
        raise RuntimeError("TEST_DATABASE_URL is required; PostgreSQL tests must not silently skip")
    parsed = make_url(raw)
    if parsed.drivername != "postgresql+asyncpg":
        raise RuntimeError("Tests require postgresql+asyncpg, never SQLite")
    if parsed.host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Tests require an explicitly disposable loopback PostgreSQL target")
    if not (parsed.database or "").startswith("3dps_test"):
        raise RuntimeError("Test database name must begin with 3dps_test")
    return raw


@pytest.fixture(scope="session")
def database_url() -> str:
    return guarded_test_database_url()


@pytest.fixture(scope="session")
def migrated_database(database_url: str) -> str:
    environment = dict(os.environ)
    environment.update(
        DATABASE_URL=database_url,
        BOT_TOKEN=BOT_TOKEN,
        SESSION_SECRET=SESSION_SECRET,
        PUBLIC_BASE_URL=ORIGIN,
        APP_ENV="test",
        OWNER_TELEGRAM_IDS=str(OWNER_ID),
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=environment,
        check=True,
        capture_output=True,
    )
    return database_url


@pytest_asyncio.fixture
async def clean_database(migrated_database: str) -> AsyncIterator[str]:
    engine = create_async_engine(migrated_database, hide_parameters=True)
    async with engine.begin() as connection:
        actual = await connection.scalar(text("SELECT current_database()"))
        if not isinstance(actual, str) or not actual.startswith("3dps_test"):
            raise RuntimeError("Refusing cleanup outside a disposable test database")
        await connection.execute(text("TRUNCATE TABLE sessions, users, auth_rate_limits CASCADE"))
    try:
        yield migrated_database
    finally:
        await engine.dispose()


def make_settings(database_dsn: str, **changes: object) -> Settings:
    values: dict[str, object] = {
        "database_url": database_dsn,
        "bot_token": BOT_TOKEN,
        "session_secret": SESSION_SECRET,
        "public_base_url": ORIGIN,
        "owner_telegram_ids": str(OWNER_ID),
        "app_env": "test",
    }
    values.update(changes)
    return Settings(_env_file=None, **values)


@pytest_asyncio.fixture
async def app(clean_database: str, tmp_path: Path) -> AsyncIterator[FastAPI]:
    application = create_app(make_settings(clean_database, storage_root=tmp_path / "private"))
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url=ORIGIN,
        headers={"Origin": ORIGIN},
    ) as http:
        yield http
