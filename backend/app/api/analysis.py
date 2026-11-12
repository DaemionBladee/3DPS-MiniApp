from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select

from app.api.analysis_schemas import (
    AnalysisResults,
    RetryResponse,
    RetryTask,
    SimulationProfile,
    TaskPage,
)
from app.api.auth import FactoryDependency, PrincipalDependency, SettingsDependency
from app.api.business import BusinessPrincipalDependency, CommandKey, PageLimit, PageOffset
from app.core.errors import AuthError
from app.database.analysis_models import SlicerProfile
from app.database.intake_models import ProcessingTask, RequestItem
from app.services.analysis import owner, owner_task, results, retry
from app.services.intake import authorized_request

router = APIRouter(prefix="/api/v1", tags=["simulation-analysis"])


@router.get("/catalog/simulation-profiles", response_model=list[SimulationProfile])
async def profiles(
    principal: PrincipalDependency, factory: FactoryDependency
) -> list[SimulationProfile]:
    async with factory() as db:
        rows = (
            await db.scalars(
                select(SlicerProfile)
                .where(SlicerProfile.active)
                .order_by(SlicerProfile.key, SlicerProfile.version.desc())
                .limit(100)
            )
        ).all()
        return [SimulationProfile.model_validate(p) for p in rows]


@router.get("/requests/{request_id}/analysis/results", response_model=AnalysisResults)
async def request_results(
    request_id: UUID, principal: PrincipalDependency, factory: FactoryDependency
) -> AnalysisResults:
    async with factory() as db:
        row = await authorized_request(db, principal.user, request_id)
        return await results(db, row)


@router.get("/requests/{request_id}/items/{item_id}/analysis", response_model=AnalysisResults)
async def item_results(
    request_id: UUID, item_id: UUID, principal: PrincipalDependency, factory: FactoryDependency
) -> AnalysisResults:
    async with factory() as db:
        row = await authorized_request(db, principal.user, request_id)
        item = await db.get(RequestItem, item_id)
        if item is None or item.request_id != row.id or not item.active:
            raise AuthError(404, "item_not_found", "This item could not be found.")
        return await results(db, row, item_id)


@router.get("/owner/processing-tasks", response_model=TaskPage)
async def queue(
    principal: PrincipalDependency,
    factory: FactoryDependency,
    limit: PageLimit = 20,
    offset: PageOffset = 0,
) -> TaskPage:
    owner(principal.user)
    async with factory() as db:
        rows = (
            await db.scalars(
                select(ProcessingTask)
                .order_by(ProcessingTask.created_at, ProcessingTask.id)
                .limit(limit + 1)
                .offset(offset)
            )
        ).all()
        return TaskPage(
            items=[await owner_task(db, t) for t in rows[:limit]],
            next_offset=offset + limit if len(rows) > limit and offset + limit <= 10000 else None,
        )


@router.post("/owner/processing-tasks/{task_id}/retry", response_model=RetryResponse)
async def reschedule(
    task_id: UUID,
    body: RetryTask,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    factory: FactoryDependency,
    settings: SettingsDependency,
) -> RetryResponse:
    return await retry(factory, settings, principal, task_id, key, body)
