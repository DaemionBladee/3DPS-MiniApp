"""Pure fail-closed Level 2 evaluation. A candidate pass never authorizes issuance."""

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from app.pricing.engine import CostResult
from app.pricing.policies import AvailabilityDefinition, PricingPolicyDefinition


@dataclass(frozen=True)
class Rule:
    code: str
    result: Literal["pass", "fail", "unknown"]
    detail: str


@dataclass(frozen=True)
class Evaluation:
    decision: Literal["pass", "review", "error"]
    rules: list[Rule]


def evaluate(
    policy: PricingPolicyDefinition,
    costs: CostResult,
    items: list[dict[str, Any]],
    *,
    service_type: str,
    special_notes: bool,
    availability: AvailabilityDefinition | None,
    today: date,
    design_scope_agreed: bool = False,
) -> Evaluation:
    rules: list[Rule] = []

    def check(code: str, condition: bool | None, detail: str) -> None:
        rules.append(
            Rule(code, "unknown" if condition is None else "pass" if condition else "fail", detail)
        )

    check(
        "printing_only",
        service_type == "printing" and policy.stage_kind == "printing",
        "Only printing-only service can be a Level 2 candidate.",
    )
    check(
        "costs_complete",
        not costs.unknown and costs.total is not None,
        "Every required cost must be explicitly configured.",
    )
    for code in sorted(costs.unknown):
        check(code, None, "A required cost or source metric is unknown or invalid.")
    if policy.stage_kind == "design":
        check(
            "scope_agreement",
            design_scope_agreed,
            "Scope proposal and agreed scope remain distinct.",
        )
        check("manual_design_pricing", False, "Design services always require Owner review.")
        return Evaluation("review", rules)
    ep = policy.eligibility
    check(
        "model_count",
        None if ep.max_models is None else bool(items) and len(items) <= ep.max_models,
        "Model count must satisfy the explicit policy.",
    )
    quantity = sum(item["quantity"] for item in items)
    check(
        "quantity",
        None if ep.max_quantity is None else 0 < quantity <= ep.max_quantity,
        "Quantity must satisfy the explicit policy.",
    )
    check(
        "cost_cap",
        None if ep.max_total is None or costs.total is None else costs.total <= ep.max_total,
        "Estimate must be below the configured cap.",
    )
    check(
        "special_requirements",
        not special_notes and not any(i.get("special_requirements") for i in items),
        "Customer notes and special requirements require Owner review.",
    )
    check(
        "availability_fixture",
        availability is not None,
        "Stock and capacity evidence must be current explicit simulation fixtures.",
    )
    total_seconds = 0
    stock_needs: dict[tuple[str, str], Decimal] = {}
    capacity_needs: dict[str, int] = {}
    for position, item in enumerate(items, 1):
        prefix = f"item_{position}_"
        check(
            prefix + "current_analysis",
            item.get("authoritative", False),
            "Analysis must match the current file, revision and specification.",
        )
        material, quality = item.get("material_key"), item.get("quality_key")
        check(
            prefix + "material",
            bool(ep.approved_materials) and material in ep.approved_materials,
            "Material must be explicitly approved.",
        )
        check(
            prefix + "quality",
            bool(ep.approved_qualities) and quality in ep.approved_qualities,
            "Quality must be explicitly approved.",
        )
        profile = item.get("profile_id")
        check(
            prefix + "profile",
            bool(ep.approved_profile_ids) and profile in ep.approved_profile_ids,
            "Exact profile/version must be approved.",
        )
        check(
            prefix + "unit_confirmation",
            item.get("unit_confirmed", False),
            "Customer must confirm intended model units.",
        )
        targets = item.get("dimensions_confirmed", False)
        check(
            prefix + "dimension_confirmation",
            targets,
            "Customer target dimensions must match the calculated model.",
        )
        check(
            prefix + "requirements_confirmed",
            item.get("requirements_confirmed", False),
            "Customer must explicitly resolve remaining requirements.",
        )
        check(
            prefix + "safety_critical",
            None if item.get("safety_critical") is None else not item["safety_critical"],
            "Safety-critical uses require Owner review.",
        )
        check(
            prefix + "unusual_tolerance",
            None if item.get("unusual_tolerance") is None else not item["unusual_tolerance"],
            "Unusual tolerances require Owner review.",
        )
        tolerance = item.get("dimension_tolerance_mm")
        check(
            prefix + "tolerance_limit",
            None
            if ep.max_tolerance_mm is None or tolerance is None
            else Decimal(str(tolerance)) <= ep.max_tolerance_mm,
            "Dimensional tolerance must satisfy the configured policy.",
        )
        required_by = item.get("required_by")
        check(
            prefix + "deadline",
            None
            if ep.minimum_lead_days is None
            else required_by is None
            or (date.fromisoformat(required_by) - today).days >= ep.minimum_lead_days,
            "Urgent or insufficient lead time requires Owner review.",
        )
        geometry = item.get("geometry") or {}
        volume = geometry.get("volume_mm3")
        check(
            prefix + "geometry",
            bool(
                geometry.get("watertight")
                and isinstance(volume, (int, float))
                and not isinstance(volume, bool)
                and math.isfinite(volume)
                and volume > 0
            ),
            "Geometry must have reliable closed-mesh analysis.",
        )
        check(
            prefix + "build_volume",
            geometry.get("build_volume_compatible"),
            "Model must fit the approved virtual profile.",
        )
        uncertain = [
            v
            for v in geometry.get("warnings", [])
            if v not in {"simulation_only", "uncalibrated_virtual_profile"}
        ]
        check(
            prefix + "manufacturability",
            not uncertain and not geometry.get("review_reasons"),
            "Any unresolved geometry/manufacturability warning requires review.",
        )
        seconds = item.get("print_seconds")
        grams = item.get("filament_g")
        if seconds is None or grams is None:
            check(prefix + "slicing_metrics", None, "Reliable slicing metrics are missing.")
        else:
            total_seconds += seconds * item["quantity"]
            stock_key = (material or "", item.get("color_key") or "")
            if policy.waste_fraction is None or policy.support_overhead_fraction is None:
                check(prefix + "stock_demand", None, "Material allowance is not configured.")
            else:
                stock_needs[stock_key] = stock_needs.get(stock_key, Decimal(0)) + Decimal(
                    str(grams)
                ) * item["quantity"] * (
                    1 + policy.waste_fraction + policy.support_overhead_fraction
                )
            capacity_needs[profile or ""] = (
                capacity_needs.get(profile or "", 0) + seconds * item["quantity"]
            )
    check(
        "duration",
        None
        if ep.max_print_seconds is None or not total_seconds
        else total_seconds <= ep.max_print_seconds,
        "Serial estimated duration must satisfy the policy.",
    )
    stocks: dict[tuple[str, str], Decimal | None] = (
        {(s.material_key, s.color_key): s.available_g for s in availability.stock}
        if availability
        else {}
    )
    capacities = (
        {c.profile_id: c.available_seconds for c in availability.capacity} if availability else {}
    )
    for (material, color), need in sorted(stock_needs.items()):
        available = stocks.get((material, color))
        check(
            "stock_" + material + "_" + color,
            None if available is None else available >= need,
            "Current mock stock must cover the complete material requirement; no hold is created.",
        )
    for profile, seconds_needed in sorted(capacity_needs.items()):
        available_seconds = capacities.get(profile)
        check(
            "capacity_" + profile,
            None if available_seconds is None else available_seconds >= seconds_needed,
            "Current mock capacity must cover estimated serial time; no assignment is created.",
        )
    return Evaluation(
        "pass" if rules and all(r.result == "pass" for r in rules) else "review", rules
    )
