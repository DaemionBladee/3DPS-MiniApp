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
async def test_auth_migration_empty_upgrade_seed_preservation_and_disposable_recovery(
    migration_database: str,
) -> None:
    # Retain the M02 roundtrip against its immutable revision explicitly.
    run_migration(migration_database, "upgrade", "0001_auth_foundation")
    engine = create_async_engine(migration_database, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            tables = set(
                (
                    await connection.scalars(
                        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    )
                ).all()
            )
            assert tables == {"users", "sessions", "auth_rate_limits", "alembic_version"}
            user_id = await connection.scalar(
                text(
                    "INSERT INTO users (telegram_id, display_name) VALUES (123, 'Seeded test user') RETURNING id"
                )
            )
            assert isinstance(user_id, UUID)
            await connection.execute(
                text(
                    "INSERT INTO sessions (user_id, token_hash, init_data_hash, expires_at) "
                    "VALUES (:user_id, :token_hash, :proof_hash, now() + interval '1 hour')"
                ),
                {"user_id": user_id, "token_hash": "a" * 64, "proof_hash": "b" * 64},
            )
        await engine.dispose()
        run_migration(migration_database, "upgrade", "0001_auth_foundation")
        async with engine.begin() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM users")) == 1
            assert await connection.scalar(text("SELECT count(*) FROM sessions")) == 1
            assert await connection.scalar(text("SELECT role FROM users")) == "customer"
            assert await connection.scalar(text("SELECT count(*) FROM alembic_version")) == 1
        await engine.dispose()
        run_migration(migration_database, "downgrade", "base")
        async with engine.begin() as connection:
            tables_after = set(
                (
                    await connection.scalars(
                        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    )
                ).all()
            )
            assert tables_after == {"alembic_version"}
        await engine.dispose()
        run_migration(migration_database, "upgrade", "0001_auth_foundation")
        async with engine.begin() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM users")) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_rejects_duplicate_identity_invalid_roles_and_reused_proofs(
    migration_database: str,
) -> None:
    run_migration(migration_database, "upgrade", "head")
    engine = create_async_engine(migration_database, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            user_id = await connection.scalar(
                text(
                    "INSERT INTO users (telegram_id, display_name) VALUES (321, 'Test') RETURNING id"
                )
            )
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text("INSERT INTO users (telegram_id, display_name) VALUES (321, 'Duplicate')")
                )
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO users (telegram_id, display_name, role) VALUES (322, 'Bad role', 'operator')"
                    )
                )
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO sessions (user_id, token_hash, init_data_hash, expires_at) "
                    "VALUES (:user_id, :token_hash, :proof_hash, now() + interval '1 hour')"
                ),
                {"user_id": user_id, "token_hash": "a" * 64, "proof_hash": "b" * 64},
            )
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO sessions (user_id, token_hash, init_data_hash, expires_at) "
                        "VALUES (:user_id, :token_hash, :proof_hash, now() + interval '1 hour')"
                    ),
                    {"user_id": user_id, "token_hash": "c" * 64, "proof_hash": "b" * 64},
                )
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM users WHERE id=:user_id"), {"user_id": user_id}
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_business_upgrade_preserves_m02_auth_and_disposable_downgrade(
    migration_database: str,
) -> None:
    run_migration(migration_database, "upgrade", "0001_auth_foundation")
    engine = create_async_engine(migration_database, hide_parameters=True)
    try:
        async with engine.begin() as db:
            user_id = await db.scalar(
                text(
                    "INSERT INTO users (telegram_id, display_name) VALUES (4321, 'M02 seed') RETURNING id"
                )
            )
            await db.execute(
                text(
                    "INSERT INTO sessions (user_id, token_hash, init_data_hash, expires_at) VALUES (:user, :token, :proof, now()+interval '1 hour')"
                ),
                {"user": user_id, "token": "d" * 64, "proof": "e" * 64},
            )
        await engine.dispose()
        run_migration(migration_database, "upgrade", "head")
        async with engine.begin() as db:
            assert (
                await db.scalar(text("SELECT version_num FROM alembic_version"))
                == "0002_business_foundation"
            )
            assert await db.scalar(text("SELECT id FROM users")) == user_id
            assert await db.scalar(text("SELECT token_hash FROM sessions")) == "d" * 64
            tables = set(
                (
                    await db.scalars(
                        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    )
                ).all()
            )
            assert tables == {
                "alembic_version",
                "users",
                "sessions",
                "auth_rate_limits",
                "service_projects",
                "service_requests",
                "audit_logs",
                "notification_outbox",
                "idempotency_records",
            }
            assert (
                await db.scalar(
                    text("SELECT count(*) FROM pg_trigger WHERE tgname='audit_logs_immutable'")
                )
                == 1
            )
        await engine.dispose()
        # This fixture owns an empty business schema. Never run destructive
        # downgrade against deployed data or retained audit events.
        run_migration(migration_database, "downgrade", "0001_auth_foundation")
        async with engine.begin() as db:
            assert await db.scalar(text("SELECT id FROM users")) == user_id
            assert await db.scalar(text("SELECT count(*) FROM sessions")) == 1
            assert await db.scalar(text("SELECT to_regclass('public.service_requests')")) is None
            assert (
                await db.scalar(text("SELECT to_regprocedure('reject_audit_mutation()')")) is None
            )
        await engine.dispose()
        run_migration(migration_database, "upgrade", "head")
        async with engine.begin() as db:
            assert await db.scalar(text("SELECT count(*) FROM users")) == 1
            assert await db.scalar(text("SELECT count(*) FROM service_requests")) == 0
    finally:
        await engine.dispose()
