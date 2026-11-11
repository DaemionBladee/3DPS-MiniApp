from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.intake_schemas import (
    CreateItem,
    FileMetadata,
    IntakeDetail,
    IntakeRequest,
    ItemDetail,
    TaskResponse,
    UpdateItem,
    VersionCommand,
)
from app.core.config import Settings
from app.core.errors import AuthError
from app.database.business_models import ServiceRequest
from app.database.intake_models import ProcessingTask, RequestItem, UploadedFile
from app.database.models import User
from app.intake.catalog import validate_spec
from app.intake.storage import PrivateStorage
from app.services.auth import Principal
from app.services.requests import locked_request, record_event
from app.services.specifications import (
    canonical_hash,
    canonical_spec,
    item_specification,
    refresh_spec,
)
from app.services.transactions import execute_command


async def authorized_request(
    db: AsyncSession,
    user: User,
    request_id: UUID,
    *,
    own_write: bool = False,
    version: int | None = None,
) -> ServiceRequest:
    row = await locked_request(db, user, request_id, version)
    if row.stage_kind != "printing":
        raise AuthError(
            409, "printing_stage_required", "This workflow is available only for printing stages."
        )
    if own_write and row.customer_id != user.id:
        raise AuthError(403, "customer_edit_required", "Only the customer can edit this draft.")
    return row


def require_draft(row: ServiceRequest) -> None:
    if row.status != "draft":
        raise AuthError(409, "draft_required", "Submitted specifications cannot be edited.")


async def detail(db: AsyncSession, row: ServiceRequest, user: User | None = None) -> IntakeDetail:
    rows = (
        await db.scalars(
            select(RequestItem)
            .where(RequestItem.request_id == row.id, RequestItem.active)
            .order_by(RequestItem.created_at, RequestItem.id)
        )
    ).all()
    items: list[ItemDetail] = []
    for item in rows:
        model = await db.get(UploadedFile, item.model_file_id) if item.model_file_id else None
        latest = await db.scalar(
            select(UploadedFile)
            .where(UploadedFile.request_item_id == item.id)
            .order_by(UploadedFile.created_at.desc(), UploadedFile.id.desc())
            .limit(1)
        )
        metadata = FileMetadata.model_validate(model) if model else None
        latest_metadata = FileMetadata.model_validate(latest) if latest else None
        if row.source_design_version_id and (user is None or user.role != "owner"):
            if metadata is not None:
                metadata.download_allowed = False
            if latest_metadata is not None:
                latest_metadata.download_allowed = False
        items.append(
            ItemDetail(
                id=item.id,
                request_revision=item.request_revision,
                specification=item_specification(item),
                model_file=metadata,
                latest_upload=latest_metadata,
            )
        )
    tasks = (
        await db.scalars(
            select(ProcessingTask)
            .where(ProcessingTask.request_id == row.id)
            .order_by(ProcessingTask.created_at, ProcessingTask.id)
            .limit(100)
        )
    ).all()
    customer = await db.get(User, row.customer_id)
    assert customer is not None
    return IntakeDetail(
        request=IntakeRequest.model_validate(row),
        items=items,
        tasks=[TaskResponse.model_validate(task) for task in tasks],
        customer_display_name=customer.display_name,
    )


async def create_item(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    principal: Principal,
    key: str,
    request_id: UUID,
    body: CreateItem,
) -> IntakeDetail:
    async def replay(db: AsyncSession, user: User) -> None:
        await authorized_request(db, user, request_id, own_write=True)

    async def operation(db: AsyncSession, user: User) -> IntakeDetail:
        row = await authorized_request(
            db, user, request_id, own_write=True, version=body.expected_version
        )
        require_draft(row)
        count = await db.scalar(
            select(func.count())
            .select_from(RequestItem)
            .where(RequestItem.request_id == row.id, RequestItem.active)
        )
        if count is not None and count >= settings.request_file_limit:
            raise AuthError(429, "request_item_limit", "This request has reached its model limit.")
        validate_spec(body.specification)
        db.add(
            RequestItem(
                request_id=row.id,
                customer_id=row.customer_id,
                stage_kind="printing",
                request_revision=row.revision + 1,
                **body.specification.model_dump(),
            )
        )
        await refresh_spec(db, row)
        await record_event(db, user, row, "request.item_created", "draft")
        return await detail(db, row)

    return await execute_command(
        factory,
        settings,
        principal,
        f"item.create:{request_id}",
        key,
        body.model_dump(),
        IntakeDetail,
        operation,
        replay,
    )


