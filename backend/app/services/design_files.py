"""File authorization distinguishes customer references, review proofs and unreleased source."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.design_schemas import DesignDetail
from app.api.intake_schemas import VersionCommand
from app.core.config import Settings
from app.core.errors import AuthError
from app.database.business_models import ServiceRequest
from app.database.design_models import DesignProject, DesignVersion
from app.database.intake_models import UploadedFile
from app.database.models import User
from app.intake.storage import PrivateStorage
from app.services.auth import Principal
from app.services.design import (
    approved_manufacturing,
    customer_only,
    ensure_no_print,
    owner_only,
    project_for_request,
)
from app.services.requests import locked_request


async def upload_request(
    db: AsyncSession,
    user: User,
    request_id: UUID,
    version: int | None,
    purpose: str,
    checksum: str | None = None,
    *,
    replay: bool = False,
) -> ServiceRequest:
    row = await locked_request(db, user, request_id, version)
    if purpose == "model":
        if row.stage_kind != "printing":
            raise AuthError(
                409, "printing_stage_required", "This model needs a printing-stage request."
            )
        if row.customer_id != user.id and not (
            user.role == "owner" and row.source_design_version_id
        ):
            raise AuthError(403, "customer_edit_required", "Only the customer can edit this draft.")
        if row.source_design_version_id:
            await verify_derived_source(db, row, checksum)
        if not replay and row.status != "draft":
            raise AuthError(409, "draft_required", "This request is no longer a draft.")
        return row
    if row.stage_kind != "design":
        raise AuthError(
            409, "design_stage_required", "Design files require a design-stage request."
        )
    project = await project_for_request(db, row)
    if purpose == "design_reference":
        customer_only(row, user)
        if not replay and row.status != "draft":
            raise AuthError(409, "draft_required", "Submitted design references are frozen.")
    elif purpose in {"design_proof", "design_manufacturing"}:
        owner_only(user)
        if not replay:
            await ensure_no_print(db, project)
            if (
                row.status != "submitted"
                or project.state not in {"designing", "customer_review", "approved"}
                or project.approved_scope_id is None
                or project.fixture_scope_id != project.approved_scope_id
            ):
                raise AuthError(
                    409,
                    "design_work_not_authorized",
                    "Activate the agreed scope's explicit simulation-paid fixture first.",
                )
    else:
        raise AuthError(415, "unsupported_file_purpose", "This file purpose is unsupported.")
    return row


async def verify_derived_source(
    db: AsyncSession, row: ServiceRequest, checksum: str | None
) -> None:
    version = await db.get(DesignVersion, row.source_design_version_id)
    project = await db.get(DesignProject, version.design_project_id) if version else None
    if project is None:
        raise AuthError(409, "source_design_unavailable", "The source design is unavailable.")
    approved, file = await approved_manufacturing(db, project)
    if (
        approved.id != row.source_design_version_id
        or file.owner_id != row.customer_id
        or approved.service_project_id != row.service_project_id
        or checksum != file.sha256
        or file.validation_status != "validated"
        or file.storage_state != "ready"
    ):
        raise AuthError(
            422,
            "source_design_mismatch",
            "Use the exact approved manufacturing model for this printing stage.",
        )


async def file_access(
    db: AsyncSession, user: User, file: UploadedFile, *, download: bool = False
) -> bool:
    row = await locked_request(db, user, file.request_id, None)
    allowed = True
    if file.purpose == "design_manufacturing":
        allowed = user.role == "owner"
        if not allowed:
            raise AuthError(404, "file_not_found", "This design source file is not released.")
    elif file.purpose == "design_proof" and user.role != "owner":
        published = await db.scalar(
            select(DesignVersion.id).where(DesignVersion.preview_file_id == file.id)
        )
        if published is None:
            raise AuthError(404, "file_not_found", "This design proof is not published.")
    elif file.purpose == "model" and row.source_design_version_id and user.role != "owner":
        allowed = False
        if download:
            raise AuthError(
                403,
                "digital_release_unavailable",
                "Manufacturing files are private; M05 does not release digital deliverables.",
            )
    return allowed


async def attach_approved_model(
    factory: "async_sessionmaker[AsyncSession]",
    settings: "Settings",
    principal: "Principal",
    identity: UUID,
    key: str,
    body: "VersionCommand",
    storage: "PrivateStorage",
) -> "DesignDetail":
    import asyncio
    from collections.abc import AsyncIterator

    from app.intake.storage import CHUNK_BYTES
    from app.services.design import detail, linked_print, locked_design
    from app.services.uploads import receive_upload

    # The Owner explicitly attaches an approved manufacturing model. Bytes pass
    # through the same reserved/checksummed M04 upload workflow; no source release.
    owner_only(principal.user)
    async with factory() as db:
        project, row = await locked_design(db, principal.user, identity)
        _, file = await approved_manufacturing(db, project)
        printing = await linked_print(db, project)
        if printing is None:
            raise AuthError(
                409, "printing_draft_required", "Create the linked printing draft first."
            )
        from app.database.intake_models import RequestItem

        item = await db.scalar(
            select(RequestItem)
            .where(RequestItem.request_id == printing.id, RequestItem.active)
            .order_by(RequestItem.created_at)
            .limit(1)
        )
        if item is None:
            raise AuthError(409, "item_required", "Create a print item before attaching the model.")
        handle = await storage.open_verified(file.storage_key, file.size_bytes, file.sha256 or "")
        request_id, item_id = printing.id, item.id
        name, size, checksum = file.original_name, file.size_bytes, file.sha256 or ""

    async def chunks() -> AsyncIterator[bytes]:
        try:
            while block := await asyncio.to_thread(handle.read, CHUNK_BYTES):
                yield block
        finally:
            await asyncio.to_thread(handle.close)

    try:
        await receive_upload(
            factory,
            settings,
            principal,
            request_id,
            item_id,
            body.expected_version,
            key,
            name,
            size,
            checksum,
            chunks(),
            storage,
        )
    finally:
        await asyncio.to_thread(handle.close)
    async with factory() as db:
        project, row = await locked_design(db, principal.user, identity)
        return await detail(db, project, row, principal.user)
