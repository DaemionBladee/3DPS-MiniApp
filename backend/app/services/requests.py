from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.business_schemas import (
    CreateRequest,
    DraftPatch,
    ProjectRequestResponse,
    ProjectResponse,
    RequestResponse,
    RequestTransition,
)
from app.core.config import Settings
from app.core.errors import AuthError
from app.database.business_models import (
    AuditLog,
    NotificationOutbox,
    ServiceProject,
    ServiceRequest,
)
from app.database.models import User
from app.domain.requests import initial_stage, specification_hash, transition
from app.services.auth import Principal
from app.services.specifications import refresh_spec
from app.services.transactions import execute_command


async def record_event(
    database: AsyncSession,
    actor: User,
    row: ServiceRequest,
    action: str,
    old_status: str | None,
    reason: str | None = None,
) -> None:
    snapshot = {
        "request_id": str(row.id),
        "project_id": str(row.service_project_id),
        "stage_kind": row.stage_kind,
        "mode": row.mode,
        "version": row.version,
        "revision": row.revision,
        "status": row.status,
        "old_status": old_status,
        "spec_sha256": row.canonical_spec_sha256,
    }
    audit = AuditLog(
        actor_user_id=actor.id,
        action=action,
        entity_id=row.id,
        metadata_snapshot=snapshot,
        reason=reason,
    )
    database.add(audit)
    await database.flush()
    database.add(
        NotificationOutbox(
            audit_log_id=audit.id,
            recipient_user_id=row.customer_id,
            event_type=action,
            payload_minimized=snapshot,
        )
    )
    await database.flush()


async def locked_request(
    database: AsyncSession, user: User, request_id: UUID, version: int | None
) -> ServiceRequest:
    row = await database.scalar(
        select(ServiceRequest).where(ServiceRequest.id == request_id).with_for_update()
    )
    if row is None or (row.customer_id != user.id and user.role != "owner"):
        raise AuthError(404, "request_not_found", "This request could not be found.")
    if version is not None and row.version != version:
        raise AuthError(
            409, "stale_version", "This request has changed. Refresh before trying again."
        )
    return row


async def create_request(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    principal: Principal,
    key: str,
    body: CreateRequest,
) -> ProjectRequestResponse:
    async def operation(db: AsyncSession, user: User) -> ProjectRequestResponse:
        project = ServiceProject(customer_id=user.id, kind=body.service_type, mode="simulation")
        db.add(project)
        await db.flush()
        stage = initial_stage(body.service_type)
        row = ServiceRequest(
            service_project_id=project.id,
            customer_id=user.id,
            service_type=body.service_type,
            stage_kind=stage,
            mode="simulation",
            status="draft",
            version=1,
            revision=1,
            customer_notes=body.customer_notes,
            canonical_spec_sha256=specification_hash(body.service_type, stage, body.customer_notes),
        )
        db.add(row)
        await db.flush()
        await refresh_spec(db, row, advance=False)
        await record_event(db, user, row, "request.created", None)
        return ProjectRequestResponse(
            project=ProjectResponse.model_validate(project),
            request=RequestResponse.model_validate(row),
        )

    return await execute_command(
        factory,
        settings,
        principal,
        "request.create",
        key,
        body.model_dump(),
        ProjectRequestResponse,
        operation,
    )


async def update_draft(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    principal: Principal,
    key: str,
    request_id: UUID,
    body: DraftPatch,
) -> RequestResponse:
    async def authorize_replay(db: AsyncSession, user: User) -> None:
        row = await locked_request(db, user, request_id, None)
        if row.customer_id != user.id:
            raise AuthError(403, "customer_edit_required", "Only the customer can edit this draft.")

    async def operation(db: AsyncSession, user: User) -> RequestResponse:
        row = await locked_request(db, user, request_id, body.expected_version)
        # The owner may inspect/cancel a draft, never impersonate its customer.
        if row.customer_id != user.id:
            raise AuthError(403, "customer_edit_required", "Only the customer can edit this draft.")
        if row.status != "draft":
            raise AuthError(409, "invalid_transition", "This request is no longer a draft.")
        changes = body.model_dump(exclude={"expected_version"}, exclude_none=True)
        if all(getattr(row, field) == value for field, value in changes.items()):
            return RequestResponse.model_validate(row)
        for field, value in changes.items():
            setattr(row, field, value)
        await refresh_spec(db, row)
        await record_event(db, user, row, "request.draft_updated", "draft")
        return RequestResponse.model_validate(row)

    return await execute_command(
        factory,
        settings,
        principal,
        f"request.update:{request_id}",
        key,
        body.model_dump(),
        RequestResponse,
        operation,
        authorize_replay,
    )


async def transition_request(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    principal: Principal,
    key: str,
    request_id: UUID,
    body: RequestTransition,
) -> RequestResponse:
    async def authorize_replay(db: AsyncSession, user: User) -> None:
        await locked_request(db, user, request_id, None)

    async def operation(db: AsyncSession, user: User) -> RequestResponse:
        row = await locked_request(db, user, request_id, body.expected_version)
        old_status = row.status
        row.status = transition(row.status, body.target)
        row.version += 1
        row.updated_at = datetime.now(UTC)
        await record_event(db, user, row, "request.cancelled", old_status, body.reason)
        return RequestResponse.model_validate(row)

    return await execute_command(
        factory,
        settings,
        principal,
        f"request.transition:{request_id}",
        key,
        body.model_dump(),
        RequestResponse,
        operation,
        authorize_replay,
    )
