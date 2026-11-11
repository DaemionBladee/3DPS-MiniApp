from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request
from sqlalchemy import select

from app.api.auth import FactoryDependency, PrincipalDependency, SettingsDependency
from app.api.business import BusinessPrincipalDependency, CommandKey, PageLimit, PageOffset
from app.api.design_schemas import (
    BriefCommand,
    ConvertDesign,
    DesignDetail,
    DesignPage,
    PublishProof,
    RemoveReference,
    ReviewProof,
    ScopeAgreement,
    ScopeCommand,
    SimulationFixture,
)
from app.api.intake import StorageDependency
from app.api.intake_schemas import VersionCommand
from app.core.errors import AuthError
from app.database.business_models import ServiceRequest
from app.database.design_models import DesignProject
from app.intake.rate_limits import consume_rate
from app.services.design import (
    design_command,
    detail,
    initialize_design,
    locked_design,
    owner_only,
)
from app.services.design_files import attach_approved_model
from app.services.requests import locked_request
from app.services.uploads import file_name, receive_upload

router = APIRouter(prefix="/api/v1", tags=["design-intake"])


@router.get("/requests/{request_id}/design", response_model=DesignDetail)
async def request_design(
    request_id: UUID, principal: PrincipalDependency, factory: FactoryDependency
) -> DesignDetail:
    # Legacy M03/M04 drafts get their empty design-project record lazily on the
    # first explicit initialize command, never as a side effect of a read.
    async with factory() as db:
        row = await locked_request(db, principal.user, request_id, None)
        project = await db.scalar(select(DesignProject).where(DesignProject.request_id == row.id))
        if project is None:
            raise AuthError(
                409,
                "design_initialization_required",
                "Initialize this earlier design draft before editing.",
            )
        return await detail(db, project, row, principal.user)


@router.post("/requests/{request_id}/design", response_model=DesignDetail)
async def initialize(
    request_id: UUID,
    body: VersionCommand,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
) -> DesignDetail:

    return await initialize_design(factory, settings, principal, request_id, key, body)


@router.get("/design-projects", response_model=DesignPage)
async def projects(
    principal: PrincipalDependency,
    factory: FactoryDependency,
    limit: PageLimit = 20,
    offset: PageOffset = 0,
) -> DesignPage:
    statement = select(DesignProject).join(
        ServiceRequest, ServiceRequest.id == DesignProject.request_id
    )
    if principal.user.role != "owner":
        statement = statement.where(DesignProject.customer_id == principal.user.id)
    async with factory() as db:
        rows = (
            await db.scalars(
                statement.order_by(DesignProject.created_at, DesignProject.id)
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
        items = []
        for project in rows[:limit]:
            row = await db.get(ServiceRequest, project.request_id)
            assert row is not None
            items.append(await detail(db, project, row, principal.user))
        return DesignPage(
            items=items,
            next_offset=offset + limit if len(rows) > limit and offset + limit <= 10000 else None,
        )


@router.get("/design-projects/{identity}", response_model=DesignDetail)
async def get_design(
    identity: UUID, principal: PrincipalDependency, factory: FactoryDependency
) -> DesignDetail:
    async with factory() as db:
        project, row = await locked_design(db, principal.user, identity)
        return await detail(db, project, row, principal.user)


@router.patch("/design-projects/{identity}/brief", response_model=DesignDetail)
async def brief(
    identity: UUID,
    body: BriefCommand,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
    storage: StorageDependency,
) -> DesignDetail:
    return await design_command(factory, settings, principal, identity, key, "brief", body, storage)


@router.post("/design-projects/{identity}/submit", response_model=DesignDetail)
async def submit(
    identity: UUID,
    body: VersionCommand,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
    storage: StorageDependency,
) -> DesignDetail:
    return await design_command(
        factory, settings, principal, identity, key, "submit", body, storage
    )


@router.post("/owner/design-projects/{identity}/scopes", response_model=DesignDetail)
async def scope(
    identity: UUID,
    body: ScopeCommand,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
    storage: StorageDependency,
) -> DesignDetail:
    return await design_command(factory, settings, principal, identity, key, "scope", body, storage)


@router.post("/design-projects/{identity}/scope-agreements", response_model=DesignDetail)
async def agree(
    identity: UUID,
    body: ScopeAgreement,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
    storage: StorageDependency,
) -> DesignDetail:
    return await design_command(factory, settings, principal, identity, key, "agree", body, storage)


@router.post("/owner/design-projects/{identity}/simulation-fixture", response_model=DesignDetail)
async def fixture(
    identity: UUID,
    body: SimulationFixture,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
    storage: StorageDependency,
) -> DesignDetail:
    return await design_command(
        factory, settings, principal, identity, key, "fixture", body, storage
    )


@router.post("/owner/design-projects/{identity}/versions", response_model=DesignDetail)
async def publish(
    identity: UUID,
    body: PublishProof,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
    storage: StorageDependency,
) -> DesignDetail:
    return await design_command(
        factory, settings, principal, identity, key, "publish", body, storage
    )


@router.post("/design-projects/{identity}/reviews", response_model=DesignDetail)
async def review(
    identity: UUID,
    body: ReviewProof,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
    storage: StorageDependency,
) -> DesignDetail:
    return await design_command(
        factory, settings, principal, identity, key, "review", body, storage
    )


@router.post("/owner/design-projects/{identity}/create-print-request", response_model=DesignDetail)
async def convert(
    identity: UUID,
    body: ConvertDesign,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
    storage: StorageDependency,
) -> DesignDetail:
    return await design_command(
        factory, settings, principal, identity, key, "convert", body, storage
    )


@router.post(
    "/requests/{request_id}/design/files",
    response_model=DesignDetail,
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
async def upload_design(
    request_id: UUID,
    request: Request,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
    storage: StorageDependency,
    expected_version: Annotated[int, Query(ge=1)],
    purpose: Literal["design_reference", "design_proof", "design_manufacturing"],
    encoded_name: Annotated[str, Header(alias="X-File-Name", min_length=1, max_length=2400)],
    size: Annotated[int, Header(alias="X-File-Size", gt=0)],
    checksum: Annotated[str, Header(alias="X-Content-SHA256", pattern="^[0-9a-f]{64}$")],
) -> DesignDetail:
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/octet-stream"
    ):
        raise AuthError(415, "binary_upload_required", "Upload raw file bytes.")
    await consume_rate(factory, settings, principal, "upload")
    return cast(
        DesignDetail,
        await receive_upload(
            factory,
            settings,
            principal,
            request_id,
            None,
            expected_version,
            key,
            file_name(encoded_name, purpose),
            size,
            checksum,
            request.stream(),
            storage,
            purpose,
        ),
    )


@router.post("/design-projects/{identity}/remove-reference", response_model=DesignDetail)
async def remove_reference(
    identity: UUID,
    body: RemoveReference,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
    storage: StorageDependency,
) -> DesignDetail:
    from app.services.uploads import cleanup_uploads

    result = await design_command(
        factory, settings, principal, identity, key, "remove-reference", body, storage
    )
    await cleanup_uploads(factory, storage)
    return result


@router.post("/owner/design-projects/{identity}/attach-print-model", response_model=DesignDetail)
async def attach(
    identity: UUID,
    body: VersionCommand,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
    storage: StorageDependency,
) -> DesignDetail:
    owner_only(principal.user)
    await consume_rate(factory, settings, principal, "upload")
    return await attach_approved_model(factory, settings, principal, identity, key, body, storage)
