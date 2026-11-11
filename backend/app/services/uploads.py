"""Short DB reservations around streamed private I/O; recover without deleting committed data."""

import asyncio
import hashlib
import json
import logging
import unicodedata
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import unquote_to_bytes
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.intake_schemas import IntakeDetail
from app.core.config import Settings
from app.core.errors import AuthError
from app.database.intake_models import RequestItem, UploadedFile
from app.database.models import User
from app.intake.storage import PrivateStorage, check_stream
from app.intake.validation import InvalidModel, validate_file
from app.services.auth import Principal
from app.services.intake import authorized_request, detail, require_draft
from app.services.requests import record_event
from app.services.specifications import refresh_spec
from app.services.transactions import execute_command, lock_principal, unit_of_work

logger = logging.getLogger("app.intake")
QUOTA_LOCK = 340044004


def file_name(encoded: str) -> str:
    try:
        name = unicodedata.normalize(
            "NFC", unquote_to_bytes(encoded).decode("utf-8", errors="strict")
        )
    except (ValueError, UnicodeError):
        raise AuthError(422, "invalid_file_name", "Use a valid model filename.") from None
    if (
        not 1 <= len(name) <= 200
        or any(
            unicodedata.category(character).startswith("C") or character in "/\\:"
            for character in name
        )
        or name.startswith(".")
    ):
        raise AuthError(422, "invalid_file_name", "Use a plain model filename without paths.")
    if name.rsplit(".", 1)[-1].lower() not in {"stl", "3mf", "obj"}:
        raise AuthError(415, "unsupported_model", "Upload STL, 3MF or OBJ model files.")
    return name


async def cleanup_uploads(
    factory: async_sessionmaker[AsyncSession], storage: PrivateStorage, *, limit: int = 100
) -> int:
    """Expired/incomplete and explicit delete-pending rows stay charged until I/O succeeds.

    Ready committed uploads are never selected. A crash after promotion but before
    DB commit is recoverable because the reservation already names the blob key.
    """
    deleted = 0
    async with factory() as db:
        identities = list(
            (
                await db.scalars(
                    select(UploadedFile.id)
                    .where(
                        or_(
                            (UploadedFile.storage_state == "delete_pending")
                            & (UploadedFile.lease_expires_at <= datetime.now(UTC)),
                            (UploadedFile.storage_state == "receiving")
                            & (UploadedFile.lease_expires_at <= datetime.now(UTC)),
                        )
                    )
                    .order_by(UploadedFile.created_at)
                    .limit(limit)
                )
            ).all()
        )
    for identity in identities:
        async with unit_of_work(factory) as db:
            row = await db.scalar(
                select(UploadedFile)
                .where(UploadedFile.id == identity)
                .with_for_update(skip_locked=True)
            )
            if row is None or not (
                row.storage_state == "delete_pending"
                and row.lease_expires_at <= datetime.now(UTC)
                or row.storage_state == "receiving"
                and row.lease_expires_at <= datetime.now(UTC)
            ):
                continue
            if row.storage_state == "receiving":
                row.validation_status = "rejected"
                row.failure_code = "upload_expired"
                row.storage_state = "delete_pending"
            key, token = row.storage_key, row.lease_token
        try:
            await storage.delete(key)
        except OSError:
            logger.warning("intake.cleanup_deferred file_id=%s", identity)
            continue
        async with unit_of_work(factory) as db:
            row = await db.scalar(
                select(UploadedFile).where(UploadedFile.id == identity).with_for_update()
            )
            if (
                row is not None
                and row.storage_key == key
                and row.lease_token == token
                and row.storage_state == "delete_pending"
                and row.lease_expires_at <= datetime.now(UTC)
            ):
                row.storage_state = "deleted"
                deleted += 1
    return deleted


