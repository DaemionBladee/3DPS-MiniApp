"""Owner-only, version-checked simulation policy and fixture publication."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.pricing_schemas import (
    AvailabilityResponse,
    PolicyResponse,
    PublishAvailability,
    PublishPolicy,
)
from app.core.config import Settings
from app.core.errors import AuthError
from app.database.business_models import AuditLog, NotificationOutbox
from app.database.models import User
from app.database.pricing_models import PricingAvailabilityFixture, PricingPolicy
from app.pricing.policies import PricingPolicyDefinition, checksum
from app.services.analysis import owner
from app.services.auth import Principal
from app.services.transactions import execute_command

PRICING_LOCK = 7007001


async def configuration_lock(db: AsyncSession) -> None:
    await db.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": PRICING_LOCK})


async def config_event(
    db: AsyncSession,
    user: User,
    target: PricingPolicy | PricingAvailabilityFixture,
    action: str,
    reason: str,
) -> None:
    data = {
        "id": str(target.id),
        "version": target.version,
        "checksum": target.checksum,
        "mode": "simulation",
    }
    audit = AuditLog(
        actor_user_id=user.id,
        entity_kind="pricing_policy" if isinstance(target, PricingPolicy) else "pricing_fixture",
        entity_id=None,
        pricing_policy_id=target.id if isinstance(target, PricingPolicy) else None,
        availability_fixture_id=target.id
        if isinstance(target, PricingAvailabilityFixture)
        else None,
        action=action,
        reason=reason,
        metadata_snapshot=data,
    )
    db.add(audit)
    await db.flush()
    db.add(
        NotificationOutbox(
            audit_log_id=audit.id,
            recipient_user_id=user.id,
            event_type=action,
            payload_minimized=data,
        )
    )
    await db.flush()


async def publish_policy(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    principal: Principal,
    key: str,
    body: PublishPolicy,
) -> PolicyResponse:
    async def authorize(db: AsyncSession, user: User) -> None:
        owner(user)

    async def operation(db: AsyncSession, user: User) -> PolicyResponse:
        owner(user)
        await configuration_lock(db)
        stage = body.configuration.stage_kind
        version = (
            await db.scalar(
                select(func.max(PricingPolicy.version)).where(PricingPolicy.stage_kind == stage)
            )
            or 0
        )
        if body.expected_version != version:
            raise AuthError(
                409,
                "stale_policy_version",
                "Reload the current policy before publishing a new version.",
            )
        config = body.configuration.model_dump(mode="json")
        await db.execute(
            update(PricingPolicy)
            .where(PricingPolicy.stage_kind == stage, PricingPolicy.active)
            .values(active=False)
        )
        row = PricingPolicy(
            stage_kind=stage,
            version=version + 1,
            currency_code=body.configuration.currency_code,
            configuration=config,
            checksum=checksum(config),
            created_by=user.id,
            reason=body.reason,
        )
        db.add(row)
        await db.flush()
        await config_event(db, user, row, "pricing.policy_published", body.reason)
        return PolicyResponse.model_validate(row)

    return await execute_command(
        factory,
        settings,
        principal,
        "pricing.policy.publish",
        key,
        body.model_dump(mode="json"),
        PolicyResponse,
        operation,
        authorize,
    )


async def publish_availability(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    principal: Principal,
    key: str,
    body: PublishAvailability,
) -> AvailabilityResponse:
    async def authorize(db: AsyncSession, user: User) -> None:
        owner(user)

    async def operation(db: AsyncSession, user: User) -> AvailabilityResponse:
        owner(user)
        await configuration_lock(db)
        version = await db.scalar(select(func.max(PricingAvailabilityFixture.version))) or 0
        if body.expected_version != version:
            raise AuthError(
                409,
                "stale_fixture_version",
                "Reload the current simulation fixture before publishing.",
            )
        reason = PublishPolicy.safe_reason(body.reason)
        config = body.configuration.model_dump(mode="json")
        now = datetime.now(UTC)
        await db.execute(
            update(PricingAvailabilityFixture)
            .where(PricingAvailabilityFixture.active)
            .values(active=False)
        )
        row = PricingAvailabilityFixture(
            version=version + 1,
            configuration=config,
            checksum=checksum(config),
            created_by=user.id,
            reason=reason,
            created_at=now,
            expires_at=now + timedelta(seconds=body.configuration.ttl_seconds),
        )
        db.add(row)
        await db.flush()
        await config_event(db, user, row, "pricing.availability_published", reason)
        return AvailabilityResponse.model_validate(row)

    return await execute_command(
        factory,
        settings,
        principal,
        "pricing.fixture.publish",
        key,
        body.model_dump(mode="json"),
        AvailabilityResponse,
        operation,
        authorize,
    )


def hypothetical_policy(
    stage: str, profile_ids: list[str] | None = None
) -> PricingPolicyDefinition:
    """Explicitly requested synthetic demonstration values, never commercial defaults."""
    common: dict[str, Any] = {
        "stage_kind": stage,
        "currency_code": "MMK" if stage == "printing" else "XTR",
        "rounding_step": "1",
        "rounding_mode": "CEILING",
        "estimate_ttl_seconds": 3600,
        "risk_fraction": "0.10",
        "gross_margin": "0.20",
        "tax_fraction": "0",
        "minimum_total": "0",
        "zero_cost_reasons": {
            "tax_fraction": "Hypothetical fixture assumes no tax; tax policy is not approved.",
            "support_overhead_fraction": "Virtual fixture disables supports; manufacturability still needs review.",
            "deliverable_fee": "Hypothetical deliverables are included in design labor.",
            "usage_rights_fee": "Hypothetical personal usage is included; no digital delivery is authorized.",
        },
    }
    if stage == "printing":
        common.update(
            material_per_g={"dev-pla": "1", "dev-petg": "2"},
            machine_per_hour="60",
            labor_per_hour="120",
            setup_hours="0.10",
            postprocess_hours_per_item="0.02",
            electricity_per_kwh="20",
            average_power_kw="0.10",
            overhead_per_hour="10",
            waste_fraction="0.05",
            support_overhead_fraction="0",
            shipping_flat="30",
            eligibility={
                "approved_materials": ["dev-pla", "dev-petg"],
                "approved_qualities": ["dev-standard", "dev-fine"],
                "approved_profile_ids": profile_ids or [],
                "max_quantity": 2,
                "max_models": 1,
                "max_print_seconds": 3600,
                "max_total": "5000",
                "minimum_lead_days": 7,
                "max_tolerance_mm": "0.5",
            },
        )
    else:
        common.update(
            design_per_hour="30",
            complexity_multipliers={"simple": "1", "standard": "1.25", "complex": "1.5"},
            deliverable_fee="0",
            usage_rights_fees={"personal": "0", "commercial": "5", "exclusive": "10"},
        )
    return PricingPolicyDefinition.model_validate(common)
