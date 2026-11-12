from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select

from app.api.auth import FactoryDependency, PrincipalDependency, SettingsDependency
from app.api.business import BusinessPrincipalDependency, CommandKey
from app.api.pricing_schemas import (
    AvailabilityResponse,
    CustomerEstimate,
    CustomerPricingView,
    EstimatePointer,
    EvaluatePrice,
    OwnerEstimate,
    OwnerPricingView,
    PolicyResponse,
    PricingConfiguration,
    PublishAvailability,
    PublishPolicy,
)
from app.core.errors import AuthError
from app.database.analysis_models import SlicerProfile
from app.database.pricing_models import PricingEstimate, PricingPolicy
from app.pricing.configuration import hypothetical_policy, publish_availability, publish_policy
from app.pricing.policies import PricingPolicyDefinition
from app.pricing.sources import latest_availability
from app.services.analysis import owner
from app.services.pricing import evaluate_request, project_estimate
from app.services.requests import locked_request

router = APIRouter(prefix="/api/v1", tags=["simulation-pricing"])


@router.get("/owner/pricing/configuration", response_model=PricingConfiguration)
async def configuration(
    principal: PrincipalDependency, factory: FactoryDependency
) -> PricingConfiguration:
    owner(principal.user)
    async with factory() as db:
        policies: list[PricingPolicy] = []
        for stage in ("printing", "design"):
            policies.extend(
                (
                    await db.scalars(
                        select(PricingPolicy)
                        .where(PricingPolicy.stage_kind == stage)
                        .order_by(PricingPolicy.version.desc())
                        .limit(50)
                    )
                ).all()
            )
        availability = await latest_availability(db)
        return PricingConfiguration(
            policies=[PolicyResponse.model_validate(p) for p in policies],
            availability=AvailabilityResponse.model_validate(availability)
            if availability
            else None,
        )


@router.get("/owner/pricing/hypothetical-policy", response_model=PricingPolicyDefinition)
async def template(
    principal: PrincipalDependency,
    factory: FactoryDependency,
    stage_kind: Literal["printing", "design"],
) -> PricingPolicyDefinition:
    owner(principal.user)
    async with factory() as db:
        ids = (
            await db.scalars(
                select(SlicerProfile.id)
                .where(SlicerProfile.active)
                .order_by(SlicerProfile.id)
                .limit(50)
            )
        ).all()
        return hypothetical_policy(stage_kind, [str(identity) for identity in ids])


@router.post("/owner/pricing/policies", response_model=PolicyResponse, status_code=201)
async def create_policy(
    body: PublishPolicy,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
) -> PolicyResponse:
    return await publish_policy(factory, settings, principal, key, body)


@router.post(
    "/owner/pricing/availability-fixtures", response_model=AvailabilityResponse, status_code=201
)
async def create_fixture(
    body: PublishAvailability,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
) -> AvailabilityResponse:
    return await publish_availability(factory, settings, principal, key, body)


@router.post("/requests/{request_id}/estimates", response_model=EstimatePointer, status_code=201)
async def customer_evaluate(
    request_id: UUID,
    body: EvaluatePrice,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
) -> EstimatePointer:
    return await evaluate_request(factory, settings, principal, key, request_id, body)


@router.post(
    "/owner/requests/{request_id}/estimates", response_model=EstimatePointer, status_code=201
)
async def owner_evaluate(
    request_id: UUID,
    body: EvaluatePrice,
    key: CommandKey,
    principal: BusinessPrincipalDependency,
    settings: SettingsDependency,
    factory: FactoryDependency,
) -> EstimatePointer:
    return await evaluate_request(
        factory, settings, principal, key, request_id, body, owner_route=True
    )


@router.get("/requests/{request_id}/estimates", response_model=CustomerPricingView)
async def customer_view(
    request_id: UUID, principal: PrincipalDependency, factory: FactoryDependency
) -> CustomerPricingView:
    async with factory() as db:
        row = await locked_request(db, principal.user, request_id, None)
        estimate = await db.scalar(
            select(PricingEstimate)
            .where(PricingEstimate.request_id == row.id)
            .order_by(PricingEstimate.number.desc())
            .limit(1)
        )
        if estimate is None:
            return CustomerPricingView(estimate=None)
        value = await project_estimate(db, row, estimate, private=False)
        assert isinstance(value, CustomerEstimate)
        return CustomerPricingView(estimate=value)


@router.get("/owner/requests/{request_id}/estimates", response_model=OwnerPricingView)
async def owner_view(
    request_id: UUID, principal: PrincipalDependency, factory: FactoryDependency
) -> OwnerPricingView:
    owner(principal.user)
    async with factory() as db:
        row = await locked_request(db, principal.user, request_id, None)
        estimate = await db.scalar(
            select(PricingEstimate)
            .where(PricingEstimate.request_id == row.id)
            .order_by(PricingEstimate.number.desc())
            .limit(1)
        )
        if estimate is None:
            return OwnerPricingView(estimate=None)
        value = await project_estimate(db, row, estimate, private=True)
        assert isinstance(value, OwnerEstimate)
        return OwnerPricingView(estimate=value)


@router.get("/owner/requests/{request_id}/estimates/{estimate_id}", response_model=OwnerEstimate)
async def history(
    request_id: UUID, estimate_id: UUID, principal: PrincipalDependency, factory: FactoryDependency
) -> OwnerEstimate:
    owner(principal.user)
    async with factory() as db:
        row = await locked_request(db, principal.user, request_id, None)
        estimate = await db.get(PricingEstimate, estimate_id)
        if estimate is None or estimate.request_id != row.id:
            raise AuthError(
                404, "estimate_not_found", "This simulation estimate could not be found."
            )
        value = await project_estimate(db, row, estimate, private=True)
        assert isinstance(value, OwnerEstimate)
        return value
