"""Deterministic accounting-unit calculations. Unknown is never converted to zero."""

from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, localcontext
from typing import Any

from app.pricing.policies import PricingPolicyDefinition

SCALE = Decimal("0.00000001")
MAX_TOTAL = Decimal("1000000000000000")


def amount(value: Decimal) -> Decimal:
    return value.quantize(SCALE, rounding=ROUND_HALF_UP)


def round_currency(value: Decimal, step: Decimal, mode: str, currency: str) -> Decimal:
    if (
        not value.is_finite()
        or value < 0
        or step <= 0
        or step != step.to_integral_value()
        or currency not in {"MMK", "XTR"}
        or currency == "XTR"
        and step != 1
    ):
        raise ValueError("Invalid money or currency rounding rule")
    if mode not in {"HALF_UP", "CEILING"}:
        raise ValueError("Unknown rounding mode")
    rounding = {"HALF_UP": ROUND_HALF_UP, "CEILING": ROUND_CEILING}[mode]
    return (value / step).to_integral_value(rounding=rounding) * step


@dataclass(frozen=True)
class CostLine:
    code: str
    item_id: str | None
    quantity: Decimal | None
    rate: Decimal | None
    amount: Decimal | None
    assumption: str | None = None


@dataclass
class CostResult:
    lines: list[CostLine] = field(default_factory=list)
    unknown: set[str] = field(default_factory=set)
    assumptions: set[str] = field(default_factory=set)
    subtotal: Decimal | None = None
    total: Decimal | None = None

    def add(
        self,
        code: str,
        quantity: Decimal | None,
        rate: Decimal | None,
        item_id: str | None = None,
        assumption: str | None = None,
    ) -> None:
        value = amount(quantity * rate) if quantity is not None and rate is not None else None
        if value is not None and (not value.is_finite() or abs(value) > MAX_TOTAL):
            self.unknown.add("limit_" + code)
            value = None
        self.lines.append(CostLine(code, item_id, quantity, rate, value, assumption))
        if value is None:
            self.unknown.add("unknown_" + code)
        if assumption:
            self.assumptions.add(assumption)


def known_rate(
    result: CostResult,
    policy: PricingPolicyDefinition,
    key: str,
    value: Decimal | None,
    *,
    core: bool = False,
) -> Decimal | None:
    if value is None or value == 0 and (core or key not in policy.zero_cost_reasons):
        result.unknown.add(("zero_" if value == 0 else "unknown_") + key)
        return None
    if value == 0:
        result.assumptions.add("explicit_zero_" + key)
    return value


def finish(
    result: CostResult, policy: PricingPolicyDefinition, shipping: Decimal | None
) -> CostResult:
    base = (
        sum((line.amount for line in result.lines if line.amount is not None), Decimal(0))
        if not result.unknown
        else None
    )
    risk = None if base is None or policy.risk_fraction is None else base * policy.risk_fraction
    result.add("risk_allowance", Decimal(1), risk)
    risked = base + amount(risk) if base is not None and risk is not None else None
    profit = (
        None
        if risked is None or policy.gross_margin is None
        else risked / (1 - policy.gross_margin) - risked
    )
    result.add("profit_margin", Decimal(1), profit)
    net = risked + amount(profit) if risked is not None and profit is not None else None
    minimum = (
        None
        if net is None or policy.minimum_total is None
        else max(Decimal(0), policy.minimum_total - net)
    )
    result.add("minimum_adjustment", Decimal(1), minimum)
    result.add("shipping", Decimal(1), shipping)
    taxable = (
        net + amount(minimum) + shipping
        if net is not None and minimum is not None and shipping is not None
        else None
    )
    tax_rate = known_rate(result, policy, "tax_fraction", policy.tax_fraction)
    result.add("tax", taxable, tax_rate)
    if not result.unknown:
        unrounded = sum(
            (line.amount for line in result.lines if line.amount is not None), Decimal(0)
        )
        if unrounded > MAX_TOTAL:
            result.unknown.add("total_limit_exceeded")
        else:
            rounded = round_currency(
                unrounded, policy.rounding_step, policy.rounding_mode, policy.currency_code
            )
            if rounded > MAX_TOTAL:
                result.unknown.add("rounded_total_limit_exceeded")
                return result
            result.lines.append(
                CostLine("rounding_adjustment", None, Decimal(1), None, amount(rounded - unrounded))
            )
            assert taxable is not None
            result.subtotal, result.total = amount(taxable), amount(rounded)
    return result


