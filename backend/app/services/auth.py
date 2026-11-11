from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import case, delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AuthError
from app.core.telegram import VerifiedTelegramUser
from app.database.models import AuthRateLimit, Role, Session, User


@dataclass(frozen=True)
class Principal:
    user: User
    session: Session
    token: str


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def csrf_token(token: str, settings: Settings) -> str:
    return hmac.new(
        settings.session_secret.get_secret_value().encode("utf-8"),
        f"csrf:{token}".encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def configured_role(telegram_id: int, settings: Settings) -> Role:
    return "owner" if telegram_id in settings.owner_ids else "customer"


async def consume_auth_rate_limit(
    factory: async_sessionmaker[AsyncSession], settings: Settings, peer: str, *, login: bool
) -> None:
    """Atomic PostgreSQL counter; rejected proofs count across all app workers."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.auth_rate_window_seconds)
    scope = "login" if login else "session"
    key = hmac.new(
        settings.session_secret.get_secret_value().encode("utf-8"),
        f"rate:{scope}:{peer}".encode(),
        hashlib.sha256,
    ).hexdigest()
    async with factory() as database, database.begin():
        # Each request deletes at most 100 stale peer counters. No raw IPs persist.
        stale = select(AuthRateLimit.key_hash).where(
            AuthRateLimit.window_start < now - timedelta(seconds=2 * settings.auth_rate_window_seconds)
        ).limit(100).with_for_update(skip_locked=True)
        await database.execute(delete(AuthRateLimit).where(AuthRateLimit.key_hash.in_(stale)))
        statement = insert(AuthRateLimit).values(key_hash=key, window_start=now, attempts=1)
        upsert = statement.on_conflict_do_update(
            index_elements=[AuthRateLimit.key_hash],
            set_={
                "window_start": case((AuthRateLimit.window_start <= cutoff, now), else_=AuthRateLimit.window_start),
                "attempts": case((AuthRateLimit.window_start <= cutoff, 1), else_=AuthRateLimit.attempts + 1),
            },
        ).returning(AuthRateLimit.attempts)
        attempts = (await database.execute(upsert)).scalar_one()
    if attempts > settings.auth_rate_limit * (1 if login else 6):
        raise AuthError(429, "rate_limited", "Too many authentication requests. Please try again shortly.")


async def establish_session(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    verified: VerifiedTelegramUser,
    previous_token: str | None,
) -> tuple[User, str]:
    now = datetime.now(UTC)
    token = secrets.token_urlsafe(32)
    try:
        async with factory() as database, database.begin():
            statement = insert(User).values(
                telegram_id=verified.telegram_id,
                display_name=verified.display_name,
                username=verified.username,
                role=configured_role(verified.telegram_id, settings),
                last_seen_at=now,
            )
            upsert = statement.on_conflict_do_update(
                index_elements=[User.telegram_id],
                set_={
                    "display_name": verified.display_name,
                    "username": verified.username,
                    "role": configured_role(verified.telegram_id, settings),
                    "last_seen_at": now,
                },
            ).returning(User)
            user = (await database.execute(upsert)).scalar_one()
            if not user.active:
                raise AuthError(403, "account_disabled", "This account is not available.")
            if previous_token:
                await database.execute(
                    update(Session).where(
                        Session.token_hash == hash_token(previous_token), Session.revoked_at.is_(None)
                    ).values(revoked_at=now)
                )
            database.add(Session(
                user_id=user.id,
                token_hash=hash_token(token),
                init_data_hash=verified.proof_hash,
                created_at=now,
                expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
            ))
            await database.flush()
    except IntegrityError:
        # The same signed launch proof is usable once, including after logout.
        # Rollback also undoes user/previous-session changes on a racing replay.
        raise AuthError(409, "telegram_proof_replayed", "Reopen the Mini App to start a fresh session.") from None
    return user, token


async def resolve_session(
    factory: async_sessionmaker[AsyncSession], settings: Settings, token: str | None
) -> Principal:
    if not token or len(token) != 43 or not all(character.isascii() and (character.isalnum() or character in "-_") for character in token):
        raise AuthError(401, "authentication_required", "Open the Mini App in Telegram to sign in.")
    async with factory() as database, database.begin():
        result = (await database.execute(
            select(Session, User).join(User, Session.user_id == User.id).where(Session.token_hash == hash_token(token))
        )).one_or_none()
        if result is None:
            raise AuthError(401, "session_invalid", "Your session has expired. Open the Mini App again.")
        session, user = result
        if session.revoked_at is not None or session.expires_at <= datetime.now(UTC) or not user.active:
            raise AuthError(401, "session_invalid", "Your session has expired. Open the Mini App again.")
        # Configuration remains authoritative even if the DB role was edited or
        # an owner allowlist entry was removed while a session was still active.
        user.role = configured_role(user.telegram_id, settings)
    return Principal(user=user, session=session, token=token)


async def revoke_session(factory: async_sessionmaker[AsyncSession], session_id: UUID) -> None:
    async with factory() as database, database.begin():
        await database.execute(
            update(Session).where(Session.id == session_id, Session.revoked_at.is_(None)).values(revoked_at=datetime.now(UTC))
        )
