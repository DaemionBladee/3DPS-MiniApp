import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.signing import BOT_TOKEN, ORIGIN, SESSION_SECRET

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest_asyncio.fixture
async def migration_database(database_url: str) -> AsyncIterator[str]:
    """Create/drop only a uniquely named database this fixture itself owns."""
    parsed = make_url(database_url)
    admin_url = parsed.set(drivername="postgresql").render_as_string(hide_password=False)
    name = "3dps_test_migrations_" + uuid4().hex
    admin = await asyncpg.connect(admin_url)
    await admin.execute(f'CREATE DATABASE "{name}"')
    try:
        yield parsed.set(database=name).render_as_string(hide_password=False)
    finally:
        await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await admin.close()


def run_migration(url: str, direction: str, revision: str) -> None:
    environment = dict(os.environ)
    environment.update(
        DATABASE_URL=url,
        APP_ENV="test",
        BOT_TOKEN=BOT_TOKEN,
        SESSION_SECRET=SESSION_SECRET,
        PUBLIC_BASE_URL=ORIGIN,
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", direction, revision],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        check=True,
    )


@pytest.mark.asyncio
async def test_auth_migration_empty_upgrade_seed_preservation_and_disposable_recovery(migration_database: str) -> None:
    # No live/legacy DB exists in M02; seeded head re-upgrade is idempotency
    # evidence, not a claim that a future M03 data migration was exercised.
    run_migration(migration_database, "upgrade", "head")
    engine = create_async_engine(migration_database, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            tables = set(
                (await connection.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))).all()
            )
            assert tables == {"users", "sessions", "auth_rate_limits", "alembic_version"}
            user_id = await connection.scalar(
                text("INSERT INTO users (telegram_id, display_name) VALUES (123, 'Seeded test user') RETURNING id")
            )
            assert isinstance(user_id, UUID)
            await connection.execute(
                text("INSERT INTO sessions (user_id, token_hash, init_data_hash, expires_at) "
                     "VALUES (:user_id, :token_hash, :proof_hash, now() + interval '1 hour')"),
                {"user_id": user_id, "token_hash": "a" * 64, "proof_hash": "b" * 64},
            )
        await engine.dispose()
        run_migration(migration_database, "upgrade", "head")
        async with engine.begin() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM users")) == 1
            assert await connection.scalar(text("SELECT count(*) FROM sessions")) == 1
            assert await connection.scalar(text("SELECT role FROM users")) == "customer"
            assert await connection.scalar(text("SELECT count(*) FROM alembic_version")) == 1
        await engine.dispose()
        run_migration(migration_database, "downgrade", "base")
        async with engine.begin() as connection:
            tables_after = set(
                (await connection.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))).all()
            )
            assert tables_after == {"alembic_version"}
        await engine.dispose()
        run_migration(migration_database, "upgrade", "head")
        async with engine.begin() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM users")) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_rejects_duplicate_identity_invalid_roles_and_reused_proofs(migration_database: str) -> None:
    run_migration(migration_database, "upgrade", "head")
    engine = create_async_engine(migration_database, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            user_id = await connection.scalar(
                text("INSERT INTO users (telegram_id, display_name) VALUES (321, 'Test') RETURNING id")
            )
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(text("INSERT INTO users (telegram_id, display_name) VALUES (321, 'Duplicate')"))
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text("INSERT INTO users (telegram_id, display_name, role) VALUES (322, 'Bad role', 'operator')")
                )
        async with engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO sessions (user_id, token_hash, init_data_hash, expires_at) "
                     "VALUES (:user_id, :token_hash, :proof_hash, now() + interval '1 hour')"),
                {"user_id": user_id, "token_hash": "a" * 64, "proof_hash": "b" * 64},
            )
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text("INSERT INTO sessions (user_id, token_hash, init_data_hash, expires_at) "
                         "VALUES (:user_id, :token_hash, :proof_hash, now() + interval '1 hour')"),
                    {"user_id": user_id, "token_hash": "c" * 64, "proof_hash": "b" * 64},
                )
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(text("DELETE FROM users WHERE id=:user_id"), {"user_id": user_id})
    finally:
        await engine.dispose()
