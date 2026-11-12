"""Separate customer-safe and Owner-only pricing projections."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.business_schemas import BusinessInput, CreateRequest
from app.pricing.policies import Amount, AvailabilityDefinition, PricingPolicyDefinition

ApiUUID = Annotated[UUID, Field(strict=False)]


class PublishPolicy(BusinessInput):
    expected_version: int = Field(ge=0)
    configuration: PricingPolicyDefinition
    reason: str = Field(min_length=8, max_length=500)

    @field_validator("reason")
    @classmethod
    def safe_reason(cls, value: str) -> str:
        value = CreateRequest.safe_notes(value).strip()
        if len(value) < 8:
            raise ValueError("Explain the simulation policy change")
        return value


class PublishAvailability(BusinessInput):
    expected_version: int = Field(ge=0)
    configuration: AvailabilityDefinition
    reason: str = Field(min_length=8, max_length=500)

    @field_validator("reason")
    @classmethod
    def safe_reason(cls, value: str) -> str:
        return PublishPolicy.safe_reason(value)


class PolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    stage_kind: Literal["printing", "design"]
    version: int
    currency_code: Literal["MMK", "XTR"]
    mode: Literal["simulation"]
    configuration: PricingPolicyDefinition
    checksum: str
    active: bool
    created_at: datetime


class AvailabilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version: int
    mode: Literal["simulation"]
    configuration: AvailabilityDefinition
    checksum: str
    active: bool
    created_at: datetime
    expires_at: datetime


class PricingConfiguration(BaseModel):
    policies: list[PolicyResponse]
    availability: AvailabilityResponse | None


class DesignPricingBasis(BusinessInput):
    scope_id: ApiUUID
    estimated_hours: Amount
    hours_per_revision: Amount
    complexity: Literal["simple", "standard", "complex"]
    usage_rights: Literal["personal", "commercial", "exclusive"]

    @model_validator(mode="after")
    def bounded_hours(self) -> "DesignPricingBasis":
        if self.estimated_hours > 10000 or self.hours_per_revision > 1000:
            raise ValueError("Design effort exceeds the supported simulation range")
        return self


class EvaluatePrice(BusinessInput):
    expected_version: int = Field(ge=1)
    design_basis: DesignPricingBasis | None = None


class EstimatePointer(BaseModel):
    estimate_id: UUID
    request_id: UUID
    number: int


class EligibilityRule(BaseModel):
    code: str
    result: Literal["pass", "fail", "unknown"]
    detail: str


class CustomerEstimate(BaseModel):
    id: UUID
    request_id: UUID
    number: int
    stage_kind: Literal["printing", "design"]
    currency_code: Literal["MMK", "XTR"]
    kind: Literal["test_estimate"] = "test_estimate"
    mode: Literal["simulation"] = "simulation"
    binding_authorized: Literal[False] = False
    acceptable: Literal[False] = False
    current: bool
    priced: bool
    estimated_total: Decimal | None
    policy_version: int
    request_revision: int
    decision: Literal["pass", "review", "error"]
    review_reasons: list[str]
    stale_reasons: list[str]
    assumptions: list[str]
    created_at: datetime
    expires_at: datetime
    notice: str = (
        "NON-BINDING TEST ESTIMATE — hypothetical simulation costs, not a final quotation."
    )


class PricingLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    item_kind: Literal["print_item", "design_service"]
    request_item_id: UUID | None
    position: int
    component_code: str
    quantity: Decimal | None
    rate: Decimal | None
    amount: Decimal | None
    assumption: str | None


class OwnerEstimate(CustomerEstimate):
    historical_total: Decimal | None
    subtotal: Decimal | None
    policy_id: UUID
    policy_checksum: str
    policy_snapshot: dict[str, Any]
    source_sha256: str
    source_snapshot: dict[str, Any]
    eligibility_rules: list[EligibilityRule]
    unknown_costs: list[str]
    lines: list[PricingLineResponse]


class CustomerPricingView(BaseModel):
    estimate: CustomerEstimate | None


class OwnerPricingView(BaseModel):
    estimate: OwnerEstimate | None