async def quotas(
    db: AsyncSession, settings: Settings, owner_id: UUID, request_id: UUID, size: int
) -> None:
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": QUOTA_LOCK})
    live = UploadedFile.storage_state != "deleted"
    for scope, conditions, byte_limit, count_limit in [
        (
            "request",
            [live, UploadedFile.request_id == request_id],
            settings.request_storage_bytes,
            settings.request_file_limit,
        ),
        (
            "user",
            [live, UploadedFile.owner_id == owner_id],
            settings.user_storage_bytes,
            settings.user_file_limit,
        ),
        ("total", [live], settings.total_storage_bytes, settings.total_file_limit),
    ]:
        used, count = (
            await db.execute(
                select(func.coalesce(func.sum(UploadedFile.reserved_bytes), 0), func.count()).where(
                    *conditions
                )
            )
        ).one()
        if used + size > byte_limit or count + 1 > count_limit:
            raise AuthError(
                429,
                "storage_quota_exceeded",
                f"The {scope} private storage limit has been reached.",
            )
    receiving = await db.scalar(
        select(func.count())
        .select_from(UploadedFile)
        .where(UploadedFile.storage_state == "receiving")
    )
    if receiving is not None and receiving >= settings.max_inflight_uploads:
        raise AuthError(429, "uploads_busy", "Uploads are busy. Try again shortly.")


