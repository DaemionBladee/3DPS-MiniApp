"""Authorized analysis projections and reasoned, bounded Owner retries."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.analysis.registry import safe_profile
from app.api.analysis_schemas import (
    AnalysisResult,
    AnalysisResults,
    OwnerTask,
    RetryResponse,
    RetryTask,
    SimulationProfile,
)
from app.api.intake_schemas import AnalysisStatus, TaskResponse
from app.core.config import Settings
from app.core.errors import AuthError
from app.database.analysis_models import ModelAnalysis, SlicerProfile, SlicingRun
from app.database.business_models import ServiceRequest
from app.database.intake_models import ProcessingTask, RequestItem, UploadedFile
from app.database.models import User
from app.services.auth import Principal
from app.services.intake import authorized_request
from app.services.requests import record_event
from app.services.specifications import item_specification
from app.services.transactions import execute_command


def owner(user: User) -> None:
    if user.role != "owner":
        raise AuthError(403, "owner_required", "This action requires Owner access.")


async def results(
    db: AsyncSession, row: ServiceRequest, item_id: UUID | None = None
) -> AnalysisResults:
    statement = (
        select(ModelAnalysis, SlicingRun, SlicerProfile, RequestItem, UploadedFile)
        .join(SlicingRun, SlicingRun.model_analysis_id == ModelAnalysis.id)
        .join(ProcessingTask, ProcessingTask.id == ModelAnalysis.task_id)
        .join(SlicerProfile, SlicerProfile.id == SlicingRun.slicer_profile_id)
        .join(RequestItem, RequestItem.id == ModelAnalysis.request_item_id)
        .join(UploadedFile, UploadedFile.id == ModelAnalysis.uploaded_file_id)
        .where(
            ModelAnalysis.request_id == row.id,
            ModelAnalysis.request_revision == row.revision,
            ModelAnalysis.spec_sha256 == row.canonical_spec_sha256,
            ProcessingTask.state == "succeeded",
            ProcessingTask.result_run_id == SlicingRun.id,
            RequestItem.active,
            RequestItem.model_file_id == UploadedFile.id,
            ModelAnalysis.input_sha256 == UploadedFile.sha256,
            UploadedFile.storage_state == "ready",
            UploadedFile.validation_status == "validated",
        )
        .order_by(ModelAnalysis.created_at, ModelAnalysis.id)
        .limit(100)
    )
    if item_id is not None:
        statement = statement.where(RequestItem.id == item_id)
    values = (await db.execute(statement)).all()
    return AnalysisResults(
        items=[
            AnalysisResult(
                id=run.id,
                task_id=a.task_id,
                request_item_id=item.id,
                uploaded_file_id=file.id,
                request_revision=a.request_revision,
                spec_sha256=a.spec_sha256,
                input_sha256=a.input_sha256,
                outcome=run.outcome,
                geometry=a.geometry,
                estimate=run.estimate,
                profile=SimulationProfile.model_validate(p),
                profile_snapshot=run.profile_snapshot,
                engine_version=run.engine_version,
                executable_sha256=run.executable_sha256,
                worker_image=run.worker_image,
                quantity=item.quantity,
                submitted_specification=item_specification(item),
                special_requirements=bool(
                    item.special_requirements.strip() or row.customer_notes.strip()
                ),
            )
            for a, run, p, item, file in values
        ]
    )


async def status(db: AsyncSession, row: ServiceRequest) -> AnalysisStatus:
    tasks = (
        await db.scalars(
            select(ProcessingTask)
            .where(ProcessingTask.request_id == row.id)
            .order_by(ProcessingTask.created_at, ProcessingTask.id)
            .limit(100)
        )
    ).all()
    active = [
        t
        for t in tasks
        if t.request_revision == row.revision
        and t.spec_sha256 == row.canonical_spec_sha256
        and t.state != "superseded"
    ]
    now = datetime.now(UTC)
    running = any(
        t.state == "leased" and t.started_at and t.lease_expires_at and t.lease_expires_at > now
        for t in active
    )
    state = "not_submitted"
    if active:
        if running:
            state = "processing"
        elif any(t.state in {"pending", "leased"} for t in active):
            state = "pending"
        elif any(t.state == "failed" for t in active):
            state = (
                "needs_clarification"
                if any(
                    t.error_code in {"unit_confirmation_required", "declared_unit_mismatch"}
                    for t in active
                )
                else "failed"
            )
        else:
            current = await results(db, row)
            if len(current.items) != len(active):
                state = "superseded"
            elif any(r.outcome == "manual_review" for r in current.items):
                state = (
                    "needs_clarification"
                    if any(
                        "customer_dimension_mismatch" in r.geometry.review_reasons
                        for r in current.items
                    )
                    else "manual_review"
                )
            else:
                state = "completed"
    elif tasks:
        state = "superseded"
    return AnalysisStatus(
        state=state,
        tasks=[TaskResponse.model_validate(t) for t in tasks],
        processing_available=running,
    )


async def owner_task(db: AsyncSession, task: ProcessingTask) -> OwnerTask:
    row = await db.get(ServiceRequest, task.request_id)
    file = await db.get(UploadedFile, task.uploaded_file_id)
    item = await db.get(RequestItem, file.request_item_id) if file else None
    return OwnerTask(
        **TaskResponse.model_validate(task).model_dump(),
        request_id=task.request_id,
        customer_id=task.customer_id,
        selected_profile_id=task.selected_profile_id,
        max_attempts=task.max_attempts,
        next_available_at=task.next_available_at,
        completed_at=task.completed_at,
        special_requirements=bool(
            (row and row.customer_notes.strip()) or (item and item.special_requirements.strip())
        ),
    )


async def retry(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    principal: Principal,
    task_id: UUID,
    key: str,
    body: RetryTask,
) -> RetryResponse:
    async def replay(db: AsyncSession, user: User) -> None:
        owner(user)
        task = await db.get(ProcessingTask, task_id)
        if task is None:
            raise AuthError(404, "task_not_found", "This processing task could not be found.")
        await authorized_request(db, user, task.request_id)

    async def operation(db: AsyncSession, user: User) -> RetryResponse:
        from app.analysis.tasks import current, locked

        owner(user)
        # Avoid revealing a missing task as an internal worker exception.
        await replay(db, user)
        row, task = await locked(db, task_id)
        if row.version != body.expected_version:
            raise AuthError(409, "stale_version", "Refresh this request before retrying.")
        if task.state not in {"failed", "succeeded"} or await current(db, row, task) is None:
            raise AuthError(
                409,
                "task_not_retryable",
                "Only current completed simulation work can be rescheduled.",
            )
        if not body.reason.strip() or any(ord(c) < 32 for c in body.reason):
            raise AuthError(422, "reason_required", "Provide a clear review reason.")
        if task.attempts >= 6:
            raise AuthError(409, "retry_budget_exhausted", "The bounded retry budget is exhausted.")
        file = await db.get(UploadedFile, task.uploaded_file_id)
        item = await db.get(RequestItem, file.request_item_id) if file else None
        profile = (
            await db.get(SlicerProfile, body.profile_id or task.selected_profile_id)
            if (body.profile_id or task.selected_profile_id)
            else None
        )
        if (
            profile is None
            or item is None
            or profile.material_key != item.material_key
            or profile.quality_key != item.quality_key
        ):
            raise AuthError(
                422, "profile_unavailable", "Select an approved compatible simulation profile."
            )
        try:
            safe_profile(profile)
        except ValueError:
            raise AuthError(422, "profile_unavailable", "This profile is not available.") from None
        task.selected_profile_id = profile.id
        task.max_attempts = min(6, max(task.max_attempts, task.attempts + 1))
        task.state, task.result_run_id, task.started_at, task.completed_at = (
            "pending",
            None,
            None,
            None,
        )
        task.next_available_at, task.error_code, task.retryable = datetime.now(UTC), None, False
        row.version += 1
        row.updated_at = datetime.now(UTC)
        await record_event(
            db,
            user,
            row,
            "analysis.rescheduled",
            row.status,
            body.reason,
            {"task_id": str(task.id), "profile_id": str(profile.id), "simulation_only": True},
        )
        return RetryResponse(request_id=row.id, task_id=task.id, version=row.version)

    return await execute_command(
        factory,
        settings,
        principal,
        "analysis.retry",
        key,
        {"task_id": str(task_id), **body.model_dump(mode="json")},
        RetryResponse,
        operation,
        replay,
    )
