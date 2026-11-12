"""Explicit immutable policy inputs; Decimal strings never pass through binary floats."""

import hashlib
import json
import re
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field, model_validator

from app.api.business_schemas import BusinessInput


def decimal_input(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:0|[1-9][0-9]{0,15})(?:\.[0-9]{1,8})?", value
    ):
        raise ValueError(
            "Use a finite nonnegative decimal string with at most eight fractional places"
        )
    return Decimal(value)


Amount = Annotated[
    Decimal,
    BeforeValidator(decimal_input, json_schema_input_type=str),
    Field(ge=0, le=Decimal("1000000000000000"), allow_inf_nan=False),
]
Ratio = Annotated[
    Decimal,
    BeforeValidator(decimal_input, json_schema_input_type=str),
    Field(ge=0, le=Decimal("0.95"), allow_inf_nan=False),
]
Currency = Literal["MMK", "XTR"]


class EligibilityPolicy(BusinessInput):
    approved_materials: list[Literal["dev-pla", "dev-petg"]] = Field(
        default_factory=list, max_length=2
    )
    approved_qualities: list[Literal["dev-standard", "dev-fine"]] = Field(
        default_factory=list, max_length=2
    )
    approved_profile_ids: list[str] = Field(default_factory=list, max_length=50)
    max_quantity: int | None = Field(default=None, ge=1, le=1000)
    max_models: int | None = Field(default=None, ge=1, le=25)
    max_print_seconds: int | None = Field(default=None, gt=0, le=31536000)
    max_total: Amount | None = None
    minimum_lead_days: int | None = Field(default=None, ge=0, le=365)
    max_tolerance_mm: Amount | None = None


class PricingPolicyDefinition(BusinessInput):
    schema_version: Literal[1] = 1
    stage_kind: Literal["printing", "design"]
    currency_code: Currency
    simulation_only: Literal[True] = True
    rounding_step: Amount
    rounding_mode: Literal["HALF_UP", "CEILING"]
    estimate_ttl_seconds: int = Field(ge=60, le=86400)
    risk_fraction: Ratio | None
    gross_margin: Ratio | None
    tax_fraction: Ratio | None
    minimum_total: Amount | None
    zero_cost_reasons: dict[str, str] = Field(default_factory=dict, max_length=15)
    # Printing parameters; null means unknown, not free.
    material_per_g: dict[str, Amount | None] = Field(default_factory=dict, max_length=8)
    machine_per_hour: Amount | None = None
    labor_per_hour: Amount | None = None
    setup_hours: Amount | None = None
    postprocess_hours_per_item: Amount | None = None
    electricity_per_kwh: Amount | None = None
    average_power_kw: Amount | None = None
    overhead_per_hour: Amount | None = None
    waste_fraction: Ratio | None = None
    support_overhead_fraction: Ratio | None = None
    shipping_flat: Amount | None = None
    eligibility: EligibilityPolicy = Field(default_factory=EligibilityPolicy)
    # Scope-driven design parameters. These never depend on a printer/material.
    design_per_hour: Amount | None = None
    complexity_multipliers: dict[str, Amount | None] = Field(default_factory=dict, max_length=3)
    deliverable_fee: Amount | None = None
    usage_rights_fees: dict[str, Amount | None] = Field(default_factory=dict, max_length=3)

    @model_validator(mode="after")
    def safe_policy(self) -> "PricingPolicyDefinition":
        if self.rounding_step <= 0 or self.rounding_step != self.rounding_step.to_integral_value():
            raise ValueError("MMK rounding uses positive whole accounting units")
        if self.stage_kind == "printing" and self.currency_code != "MMK":
            raise ValueError("M07 physical printing test policies use MMK")
        if self.stage_kind == "design" and (self.currency_code != "XTR" or self.rounding_step != 1):
            raise ValueError("M07 design test policies use integral XTR; no currency conversion")
        if set(self.material_per_g) - {"dev-pla", "dev-petg"}:
            raise ValueError("Unknown material class")
        if set(self.complexity_multipliers) - {"simple", "standard", "complex"}:
            raise ValueError("Unknown scope complexity")
        if any(v is not None and v > 10 for v in self.complexity_multipliers.values()):
            raise ValueError("Scope complexity multiplier is outside the supported range")
        if set(self.usage_rights_fees) - {"personal", "commercial", "exclusive"}:
            raise ValueError("Unknown usage rights")
        for key, reason in self.zero_cost_reasons.items():
            key.encode("utf-8", errors="strict")
            reason.encode("utf-8", errors="strict")
            if "\x00" in key or "\x00" in reason:
                raise ValueError("Invalid zero-cost explanation")
        if any(
            not k or len(k) > 80 or len(v.strip()) < 8 or len(v) > 300
            for k, v in self.zero_cost_reasons.items()
        ):
            raise ValueError("Explain explicitly configured zero components")
        if any(
            not re.fullmatch("[0-9a-f-]{36}", value)
            for value in self.eligibility.approved_profile_ids
        ):
            raise ValueError("Use exact approved profile IDs")
        return self


class StockFixture(BusinessInput):
    material_key: Literal["dev-pla", "dev-petg"]
    color_key: Literal["dev-white", "dev-black"]
    available_g: Amount | None


class CapacityFixture(BusinessInput):
    profile_id: str = Field(pattern="^[0-9a-f-]{36}$")
    available_seconds: int | None = Field(default=None, ge=0, le=31536000)


class AvailabilityDefinition(BusinessInput):
    simulation_only: Literal[True] = True
    ttl_seconds: int = Field(ge=60, le=86400)
    stock: list[StockFixture] = Field(default_factory=list, max_length=4)
    capacity: list[CapacityFixture] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def unique_fixtures(self) -> "AvailabilityDefinition":
        if len({(s.material_key, s.color_key) for s in self.stock}) != len(self.stock):
            raise ValueError("Duplicate stock fixture")
        if len({c.profile_id for c in self.capacity}) != len(self.capacity):
            raise ValueError("Duplicate capacity fixture")
        return self


def checksum(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()
