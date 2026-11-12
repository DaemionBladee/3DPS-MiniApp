"""Authorized, idempotent immutable test estimates; no offer or payment transitions."""

from dataclasses import asdict
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.pricing_schemas import (
    CustomerEstimate,
    DesignPricingBasis,
    EstimatePointer,
    EvaluatePrice,
    OwnerEstimate,
    PricingLineResponse,
)
from app.core.config import Settings
from app.core.errors import AuthError
from app.database.business_models import ServiceRequest
from app.database.models import User
from app.database.pricing_models import PricingEstimate, PricingEstimateLine, PricingPolicy
from app.pricing.configuration import configuration_lock
from app.pricing.eligibility import evaluate
from app.pricing.engine import design_cost, printing_cost
from app.pricing.policies import PricingPolicyDefinition, checksum
from app.pricing.sources import build_sources
from app.services.analysis import owner
from app.services.auth import Principal
from app.services.requests import locked_request, record_event
from app.services.transactions import execute_command


def require_simulation(settings: Settings) -> None:
    if (
        not settings.simulation_mode
        or settings.binding_quotes_enabled
        or settings.auto_quote_enabled
        or settings.live_payments_enabled
        or settings.real_printing_enabled
    ):
        raise AuthError(
            409, "live_pricing_unavailable", "M07 creates nonbinding simulation estimates only."
        )


async def active_policy(db: AsyncSession, stage: str) -> PricingPolicy | None:
    return await db.scalar(
        select(PricingPolicy)
        .where(PricingPolicy.stage_kind == stage, PricingPolicy.active)
        .limit(1)
    )


def validated_policy(row: PricingPolicy) -> PricingPolicyDefinition:
    try:
        value = PricingPolicyDefinition.model_validate(row.configuration)
        if (
            checksum(row.configuration) != row.checksum
            or value.stage_kind != row.stage_kind
            or value.currency_code != row.currency_code
            or row.mode != "simulation"
        ):
            raise ValueError("Policy integrity failed")
        return value
    except ValueError:
        raise AuthError(
            422, "pricing_policy_invalid", "The simulation pricing policy is incomplete or invalid."
        ) from None


async def evaluate_request(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    principal: Principal,
    key: str,
    request_id: UUID,
    body: EvaluatePrice,
    *,
    owner_route: bool = False,
) -> EstimatePointer:
    async def authorize(db: AsyncSession, user: User) -> None:
        if owner_route:
            owner(user)
        row = await locked_request(db, user, request_id, None)
        if row.stage_kind == "design":
            owner(user)

    async def operation(db: AsyncSession, user: User) -> EstimatePointer:
        require_simulation(settings)
        if owner_route:
            owner(user)
        await configuration_lock(db)
        row = await locked_request(db, user, request_id, body.expected_version)
        if row.stage_kind == "design":
            owner(user)
        if row.status not in {"submitted", "analyzing", "manual_review"}:
            raise AuthError(
                409,
                "submitted_request_required",
                "Submit the current request specification before requesting an estimate.",
            )
        policy_row = await active_policy(db, row.stage_kind)
        if policy_row is None:
            raise AuthError(
                409,
                "pricing_policy_missing",
                "The Owner has not configured a simulation pricing policy.",
            )
        policy = validated_policy(policy_row)
        now = (await db.execute(select(func.clock_timestamp()))).scalar_one()
        source, items, availability = await build_sources(db, row, now, body.design_basis)
        source["policy"] = {
            "id": str(policy_row.id),
            "version": policy_row.version,
            "checksum": policy_row.checksum,
        }
        digest = checksum(source)
        previous = await db.scalar(
            select(PricingEstimate)
            .where(PricingEstimate.request_id == row.id)
            .order_by(PricingEstimate.number.desc())
            .limit(1)
        )
        if previous and previous.source_sha256 == digest and previous.expires_at > now:
            return EstimatePointer(
                estimate_id=previous.id, request_id=row.id, number=previous.number
            )
        if row.stage_kind == "printing":
            costs = printing_cost(policy, items, row.fulfillment_method)
        else:
            assert body.design_basis is not None
            costs = design_cost(
                policy, body.design_basis.model_dump(mode="json"), source["scope"]["specification"]
            )
        eligibility = evaluate(
            policy,
            costs,
            items,
            service_type=row.service_type,
            special_notes=bool(row.customer_notes.strip()),
            availability=availability,
            today=now.date(),
            design_scope_agreed=bool(source.get("scope", {}).get("agreed_at")),
        )
        if row.service_type == "design_and_print" and row.stage_kind == "design":
            costs.assumptions.add("combined_payment_classification_pending")
        fixture_id = UUID(source["availability"]["id"]) if source.get("availability") else None
        estimate = PricingEstimate(
            request_id=row.id,
            customer_id=row.customer_id,
            stage_kind=row.stage_kind,
            number=previous.number + 1 if previous else 1,
            currency_code=policy.currency_code,
            payment_category="physical_goods" if row.stage_kind == "printing" else "digital_goods",
            request_revision=row.revision,
            spec_sha256=row.canonical_spec_sha256,
            source_sha256=digest,
            pricing_policy_id=policy_row.id,
            policy_checksum=policy_row.checksum,
            availability_fixture_id=fixture_id,
            design_scope_id=body.design_basis.scope_id if body.design_basis else None,
            policy_snapshot=policy_row.configuration,
            source_snapshot=source,
            eligibility_decision=eligibility.decision,
            eligibility_rules=[asdict(rule) for rule in eligibility.rules],
            unknown_costs=sorted(costs.unknown),
            assumptions=sorted(costs.assumptions),
            subtotal=costs.subtotal,
            total=costs.total,
            created_by=user.id,
            created_at=now,
            expires_at=now + timedelta(seconds=policy.estimate_ttl_seconds),
        )
        db.add(estimate)
        await db.flush()
        for position, line in enumerate(costs.lines, 1):
            db.add(
                PricingEstimateLine(
                    estimate_id=estimate.id,
                    request_id=row.id,
                    customer_id=row.customer_id,
                    request_item_id=UUID(line.item_id) if line.item_id else None,
                    item_kind="print_item" if row.stage_kind == "printing" else "design_service",
                    position=position,
                    component_code=line.code,
                    quantity=line.quantity,
                    rate=line.rate,
                    amount=line.amount,
                    assumption=line.assumption,
                )
            )
        await db.flush()
        await record_event(
            db,
            user,
            row,
            "pricing.estimate_evaluated",
            row.status,
            metadata={
                "estimate_id": str(estimate.id),
                "estimate_number": estimate.number,
                "pricing_policy_id": str(policy_row.id),
                "policy_checksum": policy_row.checksum,
                "source_sha256": digest,
                "kind": "test_estimate",
                "binding_authorized": False,
                "eligibility_decision": eligibility.decision,
            },
        )
        return EstimatePointer(estimate_id=estimate.id, request_id=row.id, number=estimate.number)

    return await execute_command(
        factory,
        settings,
        principal,
        "pricing.evaluate",
        key,
        {"request_id": str(request_id), **body.model_dump(mode="json")},
        EstimatePointer,
        operation,
        authorize,
    )


