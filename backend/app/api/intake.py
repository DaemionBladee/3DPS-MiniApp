import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, cast
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.auth import FactoryDependency, PrincipalDependency, SettingsDependency
from app.api.business import BusinessPrincipalDependency, CommandKey
from app.api.business_schemas import DraftPatch
from app.api.intake_schemas import (
    AnalysisStatus,
    CreateItem,
    FileMetadata,
    IntakeDetail,
    PrintingOptions,
    TaskResponse,
    UpdateItem,
    VersionCommand,
)
from app.core.errors import AuthError
from app.database.intake_models import ProcessingTask, UploadedFile
from app.intake.catalog import options
from app.intake.rate_limits import consume_rate
from app.intake.storage import CHUNK_BYTES, PrivateStorage
from app.services.intake import (
    authorized_request,
    create_item,
    detail,
    remove_item,
    submit_request,
    update_item,
)
from app.services.requests import update_draft
from app.services.uploads import cleanup_uploads, file_name, receive_upload

router = APIRouter(prefix="/api/v1", tags=["printing-intake"])


def get_storage(request: Request) -> PrivateStorage:
    return cast(PrivateStorage, request.app.state.storage)


StorageDependency = Annotated[PrivateStorage, Depends(get_storage)]


@router.get("/catalog/printing-options", response_model=PrintingOptions)
async def catalog(principal: PrincipalDependency, settings: SettingsDependency) -> PrintingOptions:
    return options(settings)


@router.get("/requests/{request_id}/intake", response_model=IntakeDetail)
async def retrieve(
    request_id: UUID, principal: PrincipalDependency, factory: FactoryDependency
) -> IntakeDetail:
    async with factory() as db:
        row = await authorized_request(db, principal.user, request_id)
        return await detail(db, row)


@router.patch("/requests/{request_id}/intake", response_model=IntakeDetail)
async def preferences(
    request_id: UUID,
    body: DraftPatch,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
) -> IntakeDetail:
    await update_draft(factory, settings, principal, key, request_id, body)
    async with factory() as db:
        row = await authorized_request(db, principal.user, request_id)
        return await detail(db, row)


@router.post("/requests/{request_id}/items", response_model=IntakeDetail, status_code=201)
async def add_item(
    request_id: UUID,
    body: CreateItem,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
) -> IntakeDetail:
    return await create_item(factory, settings, principal, key, request_id, body)


@router.patch("/requests/{request_id}/items/{item_id}", response_model=IntakeDetail)
async def patch_item(
    request_id: UUID,
    item_id: UUID,
    body: UpdateItem,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
) -> IntakeDetail:
    return await update_item(factory, settings, principal, key, request_id, item_id, body)


@router.delete("/requests/{request_id}/items/{item_id}", response_model=IntakeDetail)
async def delete_item(
    request_id: UUID,
    item_id: UUID,
    body: VersionCommand,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
    storage: StorageDependency,
) -> IntakeDetail:
    result = await remove_item(factory, settings, principal, key, request_id, item_id, body)
    await cleanup_uploads(factory, storage)
    return result


@router.post(
    "/requests/{request_id}/files",
    response_model=IntakeDetail,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
async def upload(
    request_id: UUID,
    request: Request,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
    storage: StorageDependency,
    item_id: Annotated[UUID, Query()],
    expected_version: Annotated[int, Query(ge=1)],
    encoded_name: Annotated[str, Header(alias="X-File-Name", min_length=1, max_length=2400)],
    size: Annotated[int, Header(alias="X-File-Size", gt=0)],
    checksum: Annotated[str, Header(alias="X-Content-SHA256", pattern="^[0-9a-f]{64}$")],
) -> IntakeDetail:
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/octet-stream"
    ):
        raise AuthError(
            415, "binary_upload_required", "Upload raw model bytes as application/octet-stream."
        )
    await consume_rate(factory, settings, principal, "upload")
    return await receive_upload(
        factory,
        settings,
        principal,
        request_id,
        item_id,
        expected_version,
        key,
        file_name(encoded_name),
        size,
        checksum,
        request.stream(),
        storage,
    )


@router.get("/files/{file_id}", response_model=FileMetadata)
async def metadata(
    file_id: UUID,
    principal: PrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
) -> FileMetadata:
    await consume_rate(factory, settings, principal, "file_read")
    async with factory() as db:
        file = await db.get(UploadedFile, file_id)
        if file is None:
            raise AuthError(404, "file_not_found", "This model file could not be found.")
        await authorized_request(db, principal.user, file.request_id)
        return FileMetadata.model_validate(file)


@router.get("/files/{file_id}/download", response_class=StreamingResponse)
async def download(
    file_id: UUID,
    principal: PrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
    storage: StorageDependency,
) -> StreamingResponse:
    await consume_rate(factory, settings, principal, "file_read")
    async with factory() as db:
        file = await db.get(UploadedFile, file_id)
        if file is None:
            raise AuthError(404, "file_not_found", "This model file could not be found.")
        await authorized_request(db, principal.user, file.request_id)
        if (
            file.validation_status != "validated"
            or file.storage_state != "ready"
            or file.sha256 is None
        ):
            raise AuthError(
                409, "file_not_cleared", "This model has not cleared structural intake validation."
            )
        try:
            handle = await storage.open_verified(file.storage_key, file.size_bytes, file.sha256)
        except OSError:
            raise AuthError(
                404, "file_unavailable", "The private model file is unavailable."
            ) from None
        name, size = file.original_name, file.size_bytes

    async def stream() -> AsyncIterator[bytes]:
        try:
            while block := await asyncio.to_thread(handle.read, CHUNK_BYTES):
                yield block
        finally:
            await asyncio.to_thread(handle.close)

    return StreamingResponse(
        stream(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=model; filename*=UTF-8''{quote(name, safe='')}",
            "Content-Length": str(size),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )


@router.post("/requests/{request_id}/submit", response_model=IntakeDetail)
async def submit(
    request_id: UUID,
    body: VersionCommand,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
    storage: StorageDependency,
) -> IntakeDetail:
    return await submit_request(factory, settings, principal, key, request_id, body, storage)


@router.get("/requests/{request_id}/analysis", response_model=AnalysisStatus)
async def analysis(
    request_id: UUID, principal: PrincipalDependency, factory: FactoryDependency
) -> AnalysisStatus:
    async with factory() as db:
        row = await authorized_request(db, principal.user, request_id)
        tasks = (
            await db.scalars(
                select(ProcessingTask)
                .where(ProcessingTask.request_id == row.id)
                .order_by(ProcessingTask.created_at, ProcessingTask.id)
                .limit(100)
            )
        ).all()
        return AnalysisStatus(
            state="pending"
            if row.status == "submitted"
            else "superseded"
            if tasks
            else "not_submitted",
            tasks=[TaskResponse.model_validate(task) for task in tasks],
        )
