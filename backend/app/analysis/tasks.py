"""PostgreSQL leases, bounded retries and atomic immutable result publication."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.analysis.registry import safe_profile, snapshot
from app.api.analysis_schemas import WorkerResult
from app.database.analysis_models import ModelAnalysis, SlicerProfile, SlicingRun
from app.database.business_models import AuditLog, NotificationOutbox, ServiceRequest
from app.database.intake_models import ProcessingTask, RequestItem, UploadedFile
from app.services.specifications import item_specification
from app.services.transactions import unit_of_work

LEASE_SECONDS = 180
MAX_CONCURRENT = 2
RETRYABLE = frozenset(
    {"worker_timeout", "worker_crashed", "engine_unavailable", "publication_failed"}
)


class LeaseLost(Exception):
    """Expired, superseded or already consumed delivery; never publish it."""


@dataclass(frozen=True)
class Job:
    task_id: UUID
    request_id: UUID
    lease_token: UUID
    file_id: UUID
    storage_key: str
    size_bytes: int
    sha256: str
    format: str
    profile_id: UUID
    image: str
    manifest: dict[str, Any]


async def event(db: AsyncSession, row: ServiceRequest, task: ProcessingTask, action: str) -> None:
    data = {
        "request_id": str(row.id),
        "task_id": str(task.id),
        "revision": task.request_revision,
        "spec_sha256": task.spec_sha256,
        "attempt": task.attempts,
        "profile_id": str(task.selected_profile_id) if task.selected_profile_id else None,
        "result_id": str(task.result_run_id) if task.result_run_id else None,
        "state": task.state,
        "error_code": task.error_code,
        "mode": "simulation",
    }
    audit = AuditLog(
        actor_kind="system",
        system_actor="analysis-orchestrator",
        actor_user_id=None,
        action=action,
        entity_id=row.id,
        metadata_snapshot=data,
    )
    db.add(audit)
    await db.flush()
    db.add(
        NotificationOutbox(
            audit_log_id=audit.id,
            recipient_user_id=row.customer_id,
            event_type=action,
            payload_minimized=data,
        )
    )
    await db.flush()


def clear_lease(task: ProcessingTask) -> None:
    task.lease_token = None
    task.lease_owner = None
    task.lease_expires_at = None


async def locked(db: AsyncSession, task_id: UUID) -> tuple[ServiceRequest, ProcessingTask]:
    # Match interactive request -> task lock order, including retry/revision updates.
    request_id = await db.scalar(
        select(ProcessingTask.request_id).where(ProcessingTask.id == task_id)
    )
    if request_id is None:
        raise LeaseLost()
    row = await db.scalar(
        select(ServiceRequest).where(ServiceRequest.id == request_id).with_for_update()
    )
    task = await db.scalar(
        select(ProcessingTask).where(ProcessingTask.id == task_id).with_for_update()
    )
    assert row is not None and task is not None
    return row, task


async def current(
    db: AsyncSession, row: ServiceRequest, task: ProcessingTask
) -> UploadedFile | None:
    file = await db.get(UploadedFile, task.uploaded_file_id)
    item = (
        await db.get(RequestItem, file.request_item_id) if file and file.request_item_id else None
    )
    if (
        row.stage_kind != "printing"
        or row.status not in {"submitted", "analyzing", "manual_review"}
        or row.revision != task.request_revision
        or row.canonical_spec_sha256 != task.spec_sha256
        or row.customer_id != task.customer_id
        or not file
        or not item
        or not item.active
        or item.model_file_id != file.id
        or file.owner_id != row.customer_id
        or file.validation_status != "validated"
        or file.storage_state != "ready"
        or not file.sha256
    ):
        return None
    return file


async def fence(
    db: AsyncSession, row: ServiceRequest, task: ProcessingTask, token: UUID
) -> UploadedFile:
    now = (await db.execute(select(func.clock_timestamp()))).scalar_one()
    if (
        task.state != "leased"
        or task.lease_token != token
        or not task.lease_expires_at
        or task.lease_expires_at <= now
    ):
        raise LeaseLost()
    file = await current(db, row, task)
    if file is None:
        raise LeaseLost()
    return file


async def settle_request(db: AsyncSession, row: ServiceRequest) -> None:
    await db.flush()
    tasks = (
        await db.scalars(
            select(ProcessingTask).where(
                ProcessingTask.request_id == row.id, ProcessingTask.request_revision == row.revision
            )
        )
    ).all()
    if tasks and all(t.state in {"succeeded", "failed", "superseded"} for t in tasks):
        row.status = (
            "manual_review"  # No quote eligibility or downstream business authorization in M06.
        )
        row.version += 1
        row.updated_at = datetime.now(UTC)


async def fail_locked(
    db: AsyncSession, row: ServiceRequest, task: ProcessingTask, code: str
) -> None:
    retry = code in RETRYABLE and task.attempts < task.max_attempts
    task.state = "pending" if retry else "failed"
    task.error_code = code
    task.retryable = code in RETRYABLE
    task.next_available_at = datetime.now(UTC) + timedelta(
        seconds=min(300, 10 * 2 ** max(0, task.attempts - 1))
    )
    task.completed_at = None if retry else datetime.now(UTC)
    clear_lease(task)
    await settle_request(db, row)
    await event(db, row, task, "analysis.retry_scheduled" if retry else "analysis.failed")


async def recover(factory: async_sessionmaker[AsyncSession]) -> int:
    async with factory() as db:
        ids = (
            await db.scalars(
                select(ProcessingTask.id)
                .where(
                    ProcessingTask.state == "leased",
                    ProcessingTask.lease_expires_at <= func.clock_timestamp(),
                )
                .limit(100)
            )
        ).all()
    count = 0
    for task_id in ids:
        async with unit_of_work(factory) as db:
            row, task = await locked(db, task_id)
            now = (await db.execute(select(func.clock_timestamp()))).scalar_one()
            if task.state != "leased" or not task.lease_expires_at or task.lease_expires_at > now:
                continue
            if await current(db, row, task) is None:
                task.state = "superseded"
                clear_lease(task)
                await event(db, row, task, "analysis.superseded")
            else:
                await fail_locked(db, row, task, "worker_timeout")
            count += 1
    return count


async def claim(factory: async_sessionmaker[AsyncSession], owner: str) -> Job | None:
    if not owner or len(owner) > 80:
        raise ValueError("Invalid orchestrator identifier")
    await recover(factory)
    async with unit_of_work(factory) as db:
        await db.execute(text("SELECT pg_advisory_xact_lock(6006002)"))
        active = await db.scalar(
            select(func.count())
            .select_from(ProcessingTask)
            .where(
                ProcessingTask.state == "leased",
                ProcessingTask.lease_expires_at > func.clock_timestamp(),
            )
        )
        if (active or 0) >= MAX_CONCURRENT:
            return None
        candidates = (
            await db.scalars(
                select(ProcessingTask.id)
                .where(
                    ProcessingTask.state == "pending",
                    ProcessingTask.next_available_at <= func.clock_timestamp(),
                    ProcessingTask.attempts < ProcessingTask.max_attempts,
                )
                .order_by(ProcessingTask.created_at, ProcessingTask.id)
                .limit(100)
            )
        ).all()
        for task_id in candidates:
            request_id = await db.scalar(
                select(ProcessingTask.request_id).where(ProcessingTask.id == task_id)
            )
            row = await db.scalar(
                select(ServiceRequest)
                .where(ServiceRequest.id == request_id)
                .with_for_update(skip_locked=True)
            )
            if row is None:
                continue
            task = await db.scalar(
                select(ProcessingTask)
                .where(ProcessingTask.id == task_id, ProcessingTask.state == "pending")
                .with_for_update(skip_locked=True)
            )
            if task is None:
                continue
            file = await current(db, row, task)
            if file is None:
                task.state = "superseded"
                await event(db, row, task, "analysis.superseded")
                continue
            item = await db.get(RequestItem, file.request_item_id)
            assert item is not None and file.sha256 is not None and file.format is not None
            profile = (
                await db.get(SlicerProfile, task.selected_profile_id)
                if task.selected_profile_id
                else await db.scalar(
                    select(SlicerProfile)
                    .where(
                        SlicerProfile.active,
                        SlicerProfile.material_key == item.material_key,
                        SlicerProfile.quality_key == item.quality_key,
                    )
                    .order_by(SlicerProfile.version.desc(), SlicerProfile.id)
                    .limit(1)
                )
            )
            if (
                profile is None
                or profile.material_key != item.material_key
                or profile.quality_key != item.quality_key
            ):
                await fail_locked(db, row, task, "profile_unavailable")
                continue
            try:
                safe_profile(profile)
            except ValueError:
                await fail_locked(db, row, task, "unsafe_profile")
                continue
            now = (await db.execute(select(func.clock_timestamp()))).scalar_one()
            token = uuid4()
            task.state, task.lease_token, task.lease_owner = "leased", token, owner
            task.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
            task.attempts += 1
            task.started_at, task.completed_at, task.error_code = None, None, None
            task.selected_profile_id = profile.id
            task.retryable = False
            task.result_run_id = None
            await db.flush()
            return Job(
                task.id,
                row.id,
                token,
                file.id,
                file.storage_key,
                file.size_bytes,
                file.sha256,
                file.format,
                profile.id,
                profile.worker_image,
                {
                    "schema_version": 1,
                    "task_id": str(task.id),
                    "lease_token": str(token),
                    "input_sha256": file.sha256,
                    "input_format": file.format,
                    "profile_sha256": profile.config_sha256,
                    "profile": profile.configuration,
                    "specification": {
                        k: v
                        for k, v in item_specification(item).model_dump().items()
                        if k
                        in {
                            "unit_key",
                            "unit_confirmed",
                            "dimension_x_mm",
                            "dimension_y_mm",
                            "dimension_z_mm",
                            "dimension_tolerance_mm",
                        }
                    },
                },
            )
    return None


async def started(factory: async_sessionmaker[AsyncSession], job: Job) -> None:
    async with unit_of_work(factory) as db:
        row, task = await locked(db, job.task_id)
        await fence(db, row, task, job.lease_token)
        if task.started_at is not None:
            return
        task.started_at = datetime.now(UTC)
        if row.status != "analyzing":
            row.status = "analyzing"
            row.version += 1
            row.updated_at = datetime.now(UTC)
        await event(db, row, task, "analysis.started")


async def failed(factory: async_sessionmaker[AsyncSession], job: Job, code: str) -> None:
    allowed = RETRYABLE | {
        "malformed_geometry",
        "input_checksum_mismatch",
        "input_unavailable",
        "output_verification_failed",
        "unsafe_profile",
        "unit_confirmation_required",
        "declared_unit_mismatch",
        "geometry_complexity_limit",
        "impossible_scale",
        "slicer_failed",
        "worker_memory_limit",
        "worker_io_limit",
        "worker_output_limit",
    }
    code = code if code in allowed else "malformed_geometry"
    async with unit_of_work(factory) as db:
        row, task = await locked(db, job.task_id)
        await fence(db, row, task, job.lease_token)
        await fail_locked(db, row, task, code)


async def publish(factory: async_sessionmaker[AsyncSession], job: Job, output: bytes) -> UUID:
    if not 0 < len(output) <= 32768:
        raise ValueError("output_verification_failed")
    result = WorkerResult.model_validate_json(output)
    async with unit_of_work(factory) as db:
        row, task = await locked(db, job.task_id)
        file = await fence(db, row, task, job.lease_token)
        p = await db.get(SlicerProfile, task.selected_profile_id)
        if not p or task.started_at is None:
            raise ValueError("output_verification_failed")
        safe_profile(p)
        if (
            result.task_id != str(task.id)
            or result.lease_token != str(job.lease_token)
            or result.input_sha256 != file.sha256
            or result.profile_sha256 != p.config_sha256
            or result.engine_version != p.engine_version
            or result.executable_sha256 != p.executable_sha256
            or job.image != p.worker_image
            or result.geometry.format != file.format
            or result.geometry.unit_key != job.manifest["specification"]["unit_key"]
        ):
            raise ValueError("output_verification_failed")
        analysis = ModelAnalysis(
            task_id=task.id,
            lease_token=job.lease_token,
            request_id=row.id,
            customer_id=row.customer_id,
            request_item_id=file.request_item_id,
            uploaded_file_id=file.id,
            request_revision=task.request_revision,
            input_sha256=file.sha256,
            spec_sha256=task.spec_sha256,
            analyzer_version=result.analyzer_version,
            geometry=result.geometry.model_dump(),
        )
        db.add(analysis)
        await db.flush()
        run = SlicingRun(
            task_id=task.id,
            lease_token=job.lease_token,
            model_analysis_id=analysis.id,
            slicer_profile_id=p.id,
            outcome=result.outcome,
            profile_snapshot=snapshot(p),
            engine_version=p.engine_version,
            executable_sha256=p.executable_sha256,
            worker_image=p.worker_image,
            estimate=result.estimate.model_dump() if result.estimate else None,
            sandbox_evidence=result.sandbox.model_dump(),
        )
        db.add(run)
        await db.flush()
        # Recheck wall-clock lease after validation and durable inserts.
        await fence(db, row, task, job.lease_token)
        task.state, task.result_run_id, task.completed_at = "succeeded", run.id, datetime.now(UTC)
        task.error_code, task.retryable = None, False
        clear_lease(task)
        await settle_request(db, row)
        await event(db, row, task, "analysis.completed")
        return run.id
