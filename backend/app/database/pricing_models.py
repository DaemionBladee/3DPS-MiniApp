"""M07 immutable simulation policies, availability fixtures and Decimal cost snapshots."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models import Base


class PricingPolicy(Base):
    __tablename__ = "pricing_policies"
    __table_args__ = (
        UniqueConstraint("stage_kind", "version", name="uq_pricing_policy_version"),
        CheckConstraint(
            "stage_kind IN ('printing','design') AND version>0 AND mode='simulation'",
            name="ck_pricing_policy_mode",
        ),
        CheckConstraint(
            "(stage_kind='printing' AND currency_code='MMK') OR (stage_kind='design' AND currency_code='XTR')",
            name="ck_pricing_policy_currency",
        ),
        CheckConstraint("checksum ~ '^[0-9a-f]{64}$'", name="ck_pricing_policy_hash"),
        Index(
            "uq_active_pricing_stage", "stage_kind", unique=True, postgresql_where=text("active")
        ),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    stage_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, server_default="simulation")
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PricingAvailabilityFixture(Base):
    __tablename__ = "pricing_availability_fixtures"
    __table_args__ = (
        UniqueConstraint("version", name="uq_pricing_fixture_version"),
        CheckConstraint(
            "mode='simulation' AND version>0 AND expires_at>created_at",
            name="ck_pricing_fixture_mode",
        ),
        CheckConstraint("checksum ~ '^[0-9a-f]{64}$'", name="ck_pricing_fixture_hash"),
        Index("uq_active_pricing_fixture", "active", unique=True, postgresql_where=text("active")),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, server_default="simulation")
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PricingEstimate(Base):
    __tablename__ = "pricing_estimates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["request_id", "customer_id", "stage_kind"],
            ["service_requests.id", "service_requests.customer_id", "service_requests.stage_kind"],
            name="fk_estimate_request",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("request_id", "number", name="uq_pricing_estimate_number"),
        UniqueConstraint("id", "request_id", "customer_id", name="uq_pricing_estimate_lineage"),
        CheckConstraint(
            "kind='test_estimate' AND mode='simulation' AND NOT binding_authorized",
            name="ck_estimate_nonbinding",
        ),
        CheckConstraint(
            "(stage_kind='printing' AND currency_code='MMK' AND payment_category='physical_goods') OR (stage_kind='design' AND currency_code='XTR' AND payment_category='digital_goods')",
            name="ck_estimate_currency_category",
        ),
        CheckConstraint(
            "number>0 AND request_revision>0 AND expires_at>created_at", name="ck_estimate_bounds"
        ),
        CheckConstraint(
            "spec_sha256 ~ '^[0-9a-f]{64}$' AND source_sha256 ~ '^[0-9a-f]{64}$' AND policy_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_estimate_hashes",
        ),
        CheckConstraint(
            "eligibility_decision IN ('pass','review','error')", name="ck_estimate_eligibility"
        ),
        CheckConstraint(
            "(total IS NULL AND subtotal IS NULL) OR (total IS NOT NULL AND subtotal IS NOT NULL AND total>=0 AND total<=1000000000000000 AND subtotal>=0 AND (currency_code!='XTR' OR total=trunc(total)))",
            name="ck_estimate_money",
        ),
        Index("ix_pricing_estimate_request", "request_id", "number"),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    customer_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    stage_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False, server_default="test_estimate")
    mode: Mapped[str] = mapped_column(String(16), nullable=False, server_default="simulation")
    binding_authorized: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    payment_category: Mapped[str] = mapped_column(String(24), nullable=False)
    request_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    spec_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    pricing_policy_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("pricing_policies.id", ondelete="RESTRICT"), nullable=False
    )
    policy_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    availability_fixture_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("pricing_availability_fixtures.id", ondelete="RESTRICT")
    )
    design_scope_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("design_scopes.id", ondelete="RESTRICT")
    )
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    eligibility_decision: Mapped[str] = mapped_column(String(16), nullable=False)
    eligibility_rules: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    unknown_costs: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    assumptions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(28, 8))
    total: Mapped[Decimal | None] = mapped_column(Numeric(28, 8))
    created_by: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PricingEstimateLine(Base):
    __tablename__ = "pricing_estimate_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["estimate_id", "request_id", "customer_id"],
            [
                "pricing_estimates.id",
                "pricing_estimates.request_id",
                "pricing_estimates.customer_id",
            ],
            name="fk_pricing_line_estimate",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["request_item_id", "request_id", "customer_id"],
            ["request_items.id", "request_items.request_id", "request_items.customer_id"],
            name="fk_pricing_line_item",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(item_kind='design_service' AND request_item_id IS NULL) OR item_kind='print_item'",
            name="ck_pricing_line_kind",
        ),
        CheckConstraint(
            "amount IS NULL OR (component_code='rounding_adjustment' OR amount>=0)",
            name="ck_pricing_line_money",
        ),
        CheckConstraint(
            "(quantity IS NULL OR quantity>=0) AND (rate IS NULL OR rate>=0) AND position>0",
            name="ck_pricing_line_parameters",
        ),
        UniqueConstraint("estimate_id", "position", name="uq_pricing_line_position"),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    estimate_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    customer_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_item_id: Mapped[UUID | None] = mapped_column(Uuid)
    item_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    component_code: Mapped[str] = mapped_column(String(80), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(28, 8))
    rate: Mapped[Decimal | None] = mapped_column(Numeric(28, 8))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(28, 8))
    assumption: Mapped[str | None] = mapped_column(String(100))
