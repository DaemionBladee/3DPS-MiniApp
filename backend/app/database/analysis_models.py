"""M06 simulation profiles and immutable, fenced analysis provenance."""

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


class VirtualPrinterModel(Base):
    __tablename__ = "virtual_printer_models"
    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_virtual_model_version"),
        CheckConstraint(
            "technology = 'FDM' AND NOT calibrated AND simulation_only",
            name="ck_virtual_simulation",
        ),
        CheckConstraint("version > 0", name="ck_virtual_version"),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    technology: Mapped[str] = mapped_column(String(8), nullable=False, server_default="FDM")
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    calibrated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    simulation_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class SlicerProfile(Base):
    __tablename__ = "slicer_profiles"
    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_slicer_profile_version"),
        CheckConstraint(
            "version > 0 AND approval_status = 'approved' AND NOT calibrated AND simulation_only",
            name="ck_profile_simulation",
        ),
        CheckConstraint(
            "config_sha256 ~ '^[0-9a-f]{64}$' AND executable_sha256 ~ '^[0-9a-f]{64}$' AND worker_image ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_profile_checksums",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    virtual_printer_model_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("virtual_printer_models.id", ondelete="RESTRICT"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    material_key: Mapped[str] = mapped_column(String(32), nullable=False)
    quality_key: Mapped[str] = mapped_column(String(32), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    executable_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    worker_image: Mapped[str] = mapped_column(String(71), nullable=False)
    approval_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="approved"
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    calibrated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    simulation_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class ModelAnalysis(Base):
    __tablename__ = "model_analyses"
    __table_args__ = (
        UniqueConstraint("task_id", "lease_token", name="uq_analysis_attempt"),
        UniqueConstraint("id", "task_id", "lease_token", name="uq_analysis_task_attempt"),
        ForeignKeyConstraint(
            ["request_item_id", "request_id", "customer_id"],
            ["request_items.id", "request_items.request_id", "request_items.customer_id"],
            name="fk_analysis_item",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["uploaded_file_id", "request_id", "customer_id"],
            ["uploaded_files.id", "uploaded_files.request_id", "uploaded_files.owner_id"],
            name="fk_analysis_file",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "input_sha256 ~ '^[0-9a-f]{64}$' AND spec_sha256 ~ '^[0-9a-f]{64}$' AND request_revision > 0",
            name="ck_analysis_provenance",
        ),
        CheckConstraint("simulation_only", name="ck_analysis_simulation"),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    task_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("processing_tasks.id", ondelete="RESTRICT"), nullable=False
    )
    lease_token: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    customer_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_item_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    uploaded_file_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    spec_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    analyzer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    geometry: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    simulation_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SlicingRun(Base):
    __tablename__ = "slicing_runs"
    __table_args__ = (
        UniqueConstraint("task_id", "lease_token", name="uq_slicing_attempt"),
        UniqueConstraint("id", "task_id", name="uq_slicing_task_result"),
        ForeignKeyConstraint(
            ["model_analysis_id", "task_id", "lease_token"],
            ["model_analyses.id", "model_analyses.task_id", "model_analyses.lease_token"],
            name="fk_run_analysis_attempt",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "outcome IN ('estimated','manual_review') AND simulation_only", name="ck_run_simulation"
        ),
        CheckConstraint(
            "(outcome='estimated' AND estimate IS NOT NULL) OR (outcome='manual_review' AND estimate IS NULL)",
            name="ck_run_estimate",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    task_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("processing_tasks.id", ondelete="RESTRICT"), nullable=False
    )
    lease_token: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    model_analysis_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    slicer_profile_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("slicer_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    executable_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    worker_image: Mapped[str] = mapped_column(String(71), nullable=False)
    estimate: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    sandbox_evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    simulation_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
