"""Design commands reuse current sessions, row locking, audit/outbox and idempotency."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.business_schemas import RequestResponse
from app.api.design_schemas import (
    BriefCommand,
    ConvertDesign,
    DesignBrief,
    DesignDetail,
    DesignReviewResponse,
    DesignVersionResponse,
    PublishProof,
    RemoveReference,
    ReviewProof,
    ScopeAgreement,
    ScopeCommand,
    ScopeResponse,
    SimulationFixture,
)
from app.api.design_schemas import DesignScope as ScopeSpec
from app.api.intake_schemas import FileMetadata, VersionCommand
from app.core.config import Settings
from app.core.errors import AuthError
from app.database.business_models import ServiceRequest
from app.database.design_models import DesignProject, DesignReview, DesignScope, DesignVersion
from app.database.intake_models import RequestItem, UploadedFile
from app.database.models import User
from app.intake.storage import PrivateStorage
from app.services.auth import Principal
from app.services.requests import locked_request, record_event
from app.services.specifications import canonical_hash, refresh_spec
from app.services.transactions import execute_command


def owner_only(user: User) -> None:
    if user.role != "owner":
        raise AuthError(403, "owner_required", "This action requires Owner access.")


def customer_only(row: ServiceRequest, user: User) -> None:
    if row.customer_id != user.id:
        raise AuthError(403, "customer_required", "Only this customer can agree or review.")


async def project_for_request(db: AsyncSession, row: ServiceRequest) -> DesignProject:
    if row.stage_kind != "design":
        raise AuthError(409, "design_stage_required", "This workflow requires a design stage.")
    project = await db.scalar(
        select(DesignProject).where(DesignProject.request_id == row.id).with_for_update()
    )
    if project is None:
        project = DesignProject(
            request_id=row.id,
            service_project_id=row.service_project_id,
            customer_id=row.customer_id,
            brief=DesignBrief(
                delivery_kind="printing" if row.service_type == "design_and_print" else "digital"
            ).model_dump(),
        )
        db.add(project)
        await db.flush()
    return project


async def locked_design(
    db: AsyncSession, user: User, identity: UUID, expected: int | None = None
) -> tuple[DesignProject, ServiceRequest]:
    project = await db.get(DesignProject, identity)
    if project is None:
        raise AuthError(404, "design_not_found", "This design project could not be found.")
    row = await locked_request(db, user, project.request_id, expected)
    project = await db.scalar(
        select(DesignProject)
        .where(DesignProject.id == identity)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert project is not None
    return project, row


async def linked_print(db: AsyncSession, project: DesignProject) -> ServiceRequest | None:
    return await db.scalar(
        select(ServiceRequest).where(
            ServiceRequest.service_project_id == project.service_project_id,
            ServiceRequest.stage_kind == "printing",
        )
    )


async def ensure_no_print(db: AsyncSession, project: DesignProject) -> None:
    if await linked_print(db, project) is not None:
        raise AuthError(
            409,
            "printing_lineage_frozen",
            "A linked printing draft already freezes this approved design.",
        )


async def detail(
    db: AsyncSession, project: DesignProject, row: ServiceRequest, user: User
) -> DesignDetail:
    scopes = (
        await db.scalars(
            select(DesignScope)
            .where(DesignScope.design_project_id == project.id)
            .order_by(DesignScope.number)
        )
    ).all()
    versions = (
        await db.scalars(
            select(DesignVersion)
            .where(DesignVersion.design_project_id == project.id)
            .order_by(DesignVersion.number)
        )
    ).all()
    proofs: list[DesignVersionResponse] = []
    used: set[UUID] = set()
    for version in versions:
        preview = await db.get(UploadedFile, version.preview_file_id)
        assert preview is not None
        manufacturing = (
            await db.get(UploadedFile, version.manufacturing_file_id)
            if version.manufacturing_file_id and user.role == "owner"
            else None
        )
        review = await db.scalar(
            select(DesignReview).where(DesignReview.design_version_id == version.id)
        )
        proofs.append(
            DesignVersionResponse(
                id=version.id,
                number=version.number,
                scope_id=version.scope_id,
                preview=FileMetadata.model_validate(preview),
                manufacturing_file=FileMetadata.model_validate(manufacturing)
                if manufacturing
                else None,
                manufacturing_ready=version.manufacturing_ready,
                release_notes=version.release_notes,
                specification_sha256=version.specification_sha256,
                review=DesignReviewResponse.model_validate(review) if review else None,
            )
        )
        used.add(version.preview_file_id)
        if version.manufacturing_file_id:
            used.add(version.manufacturing_file_id)
    files = (
        await db.scalars(
            select(UploadedFile)
            .where(
                UploadedFile.request_id == row.id,
                UploadedFile.storage_state == "ready",
                UploadedFile.validation_status == "validated",
            )
            .order_by(UploadedFile.created_at)
        )
    ).all()
    printing = await linked_print(db, project)
    item_id = (
        await db.scalar(
            select(RequestItem.id)
            .where(RequestItem.request_id == printing.id, RequestItem.active)
            .order_by(RequestItem.created_at)
            .limit(1)
        )
        if printing
        else None
    )
    customer = await db.get(User, row.customer_id)
    assert customer is not None
    return DesignDetail(
        id=project.id,
        request=RequestResponse.model_validate(row),
        state=project.state,
        brief=DesignBrief.model_validate(project.brief),
        scopes=[
            ScopeResponse(
                id=scope.id,
                number=scope.number,
                scope=ScopeSpec.model_validate(scope.specification),
                agreed=scope.agreed_at is not None,
            )
            for scope in scopes
        ],
        approved_scope_id=project.approved_scope_id,
        versions=proofs,
        latest_version_id=project.latest_version_id,
        approved_version_id=project.approved_version_id,
        references=[
            FileMetadata.model_validate(file)
            for file in files
            if file.purpose == "design_reference"
        ],
        working_files=[
            FileMetadata.model_validate(file)
            for file in files
            if user.role == "owner" and file.purpose != "design_reference" and file.id not in used
        ],
        simulation_fixture=project.fixture_scope_id is not None
        and project.fixture_scope_id == project.approved_scope_id,
        linked_print_request=RequestResponse.model_validate(printing) if printing else None,
        linked_print_item_id=item_id,
        customer_display_name=customer.display_name,
    )


async def changed(
    db: AsyncSession,
    user: User,
    row: ServiceRequest,
    action: str,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    row.version += 1
    row.updated_at = datetime.now(UTC)
    await record_event(db, user, row, action, row.status, reason, metadata)


async def design_command(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    principal: Principal,
    identity: UUID,
    key: str,
    action: str,
    body: VersionCommand,
    storage: PrivateStorage,
) -> DesignDetail:
    async def replay(db: AsyncSession, user: User) -> None:
        project, row = await locked_design(db, user, identity)
        if action in {"scope", "fixture", "publish", "convert"}:
            owner_only(user)
        else:
            customer_only(row, user)

    async def operation(db: AsyncSession, user: User) -> DesignDetail:
        project, row = await locked_design(db, user, identity, body.expected_version)
        if action in {"scope", "fixture", "publish", "convert"}:
            owner_only(user)
        else:
            customer_only(row, user)
        if row.status == "cancelled":
            raise AuthError(409, "design_cancelled", "This design request is cancelled.")
        metadata: dict[str, Any] = {"design_project_id": str(project.id)}
        reason = getattr(body, "reason", None)
        if action == "brief":
            assert isinstance(body, BriefCommand)
            if row.status != "draft":
                raise AuthError(409, "draft_required", "Submitted briefs are frozen.")
            validate_delivery(row, body.brief.delivery_kind)
            if project.brief == body.brief.model_dump():
                return await detail(db, project, row, user)
            project.brief = body.brief.model_dump()
            await refresh_spec(db, row)
            # refresh_spec already advances version.
            row.version -= 1
        elif action == "remove-reference":
            assert isinstance(body, RemoveReference)
            if row.status != "draft":
                raise AuthError(409, "draft_required", "Submitted references are frozen.")
            file = await db.get(UploadedFile, body.file_id)
            if (
                file is None
                or file.request_id != row.id
                or file.purpose != "design_reference"
                or file.owner_id != row.customer_id
            ):
                raise AuthError(404, "file_not_found", "This reference could not be found.")
            if file.storage_state == "deleted" or file.validation_status == "removed":
                return await detail(db, project, row, user)
            if file.storage_state == "ready":
                file.lease_expires_at = datetime.now(UTC)
            file.validation_status = "removed"
            file.storage_state = "delete_pending"
            await refresh_spec(db, row)
            row.version -= 1
            metadata["file_id"] = str(file.id)
        elif action == "submit":
            if row.status != "draft":
                raise AuthError(409, "draft_required", "This brief was already submitted.")
            brief = DesignBrief.model_validate(project.brief)
            validate_delivery(row, brief.delivery_kind)
            if any(
                len(value.strip()) < 3
                for value in [
                    brief.description,
                    brief.intended_use,
                    brief.dimensions,
                    brief.tolerances,
                ]
            ):
                raise AuthError(
                    422,
                    "incomplete_design_brief",
                    "Describe the purpose, dimensions and tolerance requirements; use Not sure where needed.",
                )
            files = (
                await db.scalars(
                    select(UploadedFile).where(
                        UploadedFile.request_id == row.id,
                        UploadedFile.purpose == "design_reference",
                        UploadedFile.storage_state != "deleted",
                        UploadedFile.validation_status != "removed",
                    )
                )
            ).all()
            for file in files:
                await cleared_file(storage, file)
            from app.services.specifications import design_spec

            row.submitted_spec = await design_spec(db, row, project)
            row.canonical_spec_sha256 = canonical_hash(row.submitted_spec)
            row.spec_schema_version = 3
            row.status = "submitted"
            row.submitted_revision = row.revision
            row.submitted_at = datetime.now(UTC)
            project.state = "brief_received"
        elif action == "scope":
            assert isinstance(body, ScopeCommand)
            await ensure_no_print(db, project)
            if row.status != "submitted":
                raise AuthError(
                    409, "brief_submission_required", "Submit the brief before proposing scope."
                )
            validate_delivery(
                row,
                "digital"
                if body.scope.includes_digital_delivery and row.service_type == "custom_design"
                else "both"
                if body.scope.includes_digital_delivery
                else "printing",
            )
            number = (
                await db.scalar(
                    select(func.count())
                    .select_from(DesignScope)
                    .where(DesignScope.design_project_id == project.id)
                )
                or 0
            ) + 1
            if number > 100:
                raise AuthError(429, "scope_limit", "The scope history limit has been reached.")
            scope = DesignScope(
                design_project_id=project.id,
                number=number,
                specification=body.scope.model_dump(),
                proposed_by=user.id,
            )
            db.add(scope)
            await db.flush()
            project.approved_scope_id = project.fixture_scope_id = project.approved_version_id = (
                None
            )
            project.state = "scoping"
            metadata["scope_id"] = str(scope.id)
        elif action == "agree":
            assert isinstance(body, ScopeAgreement)
            latest = await db.scalar(
                select(DesignScope)
                .where(DesignScope.design_project_id == project.id)
                .order_by(DesignScope.number.desc())
                .limit(1)
            )
            if project.state != "scoping" or latest is None or latest.id != body.scope_id:
                raise AuthError(409, "stale_scope", "Agree only to the current scope proposal.")
            latest.agreed_at = datetime.now(UTC)
            latest.agreed_by = user.id
            project.approved_scope_id = latest.id
            project.state = "awaiting_payment"
            metadata["scope_id"] = str(latest.id)
        elif action == "fixture":
            assert isinstance(body, SimulationFixture)
            if (
                project.state != "awaiting_payment"
                or project.approved_scope_id is None
                or not settings.simulation_mode
                or project.mode != "simulation"
            ):
                raise AuthError(
                    409, "simulation_fixture_unavailable", "An agreed simulation scope is required."
                )
            project.fixture_scope_id = project.approved_scope_id
            project.state = "designing"
            metadata.update(
                scope_id=str(project.approved_scope_id),
                fixture="simulation_quote_and_paid_v1",
                live_work_authorized=False,
            )
        elif action == "publish":
            assert isinstance(body, PublishProof)
            await ensure_no_print(db, project)
            if (
                project.state not in {"designing", "customer_review", "approved"}
                or project.approved_scope_id is None
                or project.fixture_scope_id != project.approved_scope_id
            ):
                raise AuthError(
                    409,
                    "design_work_not_authorized",
                    "Activate the explicit simulation-paid fixture for the agreed scope first.",
                )
            proof = await required_file(db, storage, row, body.preview_file_id, "design_proof")
            model = (
                await required_file(
                    db, storage, row, body.manufacturing_file_id, "design_manufacturing"
                )
                if body.manufacturing_file_id
                else None
            )
            count = (
                await db.scalar(
                    select(func.count())
                    .select_from(DesignVersion)
                    .where(DesignVersion.design_project_id == project.id)
                )
                or 0
            )
            current_scope = await db.get(DesignScope, project.approved_scope_id)
            assert current_scope is not None
            scoped_count = (
                await db.scalar(
                    select(func.count())
                    .select_from(DesignVersion)
                    .where(
                        DesignVersion.design_project_id == project.id,
                        DesignVersion.scope_id == current_scope.id,
                    )
                )
                or 0
            )
            if count >= 100:
                raise AuthError(
                    429, "proof_history_limit", "The design proof history limit has been reached."
                )
            if scoped_count >= int(current_scope.specification["permitted_revisions"]) + 1:
                raise AuthError(
                    409,
                    "revision_limit",
                    "The agreed scope revision limit has been reached. Propose a new scope.",
                )
            version = DesignVersion(
                design_project_id=project.id,
                service_project_id=row.service_project_id,
                customer_id=row.customer_id,
                number=count + 1,
                scope_id=current_scope.id,
                preview_file_id=proof.id,
                manufacturing_file_id=model.id if model else None,
                manufacturing_ready=body.manufacturing_ready,
                release_notes=body.release_notes,
                published_by=user.id,
                specification_sha256=canonical_hash(
                    {
                        "brief": row.canonical_spec_sha256,
                        "scope_id": str(current_scope.id),
                        "scope": current_scope.specification,
                        "preview": proof.sha256,
                        "model": model.sha256 if model else None,
                        "number": count + 1,
                    }
                ),
            )
            db.add(version)
            await db.flush()
            project.latest_version_id = version.id
            project.approved_version_id = None
            project.state = "customer_review"
            metadata["design_version_id"] = str(version.id)
        elif action == "review":
            assert isinstance(body, ReviewProof)
            if (
                project.state != "customer_review"
                or project.latest_version_id != body.design_version_id
            ):
                raise AuthError(
                    409, "stale_design_version", "Review only the latest published proof."
                )
            reviewed_version = await db.get(DesignVersion, body.design_version_id)
            if reviewed_version is None or reviewed_version.scope_id != project.approved_scope_id:
                raise AuthError(409, "stale_scope", "This proof belongs to an older scope.")
            db.add(
                DesignReview(
                    design_project_id=project.id,
                    design_version_id=reviewed_version.id,
                    customer_id=user.id,
                    decision=body.decision,
                    feedback=body.feedback,
                )
            )
            project.state = "approved" if body.decision == "approved" else "designing"
            project.approved_version_id = (
                reviewed_version.id if body.decision == "approved" else None
            )
            metadata.update(design_version_id=str(reviewed_version.id), decision=body.decision)
        elif action == "convert":
            assert isinstance(body, ConvertDesign)
            version, _ = await approved_manufacturing(db, project)
            if version.id != body.design_version_id or row.service_type != "design_and_print":
                raise AuthError(
                    409,
                    "combined_design_required",
                    "Only the exact approved combined-service design can create a printing draft.",
                )
            if await linked_print(db, project) is not None:
                raise AuthError(
                    409,
                    "printing_draft_exists",
                    "This project already has a linked printing stage.",
                )
            printing = ServiceRequest(
                service_project_id=row.service_project_id,
                customer_id=row.customer_id,
                service_type="design_and_print",
                stage_kind="printing",
                source_design_version_id=version.id,
                mode="simulation",
                status="draft",
                version=1,
                revision=1,
                customer_notes="",
                canonical_spec_sha256="0" * 64,
            )
            db.add(printing)
            await db.flush()
            db.add(
                RequestItem(
                    request_id=printing.id, customer_id=printing.customer_id, request_revision=1
                )
            )
            await refresh_spec(db, printing, advance=False)
            await record_event(
                db,
                user,
                printing,
                "design.print_draft_created",
                None,
                metadata={"design_version_id": str(version.id)},
            )
            metadata.update(design_version_id=str(version.id), printing_request_id=str(printing.id))
        else:
            raise ValueError("Unknown design command")
        await changed(db, user, row, f"design.{action}", reason, metadata)
        return await detail(db, project, row, user)

    return await execute_command(
        factory,
        settings,
        principal,
        f"design.{action}:{identity}",
        key,
        body.model_dump(mode="json"),
        DesignDetail,
        operation,
        replay,
    )


def validate_delivery(row: ServiceRequest, kind: str) -> None:
    if (row.service_type == "custom_design" and kind != "digital") or (
        row.service_type == "design_and_print" and kind not in {"printing", "both"}
    ):
        raise AuthError(
            422,
            "invalid_delivery_scope",
            "Design-only includes digital delivery; combined service includes printing, with optional digital rights.",
        )


async def cleared_file(storage: PrivateStorage, file: UploadedFile) -> None:
    if (
        file.validation_status != "validated"
        or file.storage_state != "ready"
        or file.sha256 is None
    ):
        raise AuthError(422, "file_not_cleared", "All referenced files must finish validation.")
    try:
        await storage.verify(file.storage_key, file.size_bytes, file.sha256)
    except OSError:
        raise AuthError(
            422, "file_unavailable", "A private design file is missing or changed."
        ) from None


async def required_file(
    db: AsyncSession, storage: PrivateStorage, row: ServiceRequest, file_id: UUID, purpose: str
) -> UploadedFile:
    file = await db.get(UploadedFile, file_id)
    if (
        file is None
        or file.request_id != row.id
        or file.owner_id != row.customer_id
        or file.purpose != purpose
    ):
        raise AuthError(404, "file_not_found", "This design file could not be found.")
    await cleared_file(storage, file)
    return file


async def approved_manufacturing(
    db: AsyncSession, project: DesignProject
) -> tuple[DesignVersion, UploadedFile]:
    version = (
        await db.get(DesignVersion, project.approved_version_id)
        if project.approved_version_id
        else None
    )
    if (
        version is None
        or project.state != "approved"
        or version.id != project.latest_version_id
        or version.scope_id != project.approved_scope_id
        or project.fixture_scope_id != project.approved_scope_id
        or not version.manufacturing_ready
        or not version.manufacturing_file_id
    ):
        raise AuthError(
            409,
            "approved_manufacturing_required",
            "Approve the current manufacturing-ready simulation design first.",
        )
    file = await db.get(UploadedFile, version.manufacturing_file_id)
    assert file is not None
    return version, file


async def initialize_design(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    principal: Principal,
    request_id: UUID,
    key: str,
    body: VersionCommand,
) -> DesignDetail:
    from app.database.models import User
    from app.services.transactions import execute_command

    async def replay(db: AsyncSession, user: User) -> None:
        row = await locked_request(db, user, request_id, None)
        customer_only(row, user)

    async def operation(db: AsyncSession, user: User) -> DesignDetail:
        row = await locked_request(db, user, request_id, body.expected_version)
        customer_only(row, user)
        if row.status != "draft":
            raise AuthError(
                409, "draft_required", "Only existing design drafts can be initialized."
            )
        existed = await db.scalar(
            select(DesignProject.id).where(DesignProject.request_id == row.id)
        )
        project = await project_for_request(db, row)
        if existed is None:
            await changed(db, user, row, "design.initialized")
        return await detail(db, project, row, user)

    return await execute_command(
        factory,
        settings,
        principal,
        f"design.init:{request_id}",
        key,
        body.model_dump(),
        DesignDetail,
        operation,
        replay,
    )
