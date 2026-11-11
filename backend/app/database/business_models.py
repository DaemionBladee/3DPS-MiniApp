"""M03 tables only; later domain relationships arrive in their own migrations."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models import Base
from app.domain.types import RequestStatus, ServiceType, StageKind


class ServiceProject(Base):
    __tablename__ = "service_projects"
    __table_args__ = (
        UniqueConstraint("id", "customer_id", "kind", "mode", name="uq_project_lineage"),
        Index("ix_service_projects_customer_created", "customer_id", "created_at", "id"),
        CheckConstraint(
            "kind IN ('printing','custom_design','design_and_print')", name="ck_project_kind"
        ),
        CheckConstraint("mode = 'simulation'", name="ck_project_mode"),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    customer_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[ServiceType] = mapped_column(String(32), nullable=False)
    mode: Mapped[Literal["simulation"]] = mapped_column(
        String(16), nullable=False, server_default="simulation"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ServiceRequest(Base):
    __tablename__ = "service_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["service_project_id", "customer_id", "service_type", "mode"],
            [
                "service_projects.id",
                "service_projects.customer_id",
                "service_projects.kind",
                "service_projects.mode",
            ],
            name="fk_request_project_lineage",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("service_project_id", "stage_kind", name="uq_request_project_stage"),
        Index("ix_service_requests_customer_created", "customer_id", "created_at", "id"),
        Index("ix_service_requests_created", "created_at", "id"),
        CheckConstraint(
            "(service_type = 'printing' AND stage_kind = 'printing') OR (service_type IN ('custom_design','design_and_print') AND stage_kind = 'design')",
            name="ck_request_initial_stage",
        ),
        CheckConstraint("status IN ('draft','cancelled')", name="ck_request_status"),
        CheckConstraint("mode = 'simulation'", name="ck_request_mode"),
        CheckConstraint("version > 0 AND revision > 0", name="ck_request_versions"),
        CheckConstraint("canonical_spec_sha256 ~ '^[0-9a-f]{64}$'", name="ck_request_hash"),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    service_project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    customer_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    service_type: Mapped[ServiceType] = mapped_column(String(32), nullable=False)
    stage_kind: Mapped[StageKind] = mapped_column(String(16), nullable=False)
    mode: Mapped[Literal["simulation"]] = mapped_column(
        String(16), nullable=False, server_default="simulation"
    )
    status: Mapped[RequestStatus] = mapped_column(
        String(32), nullable=False, server_default="draft"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    canonical_spec_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_notes: Mapped[str] = mapped_column(String(2000), nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("service_requests.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    metadata_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (CheckConstraint("status = 'pending'", name="ck_outbox_pending"),)
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    event_key: Mapped[UUID] = mapped_column(
        Uuid, unique=True, nullable=False, server_default=text("gen_random_uuid()")
    )
    audit_log_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("audit_logs.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    recipient_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_minimized: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    action: Mapped[str] = mapped_column(String(100), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