async def update_item(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    principal: Principal,
    key: str,
    request_id: UUID,
    item_id: UUID,
    body: UpdateItem,
) -> IntakeDetail:
    async def replay(db: AsyncSession, user: User) -> None:
        await authorized_request(db, user, request_id, own_write=True)

    async def operation(db: AsyncSession, user: User) -> IntakeDetail:
        row = await authorized_request(
            db, user, request_id, own_write=True, version=body.expected_version
        )
        require_draft(row)
        item = await db.scalar(
            select(RequestItem)
            .where(RequestItem.id == item_id, RequestItem.request_id == row.id, RequestItem.active)
            .with_for_update()
        )
        if item is None:
            raise AuthError(404, "item_not_found", "This print item could not be found.")
        validate_spec(body.specification)
        if item_specification(item) == body.specification:
            return await detail(db, row)
        for field, value in body.specification.model_dump().items():
            setattr(item, field, value)
        await refresh_spec(db, row)
        await record_event(db, user, row, "request.item_updated", "draft")
        return await detail(db, row)

    return await execute_command(
        factory,
        settings,
        principal,
        f"item.update:{item_id}",
        key,
        body.model_dump(),
        IntakeDetail,
        operation,
        replay,
    )


async def remove_item(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    principal: Principal,
    key: str,
    request_id: UUID,
    item_id: UUID,
    body: VersionCommand,
) -> IntakeDetail:
    async def replay(db: AsyncSession, user: User) -> None:
        await authorized_request(db, user, request_id, own_write=True)

    async def operation(db: AsyncSession, user: User) -> IntakeDetail:
        row = await authorized_request(
            db, user, request_id, own_write=True, version=body.expected_version
        )
        require_draft(row)
        item = await db.scalar(
            select(RequestItem)
            .where(RequestItem.id == item_id, RequestItem.request_id == row.id, RequestItem.active)
            .with_for_update()
        )
        if item is None:
            raise AuthError(404, "item_not_found", "This print item could not be found.")
        files = (
            await db.scalars(
                select(UploadedFile)
                .where(
                    UploadedFile.request_item_id == item.id, UploadedFile.storage_state != "deleted"
                )
                .with_for_update()
            )
        ).all()
        for file in files:
            file.validation_status = "removed"
            file.storage_state = "delete_pending"
        item.active = False
        item.model_file_id = None
        await refresh_spec(db, row)
        await record_event(db, user, row, "request.item_removed", "draft")
        return await detail(db, row)

    return await execute_command(
        factory,
        settings,
        principal,
        f"item.remove:{item_id}",
        key,
        body.model_dump(),
        IntakeDetail,
        operation,
        replay,
    )


async def submit_request(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    principal: Principal,
    key: str,
    request_id: UUID,
    body: VersionCommand,
    storage: PrivateStorage,
) -> IntakeDetail:
    async def replay(db: AsyncSession, user: User) -> None:
        await authorized_request(db, user, request_id, own_write=True)

    async def operation(db: AsyncSession, user: User) -> IntakeDetail:
        row = await authorized_request(
            db, user, request_id, own_write=True, version=body.expected_version
        )
        require_draft(row)
        items = (
            await db.scalars(
                select(RequestItem)
                .where(RequestItem.request_id == row.id, RequestItem.active)
                .order_by(RequestItem.id)
                .with_for_update()
            )
        ).all()
        if not items:
            raise AuthError(422, "items_required", "Add at least one complete print item.")
        for item in items:
            validate_spec(item_specification(item), complete=True)
            file = await db.get(UploadedFile, item.model_file_id) if item.model_file_id else None
            if (
                file is None
                or file.request_id != row.id
                or file.request_item_id != item.id
                or file.owner_id != row.customer_id
                or file.validation_status != "validated"
                or file.storage_state != "ready"
                or file.sha256 is None
                or item.request_revision != row.revision
            ):
                raise AuthError(
                    422, "file_not_cleared", "Each item needs a complete, validated model upload."
                )
            if row.source_design_version_id:
                from app.services.design_files import verify_derived_source

                await verify_derived_source(db, row, file.sha256)
            declared = file.format_details.get("declared_unit")
            declared_key = {
                "micron": "um",
                "millimeter": "mm",
                "centimeter": "cm",
                "inch": "inch",
                "foot": "ft",
                "meter": "m",
            }.get(str(declared))
            if file.format == "3mf" and declared_key != item.unit_key:
                raise AuthError(
                    422, "model_unit_mismatch", "Confirm the units declared by the 3MF model."
                )
            try:
                await storage.verify(file.storage_key, file.size_bytes, file.sha256)
            except OSError:
                raise AuthError(
                    422,
                    "file_unavailable",
                    "A model file is unavailable. Re-upload it before submitting.",
                ) from None
            db.add(
                ProcessingTask(
                    request_id=row.id,
                    uploaded_file_id=file.id,
                    customer_id=row.customer_id,
                    request_revision=row.revision,
                    spec_sha256=row.canonical_spec_sha256,
                    kind="model_analysis",
                    state="pending",
                )
            )
        snapshot = await canonical_spec(db, row)
        if row.spec_schema_version != 2 or canonical_hash(snapshot) != row.canonical_spec_sha256:
            raise AuthError(409, "specification_conflict", "Refresh the draft before submitting.")
        row.status = "submitted"
        row.version += 1
        row.submitted_revision = row.revision
        row.submitted_spec = snapshot
        row.submitted_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        await record_event(db, user, row, "request.submitted", "draft")
        return await detail(db, row)

    return await execute_command(
        factory,
        settings,
        principal,
        f"request.submit:{request_id}",
        key,
        body.model_dump(),
        IntakeDetail,
        operation,
        replay,
    )
