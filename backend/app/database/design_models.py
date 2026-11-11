"""M05 design intake, immutable proposals/proofs and exact-version reviews."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
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


class DesignProject(Base):
    __tablename__ = "design_projects"
    __table_args__ = (
        ForeignKeyConstraint(
            ["request_id", "customer_id", "stage_kind"],
            ["service_requests.id", "service_requests.customer_id", "service_requests.stage_kind"],
            name="fk_design_request",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "customer_id", name="uq_design_customer"),
        ForeignKeyConstraint(
            ["fixture_scope_id", "id"],
            ["design_scopes.id", "design_scopes.design_project_id"],
            name="fk_fixture_scope",
            use_alter=True,
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "service_project_id", "customer_id", name="uq_design_lineage"),
        CheckConstraint("stage_kind = 'design'", name="ck_design_stage"),
        CheckConstraint(
            "state IN ('draft','brief_received','scoping','awaiting_payment','designing','customer_review','approved')",
            name="ck_design_state",
        ),
        CheckConstraint("mode = 'simulation'", name="ck_design_simulation"),
        ForeignKeyConstraint(
            ["approved_scope_id", "id"],
            ["design_scopes.id", "design_scopes.design_project_id"],
            name="fk_design_approved_scope",
            use_alter=True,
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["latest_version_id", "id"],
            ["design_versions.id", "design_versions.design_project_id"],
            name="fk_design_latest_version",
            use_alter=True,
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["approved_version_id", "id"],
            ["design_versions.id", "design_versions.design_project_id"],
            name="fk_design_approved_version",
            use_alter=True,
            ondelete="RESTRICT",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    request_id: Mapped[UUID] = mapped_column(Uuid, unique=True, nullable=False)
    service_project_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("service_projects.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    stage_kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default="design")
    mode: Mapped[str] = mapped_column(String(16), nullable=False, server_default="simulation")
    state: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    brief: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    approved_scope_id: Mapped[UUID | None] = mapped_column(Uuid)
    latest_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    approved_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    fixture_scope_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DesignScope(Base):
    __tablename__ = "design_scopes"
    __table_args__ = (
        UniqueConstraint("design_project_id", "number", name="uq_scope_number"),
        UniqueConstraint("id", "design_project_id", name="uq_scope_project"),
        CheckConstraint("number > 0", name="ck_scope_number"),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    design_project_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("design_projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    specification: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    proposed_by: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    agreed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    agreed_by: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DesignVersion(Base):
    __tablename__ = "design_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["design_project_id", "service_project_id", "customer_id"],
            [
                "design_projects.id",
                "design_projects.service_project_id",
                "design_projects.customer_id",
            ],
            name="fk_version_design_lineage",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["scope_id", "design_project_id"],
            ["design_scopes.id", "design_scopes.design_project_id"],
            name="fk_version_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("design_project_id", "number", name="uq_design_version_number"),
        UniqueConstraint("id", "design_project_id", name="uq_design_version_project"),
        UniqueConstraint(
            "id", "service_project_id", "customer_id", name="uq_version_service_lineage"
        ),
        CheckConstraint(
            "number > 0 AND specification_sha256 ~ '^[0-9a-f]{64}$'", name="ck_design_version_hash"
        ),
        CheckConstraint(
            "manufacturing_ready = (manufacturing_file_id IS NOT NULL)",
            name="ck_design_manufacturing",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    design_project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    service_project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    customer_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    scope_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    preview_file_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("uploaded_files.id", ondelete="RESTRICT"), nullable=False
    )
    manufacturing_file_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("uploaded_files.id", ondelete="RESTRICT")
    )
    manufacturing_ready: Mapped[bool] = mapped_column(Boolean, nullable=False)
    release_notes: Mapped[str] = mapped_column(String(2000), nullable=False)
    specification_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    published_by: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DesignReview(Base):
    __tablename__ = "design_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["design_version_id", "design_project_id"],
            ["design_versions.id", "design_versions.design_project_id"],
            name="fk_review_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["design_project_id", "customer_id"],
            ["design_projects.id", "design_projects.customer_id"],
            name="fk_review_customer",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "decision IN ('approved','changes_requested')", name="ck_design_review_decision"
        ),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    design_project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    design_version_id: Mapped[UUID] = mapped_column(Uuid, unique=True, nullable=False)
    customer_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    feedback: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