async def stale_reasons(
    db: AsyncSession, row: ServiceRequest, estimate: PricingEstimate
) -> list[str]:
    reasons = []
    now = (await db.execute(select(func.clock_timestamp()))).scalar_one()
    if estimate.expires_at <= now:
        reasons.append("estimate_expired")
    if (
        row.revision != estimate.request_revision
        or row.canonical_spec_sha256 != estimate.spec_sha256
    ):
        reasons.append("request_revision_changed")
    newest = await db.scalar(
        select(func.max(PricingEstimate.number)).where(PricingEstimate.request_id == row.id)
    )
    if newest != estimate.number:
        reasons.append("estimate_superseded")
    policy = await active_policy(db, row.stage_kind)
    if (
        policy is None
        or policy.id != estimate.pricing_policy_id
        or policy.checksum != estimate.policy_checksum
    ):
        reasons.append("pricing_policy_changed")
    else:
        try:
            validated_policy(policy)
            basis = (
                DesignPricingBasis.model_validate(estimate.source_snapshot["design_basis"])
                if row.stage_kind == "design"
                else None
            )
            source, _, _ = await build_sources(db, row, now, basis)
            source["policy"] = {
                "id": str(policy.id),
                "version": policy.version,
                "checksum": policy.checksum,
            }
            if checksum(source) != estimate.source_sha256:
                reasons.append("source_or_availability_changed")
        except (ValueError, KeyError, AuthError):
            reasons.append("source_or_scope_unavailable")
    return reasons


async def project_estimate(
    db: AsyncSession, row: ServiceRequest, estimate: PricingEstimate, *, private: bool
) -> CustomerEstimate | OwnerEstimate:
    stale = await stale_reasons(db, row, estimate)
    policy = await db.get(PricingPolicy, estimate.pricing_policy_id)
    assert policy is not None
    values: dict[str, Any] = {
        "id": estimate.id,
        "request_id": row.id,
        "number": estimate.number,
        "stage_kind": estimate.stage_kind,
        "currency_code": estimate.currency_code,
        "current": not stale,
        "priced": estimate.total is not None and not stale,
        "estimated_total": estimate.total if not stale else None,
        "policy_version": policy.version,
        "request_revision": estimate.request_revision,
        "decision": estimate.eligibility_decision if not stale else "review",
        "review_reasons": [r["code"] for r in estimate.eligibility_rules if r["result"] != "pass"],
        "stale_reasons": stale,
        "assumptions": estimate.assumptions,
        "created_at": estimate.created_at,
        "expires_at": estimate.expires_at,
    }
    if not private:
        values["assumptions"] = [
            assumption
            for assumption in estimate.assumptions
            if not assumption.startswith("explicit_zero_")
        ]
        # Deliberately omit policy configuration, rates, margins and internal reasons.
        values["review_reasons"] = ["owner_review_required"] if values["review_reasons"] else []
        return CustomerEstimate(**values)
    lines = (
        await db.scalars(
            select(PricingEstimateLine)
            .where(PricingEstimateLine.estimate_id == estimate.id)
            .order_by(PricingEstimateLine.position)
        )
    ).all()
    return OwnerEstimate(
        **values,
        historical_total=estimate.total,
        subtotal=estimate.subtotal,
        policy_id=policy.id,
        policy_checksum=estimate.policy_checksum,
        policy_snapshot=estimate.policy_snapshot,
        source_sha256=estimate.source_sha256,
        source_snapshot=estimate.source_snapshot,
        eligibility_rules=estimate.eligibility_rules,
        unknown_costs=estimate.unknown_costs,
        lines=[PricingLineResponse.model_validate(line) for line in lines],
    )
