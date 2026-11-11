from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select, text

from app.api.auth import (
    FactoryDependency,
    PrincipalDependency,
    SettingsDependency,
    WritePrincipalDependency,
)
from app.api.business_schemas import (
    CreateRequest,
    DraftPatch,
    ProjectPage,
    ProjectRequestResponse,
    ProjectResponse,
    RequestPage,
    RequestResponse,
    RequestTransition,
)
from app.api.schemas import StatusResponse
from app.core.errors import AuthError
from app.database.business_models import ServiceProject, ServiceRequest
from app.domain.types import RequestStatus, StageKind
from app.intake.rate_limits import consume_rate
from app.services.auth import Principal
from app.services.requests import create_request, transition_request, update_draft

router = APIRouter(prefix="/api/v1", tags=["business-foundation"])
CommandKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
]
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0, le=10000)]


async def require_business_write(
    principal: WritePrincipalDependency, factory: FactoryDependency, settings: SettingsDependency
) -> Principal:
    await consume_rate(factory, settings, principal, "intake")
    return principal


BusinessPrincipalDependency = Annotated[Principal, Depends(require_business_write)]


def require_owner(principal: PrincipalDependency) -> None:
    if principal.user.role != "owner":
        raise AuthError(403, "owner_required", "This action requires Owner access.")


@router.post("/requests", response_model=ProjectRequestResponse, status_code=201)
async def create(
    body: CreateRequest,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
) -> ProjectRequestResponse:
    return await create_request(factory, settings, principal, key, body)


@router.get("/requests", response_model=RequestPage)
async def own_requests(
    principal: PrincipalDependency,
    factory: FactoryDependency,
    limit: PageLimit = 20,
    offset: PageOffset = 0,
) -> RequestPage:
    async with factory() as db:
        rows = (
            await db.scalars(
                select(ServiceRequest)
                .where(ServiceRequest.customer_id == principal.user.id)
                .order_by(ServiceRequest.created_at, ServiceRequest.id)
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
        return RequestPage(
            items=[RequestResponse.model_validate(row) for row in rows[:limit]],
            next_offset=offset + limit if len(rows) > limit and offset + limit <= 10000 else None,
        )


@router.get("/owner/requests", response_model=RequestPage)
async def owner_requests(
    principal: PrincipalDependency,
    factory: FactoryDependency,
    limit: PageLimit = 20,
    offset: PageOffset = 0,
    status: RequestStatus | None = None,
    stage_kind: StageKind | None = None,
) -> RequestPage:
    require_owner(principal)
    statement = select(ServiceRequest)
    if status is not None:
        statement = statement.where(ServiceRequest.status == status)
    if stage_kind is not None:
        statement = statement.where(ServiceRequest.stage_kind == stage_kind)
    async with factory() as db:
        rows = (
            await db.scalars(
                statement.order_by(ServiceRequest.created_at, ServiceRequest.id)
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
        return RequestPage(
            items=[RequestResponse.model_validate(row) for row in rows[:limit]],
            next_offset=offset + limit if len(rows) > limit and offset + limit <= 10000 else None,
        )


@router.get("/requests/{request_id}", response_model=RequestResponse)
async def detail(
    request_id: UUID, principal: PrincipalDependency, factory: FactoryDependency
) -> RequestResponse:
    async with factory() as db:
        row = await db.get(ServiceRequest, request_id)
        if row is None or (row.customer_id != principal.user.id and principal.user.role != "owner"):
            raise AuthError(404, "request_not_found", "This request could not be found.")
        return RequestResponse.model_validate(row)


@router.patch("/requests/{request_id}", response_model=RequestResponse)
async def patch(
    request_id: UUID,
    body: DraftPatch,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
) -> RequestResponse:
    return await update_draft(factory, settings, principal, key, request_id, body)


@router.post("/requests/{request_id}/transitions", response_model=RequestResponse)
async def change_status(
    request_id: UUID,
    body: RequestTransition,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
) -> RequestResponse:
    return await transition_request(factory, settings, principal, key, request_id, body)


@router.get("/projects", response_model=ProjectPage)
async def projects(
    principal: PrincipalDependency,
    factory: FactoryDependency,
    limit: PageLimit = 20,
    offset: PageOffset = 0,
) -> ProjectPage:
    async with factory() as db:
        rows = (
            await db.scalars(
                select(ServiceProject)
                .where(ServiceProject.customer_id == principal.user.id)
                .order_by(ServiceProject.created_at, ServiceProject.id)
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
        return ProjectPage(
            items=[ProjectResponse.model_validate(row) for row in rows[:limit]],
            next_offset=offset + limit if len(rows) > limit and offset + limit <= 10000 else None,
        )


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def project_detail(
    project_id: UUID, principal: PrincipalDependency, factory: FactoryDependency
) -> ProjectResponse:
    async with factory() as db:
        row = await db.get(ServiceProject, project_id)
        if row is None or (row.customer_id != principal.user.id and principal.user.role != "owner"):
            raise AuthError(404, "project_not_found", "This project could not be found.")
        return ProjectResponse.model_validate(row)


@router.get("/ready", response_model=StatusResponse)
async def readiness(principal: PrincipalDependency, factory: FactoryDependency) -> StatusResponse:
    require_owner(principal)
    async with factory() as db:
        if (
            await db.scalar(text("SELECT version_num FROM alembic_version"))
            != "0004_design_intake"
        ):
            raise AuthError(503, "schema_not_ready", "The service schema is not ready.")
    return StatusResponse()