def printing_cost(
    policy: PricingPolicyDefinition, items: list[dict[str, Any]], fulfillment: str
) -> CostResult:
    with localcontext() as context:
        context.prec = 50
        result = CostResult()
        if not items:
            result.unknown.add("printing_items_missing")
        for item in items:
            iid = item["item_id"]
            quantity = Decimal(item["quantity"])
            grams = Decimal(str(item["filament_g"])) if item.get("filament_g") is not None else None
            seconds = (
                Decimal(item["print_seconds"]) if item.get("print_seconds") is not None else None
            )
            if (
                quantity <= 0
                or grams is not None
                and grams <= 0
                or seconds is not None
                and seconds <= 0
            ):
                result.unknown.add("invalid_slicing_metrics")
                grams = seconds = None
            grams = grams * quantity if grams is not None else None
            hours = seconds * quantity / 3600 if seconds is not None else None
            material = known_rate(
                result,
                policy,
                "material_" + str(item.get("material_key")),
                policy.material_per_g.get(item.get("material_key", "")),
                core=True,
            )
            result.add("material", grams, material, iid)
            waste = known_rate(result, policy, "waste_fraction", policy.waste_fraction)
            result.add(
                "waste_allowance",
                grams * waste if grams is not None and waste is not None else None,
                material,
                iid,
                "estimated_waste_allowance",
            )
            supports = known_rate(
                result, policy, "support_overhead_fraction", policy.support_overhead_fraction
            )
            result.add(
                "support_allowance",
                grams * supports if grams is not None and supports is not None else None,
                material,
                iid,
                "support_cost_is_assumed_not_measured",
            )
            result.add(
                "machine_time",
                hours,
                known_rate(result, policy, "machine_per_hour", policy.machine_per_hour, core=True),
                iid,
            )
            result.add(
                "electricity",
                hours * policy.average_power_kw
                if hours is not None and policy.average_power_kw is not None
                else None,
                known_rate(result, policy, "electricity_per_kwh", policy.electricity_per_kwh),
                iid,
            )
            result.add(
                "overhead",
                hours,
                known_rate(result, policy, "overhead_per_hour", policy.overhead_per_hour),
                iid,
            )
            labor = known_rate(result, policy, "labor_per_hour", policy.labor_per_hour, core=True)
            result.add(
                "postprocess_labor",
                quantity * policy.postprocess_hours_per_item
                if policy.postprocess_hours_per_item is not None
                else None,
                labor,
                iid,
            )
        result.add(
            "setup_labor",
            policy.setup_hours,
            known_rate(result, policy, "labor_per_hour", policy.labor_per_hour, core=True),
        )
        shipping = (
            Decimal(0)
            if fulfillment == "pickup"
            else known_rate(result, policy, "shipping_flat", policy.shipping_flat)
        )
        result.assumptions.update(
            {
                "hypothetical_costs_only",
                "serial_quantity_scaling_not_batch_packing",
                "uncalibrated_virtual_hardware",
            }
        )
        return finish(result, policy, shipping)


def design_cost(
    policy: PricingPolicyDefinition, basis: dict[str, Any], scope: dict[str, Any]
) -> CostResult:
    with localcontext() as context:
        context.prec = 50
        result = CostResult()
        hours = Decimal(basis["estimated_hours"])
        revision_hours = Decimal(basis["hours_per_revision"]) * scope["permitted_revisions"]
        if hours <= 0:
            result.unknown.add("design_hours_missing_or_zero")
        complexity = known_rate(
            result,
            policy,
            "scope_complexity",
            policy.complexity_multipliers.get(basis["complexity"]),
            core=True,
        )
        rate = known_rate(result, policy, "design_per_hour", policy.design_per_hour, core=True)
        result.add(
            "design_labor",
            (hours + revision_hours) * complexity if complexity is not None else None,
            rate,
        )
        result.add(
            "deliverables",
            Decimal(1),
            known_rate(result, policy, "deliverable_fee", policy.deliverable_fee),
        )
        result.add(
            "usage_rights",
            Decimal(1),
            known_rate(
                result,
                policy,
                "usage_rights_fee",
                policy.usage_rights_fees.get(basis["usage_rights"]),
            ),
        )
        result.assumptions.update(
            {
                "hypothetical_costs_only",
                "owner_estimated_design_hours",
                "usage_rights_pricing_assumption_not_delivery_authorization",
            }
        )
        return finish(result, policy, Decimal(0))
