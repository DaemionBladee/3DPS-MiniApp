from __future__ import annotations

import asyncio
import os

from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.database import (
    analysis_models,  # noqa: F401 - register M06 metadata
    business_models,  # noqa: F401 -- register M03 metadata
    design_models,  # noqa: F401 - register M05 metadata
    intake_models,  # noqa: F401 - register M04 metadata
)
from app.database.models import Base

target_metadata = Base.metadata


def database_url() -> str:
    value = os.environ.get("DATABASE_URL", "")
    if not value.startswith("postgresql+asyncpg://"):
        raise RuntimeError("Alembic requires an explicitly configured PostgreSQL asyncpg DATABASE_URL")
    return value


def offline() -> None:
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def configure(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def online() -> None:
    engine = create_async_engine(database_url(), hide_parameters=True)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(configure)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    offline()
else:
    asyncio.run(online())