async def reserve_upload(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    principal: Principal,
    request_id: UUID,
    item_id: UUID,
    version: int,
    key: str,
    name: str,
    size: int,
    checksum: str,
) -> UploadedFile:
    if size > settings.upload_max_bytes:
        raise AuthError(413, "file_too_large", "This model exceeds the per-file size limit.")
    fingerprint = hashlib.sha256(
        json.dumps(
            {"item": str(item_id), "name": name, "size": size, "sha256": checksum},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    async with unit_of_work(factory) as db:
        user, _ = await lock_principal(db, settings, principal)
        request = await authorized_request(db, user, request_id, own_write=True)
        existing = await db.scalar(
            select(UploadedFile)
            .where(
                UploadedFile.owner_id == user.id,
                UploadedFile.request_id == request_id,
                UploadedFile.upload_key == key,
            )
            .with_for_update()
        )
        if existing is not None:
            if existing.fingerprint != fingerprint:
                raise AuthError(
                    409, "idempotency_conflict", "This upload key belongs to a different file."
                )
            if existing.validation_status == "validated" and existing.storage_state == "ready":
                return existing
            if existing.storage_state != "deleted":
                raise AuthError(
                    409,
                    "upload_in_progress",
                    "The previous upload is pending or recovering. Retry shortly.",
                )
        require_draft(request)
        if request.version != version:
            raise AuthError(409, "stale_version", "Refresh the draft before uploading.")
        item = await db.scalar(
            select(RequestItem)
            .where(
                RequestItem.id == item_id, RequestItem.request_id == request_id, RequestItem.active
            )
            .with_for_update()
        )
        if item is None:
            raise AuthError(404, "item_not_found", "This print item could not be found.")
        if item.model_file_id is not None:
            raise AuthError(
                409, "model_already_uploaded", "Remove the item before replacing its model."
            )
        busy = await db.scalar(
            select(UploadedFile.id).where(
                UploadedFile.request_item_id == item_id, UploadedFile.storage_state == "receiving"
            )
        )
        if busy is not None:
            raise AuthError(
                409, "upload_in_progress", "This item already has an upload in progress."
            )
        await quotas(db, settings, user.id, request_id, size)
        row = existing or UploadedFile(
            owner_id=user.id,
            request_id=request_id,
            request_item_id=item_id,
            upload_key=key,
            fingerprint=fingerprint,
            original_name=name,
            reserved_bytes=size,
            expected_sha256=checksum,
        )
        row.request_revision = request.revision
        row.expected_version = version
        row.storage_key = uuid4().hex
        row.lease_token = uuid4()
        row.lease_expires_at = datetime.now(UTC) + timedelta(seconds=settings.upload_lease_seconds)
        row.validation_status = "pending"
        row.storage_state = "receiving"
        row.size_bytes = 0
        row.sha256 = None
        row.failure_code = None
        db.add(row)
        await db.flush()
        return row


async def abort_upload(
    factory: async_sessionmaker[AsyncSession],
    storage: PrivateStorage,
    identity: UUID,
    token: UUID,
    code: str,
) -> None:
    try:
        async with unit_of_work(factory) as db:
            row = await db.scalar(
                select(UploadedFile).where(UploadedFile.id == identity).with_for_update()
            )
            # Never unlink a blob after an ambiguous commit that actually succeeded.
            if (
                row is None
                or row.storage_state not in {"receiving", "delete_pending"}
                or row.lease_token != token
            ):
                return
            row.storage_state = "delete_pending"
            row.lease_expires_at = datetime.now(UTC)
            row.validation_status = "rejected"
            row.failure_code = code
        await cleanup_uploads(factory, storage)
    except (SQLAlchemyError, OSError):
        # The durable, charged reservation survives an outage for later cleanup.
        logger.warning("intake.upload_cleanup_deferred file_id=%s", identity)


async def receive_upload(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    principal: Principal,
    request_id: UUID,
    item_id: UUID,
    version: int,
    key: str,
    name: str,
    size: int,
    checksum: str,
    chunks: AsyncIterator[bytes],
    storage: PrivateStorage,
) -> IntakeDetail:
    await cleanup_uploads(factory, storage)
    reserved = await reserve_upload(
        factory, settings, principal, request_id, item_id, version, key, name, size, checksum
    )
    replaying = reserved.storage_state == "ready"
    try:
        async with asyncio.timeout(settings.upload_timeout_seconds):
            if replaying:
                await check_stream(chunks, size, checksum)
                result: dict[str, Any] = {}
            else:
                path = await storage.stage(reserved.storage_key, chunks, size, checksum)
        if not replaying:
            result = await validate_file(
                path,
                {
                    "entries": settings.archive_entry_limit,
                    "expanded": settings.archive_expanded_bytes,
                    "entry_bytes": settings.archive_entry_bytes,
                    "ratio": settings.archive_ratio_limit,
                },
                settings.validation_timeout_seconds,
                settings.validation_cpu_seconds,
            )
            if result["format"] != name.rsplit(".", 1)[-1].lower():
                raise AuthError(
                    415, "format_mismatch", "Model content does not match its filename extension."
                )

        async def authorize_replay(db: AsyncSession, user: User) -> None:
            await authorized_request(db, user, request_id, own_write=True)
            file = await db.get(UploadedFile, reserved.id)
            item = await db.get(RequestItem, item_id)
            if (
                file is None
                or file.storage_state != "ready"
                or file.validation_status != "validated"
                or item is None
                or not item.active
                or item.model_file_id != file.id
            ):
                raise AuthError(404, "file_not_found", "This model file could not be found.")

        async def operation(db: AsyncSession, user: User) -> IntakeDetail:
            row = await authorized_request(
                db, user, request_id, own_write=True, version=reserved.expected_version
            )
            require_draft(row)
            file = await db.scalar(
                select(UploadedFile).where(UploadedFile.id == reserved.id).with_for_update()
            )
            item = await db.scalar(
                select(RequestItem)
                .where(RequestItem.id == item_id, RequestItem.active)
                .with_for_update()
            )
            if (
                file is None
                or item is None
                or file.storage_state != "receiving"
                or file.lease_token != reserved.lease_token
                or file.lease_expires_at <= datetime.now(UTC)
                or item.model_file_id is not None
            ):
                raise AuthError(409, "upload_expired", "This upload is no longer current.")
            await storage.promote(file.storage_key)
            file.sha256 = checksum
            file.size_bytes = size
            file.format = str(result["format"])
            file.mime_detected = str(result["mime"])
            file.format_details = dict(result["details"])
            file.validation_status = "validated"
            file.storage_state = "ready"
            file.lease_expires_at = datetime.now(UTC)
            file.request_revision = row.revision + 1
            item.model_file_id = file.id
            await refresh_spec(db, row)
            await record_event(db, user, row, "request.file_attached", "draft")
            return await detail(db, row)

        return await execute_command(
            factory,
            settings,
            principal,
            f"upload.attach:{reserved.id}",
            key,
            {"file": str(reserved.id), "sha256": checksum, "size": size},
            IntakeDetail,
            operation,
            authorize_replay,
        )
    except BaseException as error:
        code = error.code if isinstance(error, (AuthError, InvalidModel)) else "upload_failed"
        if not replaying:
            await asyncio.shield(
                abort_upload(factory, storage, reserved.id, reserved.lease_token, code)
            )
        if isinstance(error, InvalidModel):
            raise AuthError(
                error.status, error.code, "This model failed structural intake validation."
            ) from None
        if isinstance(error, TimeoutError):
            raise AuthError(
                422, "upload_timeout", "The upload or validation timed out. Try a smaller model."
            ) from None
        if isinstance(error, OSError):
            raise AuthError(
                503, "storage_unavailable", "Private storage is unavailable. Retry this upload."
            ) from None
        raise
