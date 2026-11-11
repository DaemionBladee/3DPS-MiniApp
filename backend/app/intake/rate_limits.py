import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AuthError
from app.database.models import AuthRateLimit
from app.services.auth import Principal


async def consume_rate(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    principal: Principal,
    scope: Literal["intake", "upload", "file_read"],
) -> None:
    # Reuse the existing atomic counter primitive with a separate namespace;
    # login buckets, identity verification and limits are unchanged.
    key = hmac.new(
        settings.session_secret.get_secret_value().encode(),
        f"m04:{scope}:{principal.user.id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.intake_rate_window_seconds)
    limit = settings.upload_rate_limit if scope == "upload" else settings.intake_rate_limit
    statement = insert(AuthRateLimit).values(key_hash=key, window_start=now, attempts=1)
    upsert = statement.on_conflict_do_update(
        index_elements=[AuthRateLimit.key_hash],
        set_={
            "window_start": case(
                (AuthRateLimit.window_start <= cutoff, now), else_=AuthRateLimit.window_start
            ),
            "attempts": case(
                (AuthRateLimit.window_start <= cutoff, 1), else_=AuthRateLimit.attempts + 1
            ),
        },
    ).returning(AuthRateLimit.attempts)
    async with factory() as database, database.begin():
        count = (await database.execute(upsert)).scalar_one()
    if count > limit:
        raise AuthError(
            429, "intake_rate_limited", "Too many intake requests. Wait before trying again."
        )
