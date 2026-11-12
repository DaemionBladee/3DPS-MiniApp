"""M04 intake relationships and durable upload reservations; no worker execution."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
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


class RequestItem(Base):
    __tablename__ = "request_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["request_id", "customer_id", "stage_kind"],
            ["service_requests.id", "service_requests.customer_id", "service_requests.stage_kind"],
            ondelete="RESTRICT",
            name="fk_item_print_request",
        ),
        ForeignKeyConstraint(
            ["model_file_id", "id", "request_id", "customer_id"],
            [
                "uploaded_files.id",
                "uploaded_files.request_item_id",
                "uploaded_files.request_id",
                "uploaded_files.owner_id",
            ],
            ondelete="RESTRICT",
            use_alter=True,
            name="fk_item_current_model",
        ),
        UniqueConstraint("id", "request_id", "customer_id", name="uq_item_request_owner"),
        CheckConstraint("stage_kind = 'printing'", name="ck_item_printing"),
        CheckConstraint(
            "quantity BETWEEN 1 AND 1000 AND request_revision > 0", name="ck_item_spec_bounds"
        ),
        CheckConstraint("unit_key IN ('mm','cm','inch','um','ft','m')", name="ck_item_units"),
        CheckConstraint("(dimension_x_mm IS NULL AND dimension_y_mm IS NULL AND dimension_z_mm IS NULL) OR (dimension_x_mm > 0 AND dimension_x_mm <= 1000000 AND dimension_y_mm > 0 AND dimension_y_mm <= 1000000 AND dimension_z_mm > 0 AND dimension_z_mm <= 1000000 AND dimension_x_mm IS NOT NULL AND dimension_y_mm IS NOT NULL AND dimension_z_mm IS NOT NULL)", name="ck_item_dimensions"),
        CheckConstraint("dimension_tolerance_mm > 0 AND dimension_tolerance_mm <= 100", name="ck_item_dimension_tolerance"),
        Index("ix_request_items_request", "request_id", "active"),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    customer_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    stage_kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default="printing")
    request_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    model_file_id: Mapped[UUID | None] = mapped_column(Uuid)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    description: Mapped[str] = mapped_column(String(300), nullable=False, server_default="")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    material_key: Mapped[str | None] = mapped_column(String(32))
    color_key: Mapped[str | None] = mapped_column(String(32))
    quality_key: Mapped[str | None] = mapped_column(String(32))
    unit_key: Mapped[str] = mapped_column(String(8), nullable=False, server_default="mm")
    unit_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    special_requirements: Mapped[str] = mapped_column(
        String(2000), nullable=False, server_default=""
    )
    dimension_x_mm: Mapped[float | None] = mapped_column(Float)
    dimension_y_mm: Mapped[float | None] = mapped_column(Float)
    dimension_z_mm: Mapped[float | None] = mapped_column(Float)
    dimension_tolerance_mm: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.5")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    __table_args__ = (
        ForeignKeyConstraint(
            ["request_item_id", "request_id", "owner_id"],
            ["request_items.id", "request_items.request_id", "request_items.customer_id"],
            name="fk_file_item_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["request_id", "owner_id"],
            ["service_requests.id", "service_requests.customer_id"],
            name="fk_file_request_customer",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(purpose = 'model' AND request_item_id IS NOT NULL) OR (purpose IN ('design_reference','design_proof','design_manufacturing') AND request_item_id IS NULL)",
            name="ck_file_purpose_item",
        ),
        UniqueConstraint(
            "id", "request_item_id", "request_id", "owner_id", name="uq_file_item_lineage"
        ),
        UniqueConstraint("id", "request_id", "owner_id", name="uq_file_request_owner"),
        UniqueConstraint("owner_id", "request_id", "upload_key", name="uq_upload_command"),
        CheckConstraint(
            "validation_status IN ('pending','validated','rejected','removed')",
            name="ck_file_validation",
        ),
        CheckConstraint(
            "storage_state IN ('receiving','ready','delete_pending','deleted')",
            name="ck_file_storage",
        ),
        CheckConstraint(
            "reserved_bytes > 0 AND size_bytes >= 0 AND request_revision > 0",
            name="ck_file_size_revision",
        ),
        CheckConstraint(
            "expected_sha256 ~ '^[0-9a-f]{64}$' AND (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$')",
            name="ck_file_hash",
        ),
        CheckConstraint(
            "validation_status != 'validated' OR (sha256 IS NOT NULL AND sha256 = expected_sha256 AND size_bytes = reserved_bytes AND format IS NOT NULL)",
            name="ck_file_validated",
        ),
        Index("ix_uploaded_files_quota", "owner_id", "request_id", "storage_state"),
        Index("ix_uploaded_files_cleanup", "storage_state", "lease_expires_at"),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_item_id: Mapped[UUID | None] = mapped_column(Uuid)
    purpose: Mapped[str] = mapped_column(String(24), nullable=False, server_default="model")
    uploader_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", name="fk_file_uploader", ondelete="RESTRICT")
    )
    owner_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_version: Mapped[int] = mapped_column(Integer, nullable=False)
    upload_key: Mapped[str] = mapped_column(String(128), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    lease_token: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reserved_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    expected_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    original_name: Mapped[str] = mapped_column(String(200), nullable=False)
    format: Mapped[str | None] = mapped_column(String(8))
    mime_detected: Mapped[str | None] = mapped_column(String(100))
    format_details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    validation_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
    storage_state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="receiving"
    )
    failure_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProcessingTask(Base):
    __tablename__ = "processing_tasks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["uploaded_file_id", "request_id", "customer_id"],
            ["uploaded_files.id", "uploaded_files.request_id", "uploaded_files.owner_id"],
            name="fk_task_file_lineage",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "request_id",
            "request_revision",
            "uploaded_file_id",
            "kind",
            name="uq_task_revision_file_kind",
        ),
        CheckConstraint("state != 'succeeded' OR (result_run_id IS NOT NULL AND started_at IS NOT NULL AND completed_at IS NOT NULL)", name="ck_task_success"),
        CheckConstraint("state != 'leased' OR result_run_id IS NULL", name="ck_task_running_result"),
        CheckConstraint("state != 'failed' OR (error_code IS NOT NULL AND completed_at IS NOT NULL)", name="ck_task_failure"),
        CheckConstraint("state IN ('pending','leased','succeeded','failed','superseded')", name="ck_task_state"),
        CheckConstraint("attempts >= 0 AND max_attempts BETWEEN 3 AND 6 AND attempts <= max_attempts", name="ck_task_attempts"),
        CheckConstraint("(state = 'leased' AND lease_token IS NOT NULL AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL) OR (state != 'leased' AND lease_token IS NULL AND lease_owner IS NULL AND lease_expires_at IS NULL)", name="ck_task_lease"),
        ForeignKeyConstraint(["result_run_id", "id"], ["slicing_runs.id", "slicing_runs.task_id"], name="fk_task_result", use_alter=True, ondelete="RESTRICT"),
        CheckConstraint(
            "kind = 'model_analysis' AND request_revision > 0", name="ck_task_kind_revision"
        ),
        CheckConstraint("spec_sha256 ~ '^[0-9a-f]{64}$'", name="ck_task_hash"),
        Index("ix_task_claim", "state", "next_available_at", "created_at"),
        Index("ix_processing_tasks_request_revision", "request_id", "request_revision"),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    uploaded_file_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    customer_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    spec_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, server_default="model_analysis")
    state: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_owner: Mapped[str | None] = mapped_column(String(80))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    selected_profile_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("slicer_profiles.id", ondelete="RESTRICT"))
    result_run_id: Mapped[UUID | None] = mapped_column(Uuid)
