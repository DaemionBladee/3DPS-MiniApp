"""Atomic commands with cross-process idempotency and fresh session checks."""

import hashlib
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AuthError
from app.database.business_models import IdempotencyRecord
from app.database.models import Session, User
from app.services.auth import Principal, configured_role


@asynccontextmanager
async def unit_of_work(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with factory() as database, database.begin():
        yield database
        await database.flush()


async def execute_command[Result: BaseModel](
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    principal: Principal,
    action: str,
    key: str,
    payload: dict[str, Any],
    result_type: type[Result],
    operation: Callable[[AsyncSession, User], Awaitable[Result]],
    authorize_replay: Callable[[AsyncSession, User], Awaitable[None]] | None = None,
) -> Result:
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    lock = int.from_bytes(
        hashlib.sha256(f"{principal.user.id}:{action}:{key}".encode()).digest()[:8], signed=True
    )
    async with unit_of_work(factory) as database:
        await database.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
        # Serialize business authorization against logout/revocation. A session
        # check done before opening this command's transaction is not enough.
        # Match authentication's user -> session lock order to avoid deadlocks
        # when a fresh Telegram login rotates the existing cookie concurrently.
        user = await database.scalar(
            # Non-key changes (disable/role/login) still serialize, while
            # other commands can validate incoming user foreign keys. An
            # exclusive user lock can deadlock Owner vs Customer mutations.
            select(User).where(User.id == principal.user.id).with_for_update(key_share=True)
        )
        session = await database.scalar(
            select(Session).where(Session.id == principal.session.id).with_for_update()
        )
        if (
            session is None
            or user is None
            or session.user_id != user.id
            or not user.active
            or session.revoked_at is not None
            or session.expires_at <= datetime.now(UTC)
        ):
            raise AuthError(
                401, "session_invalid", "Your session has expired. Open the Mini App again."
            )
        user.role = configured_role(user.telegram_id, settings)
        previous = await database.get(IdempotencyRecord, (user.id, action, key))
        if previous:
            # Cached responses are private data too. Resource commands must
            # recheck current access without reapplying their version guard.
            if authorize_replay is not None:
                await authorize_replay(database, user)
            if previous.request_hash != fingerprint:
                raise AuthError(
                    409,
                    "idempotency_conflict",
                    "This command key was already used with different information.",
                )
            return result_type.model_validate(previous.response_json)
        result = await operation(database, user)
        database.add(
            IdempotencyRecord(
                actor_user_id=user.id,
                action=action,
                key=key,
                request_hash=fingerprint,
                response_json=result.model_dump(mode="json"),
            )
        )
        return result
