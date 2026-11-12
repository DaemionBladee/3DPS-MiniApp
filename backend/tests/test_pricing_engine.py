"""Pure pricing/eligibility fixtures are hypothetical; no actual commercial rates."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.pricing.configuration import hypothetical_policy
from app.pricing.eligibility import evaluate
from app.pricing.engine import design_cost, printing_cost, round_currency
from app.pricing.policies import AvailabilityDefinition, PricingPolicyDefinition

PROFILE = "00000000-0000-4000-8000-000000000007"


def policy(stage="printing", **changes):
    return PricingPolicyDefinition.model_validate(
        hypothetical_policy(stage, [PROFILE]).model_dump(mode="json") | changes
    )


def basis(**changes):
    return (
        dict(
            item_id="00000000-0000-4000-8000-000000000008",
            quantity=2,
            material_key="dev-pla",
            color_key="dev-white",
            quality_key="dev-standard",
            filament_g="3.69",
            print_seconds=1150,
            profile_id=PROFILE,
            authoritative=True,
            unit_confirmed=True,
            dimensions_confirmed=True,
            requirements_confirmed=True,
            safety_critical=False,
            unusual_tolerance=False,
            dimension_tolerance_mm="0.5",
            required_by=None,
            special_requirements="",
            geometry={
                "watertight": True,
                "volume_mm3": 8000,
                "build_volume_compatible": True,
                "warnings": [],
                "review_reasons": [],
            },
        )
        | changes
    )


def fixture(stock="1000", capacity=10000):
    return AvailabilityDefinition.model_validate(
        dict(
            ttl_seconds=3600,
            stock=[dict(material_key="dev-pla", color_key="dev-white", available_g=stock)],
            capacity=[dict(profile_id=PROFILE, available_seconds=capacity)],
        )
    )


@pytest.mark.parametrize(
    "value,step,mode,currency,expected",
    [
        ("14.49", "1", "HALF_UP", "MMK", "14"),
        ("14.50", "1", "HALF_UP", "MMK", "15"),
        ("1250", "500", "HALF_UP", "MMK", "1500"),
        ("1000.01", "500", "CEILING", "MMK", "1500"),
        ("4.01", "1", "CEILING", "XTR", "5"),
        ("4.50", "1", "HALF_UP", "XTR", "5"),
        ("0", "1", "CEILING", "MMK", "0"),
    ],
)
def test_currency_specific_rounding(value, step, mode, currency, expected):
    assert round_currency(Decimal(value), Decimal(step), mode, currency) == Decimal(expected)


@pytest.mark.parametrize(
    "value,step,mode,currency",
    [
        ("-1", "1", "HALF_UP", "MMK"),
        ("1", "0", "HALF_UP", "MMK"),
        ("1", "0.5", "CEILING", "XTR"),
        ("1", "2", "CEILING", "XTR"),
        ("1", "1", "HALF_UP", "USD"),
        ("1", "1", "unknown", "MMK"),
    ],
)
def test_invalid_rounding_or_currency_rejected(value, step, mode, currency):
    with pytest.raises(ValueError):
        round_currency(Decimal(value), Decimal(step), mode, currency)


def test_decimal_breakdown_is_repeatable_and_balances_to_rounded_total():
    p = policy()
    results = [printing_cost(p, [basis()], "pickup") for _ in range(3)]
    assert all(r.total == Decimal("98") and not r.unknown for r in results)
    assert results[0].lines == results[1].lines == results[2].lines
    assert sum(line.amount for line in results[0].lines) == results[0].total
    assert all(isinstance(line.amount, Decimal) for line in results[0].lines)
    material = next(line for line in results[0].lines if line.code == "material")
    assert material.amount == Decimal("7.38")
    # Gross margin is cost/(1-margin), rather than a markup of cost*(1+margin).
    r = results[0]
    risked = sum(
        line.amount
        for line in r.lines
        if line.code
        not in {"profit_margin", "minimum_adjustment", "shipping", "tax", "rounding_adjustment"}
    )
    profit = next(line.amount for line in r.lines if line.code == "profit_margin")
    assert profit == pytest.approx(risked / Decimal("0.8") - risked, abs=Decimal("0.00000001"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("machine_per_hour", None),
        ("machine_per_hour", "0"),
        ("labor_per_hour", None),
        ("labor_per_hour", "0"),
        ("electricity_per_kwh", None),
        ("overhead_per_hour", "0"),
        ("risk_fraction", None),
        ("gross_margin", None),
        ("tax_fraction", None),
        ("minimum_total", None),
        ("support_overhead_fraction", None),
        ("waste_fraction", None),
    ],
)
def test_missing_and_unexplained_zero_costs_never_produce_complete_price(field, value):
    result = printing_cost(policy(**{field: value}), [basis()], "pickup")
    assert result.total is None and result.subtotal is None and result.unknown


@pytest.mark.parametrize("value", [-1, 0.2, "-1", "NaN", "Infinity", "1e2", "0.000000001", True])
def test_decimal_wire_values_reject_negative_nonfinite_floats_and_excess_precision(value):
    with pytest.raises(ValidationError):
        policy(machine_per_hour=value)


def test_explicit_zero_tax_is_distinct_from_unknown_and_delivery_needs_shipping_cost():
    p = policy(tax_fraction="0")
    assert printing_cost(p, [basis()], "pickup").total is not None
    assert printing_cost(policy(shipping_flat=None), [basis()], "delivery").total is None
    assert printing_cost(policy(shipping_flat=None), [basis()], "pickup").total is not None
    assert printing_cost(policy(zero_cost_reasons={}), [basis()], "pickup").total is None


def test_minimum_shipping_and_tax_apply_in_the_configured_order():
    p = policy(minimum_total="200", shipping_flat="30", tax_fraction="0.10")
    result = printing_cost(p, [basis()], "delivery")
    assert result.subtotal == Decimal("230") and result.total == Decimal("253")


def test_unknown_material_and_slicing_metrics_produce_unknown_costs():
    for item in [
        basis(material_key="not-sure"),
        basis(filament_g=None),
        basis(print_seconds=None),
        basis(filament_g="0"),
        basis(print_seconds=0),
    ]:
        result = printing_cost(policy(), [item], "pickup")
        assert result.total is None and result.unknown


def test_large_costs_fail_closed_before_database_numeric_overflow():
    result = printing_cost(
        policy(material_per_g={"dev-pla": "1000000000000000"}),
        [basis(filament_g="1000000", quantity=1000)],
        "pickup",
    )
    assert result.total is None and any(code.startswith("limit_") for code in result.unknown)


def test_design_hours_scope_revisions_rights_and_integral_xtr_are_independent():
    p = policy("design")
    result = design_cost(
        p,
        dict(
            estimated_hours="1.5",
            hours_per_revision="0.5",
            complexity="standard",
            usage_rights="commercial",
        ),
        dict(permitted_revisions=2),
    )
    assert result.total == Decimal("136") and result.total == result.total.to_integral_value()
    assert not result.unknown
    assert all(line.item_id is None for line in result.lines)
    assert not any(
        line.code in {"material", "machine_time", "electricity"} for line in result.lines
    )
    no_revisions = design_cost(
        p,
        dict(
            estimated_hours="1.5",
            hours_per_revision="0.5",
            complexity="standard",
            usage_rights="commercial",
        ),
        dict(permitted_revisions=0),
    )
    assert no_revisions.total < result.total
    assert p.currency_code == "XTR" and policy().currency_code == "MMK"


@pytest.mark.parametrize(
    "change",
    [
        {"currency_code": "MMK"},
        {"currency_code": "XTR", "rounding_step": "2"},
        {"design_per_hour": "0"},
        {"complexity_multipliers": {}},
        {"usage_rights_fees": {}},
    ],
)
def test_design_unknown_inputs_or_currency_mismatch_cannot_produce_usable_total(change):
    try:
        p = policy("design", **change)
    except ValidationError:
        return
    result = design_cost(
        p,
        dict(
            estimated_hours="1",
            hours_per_revision="0",
            complexity="standard",
            usage_rights="personal",
        ),
        dict(permitted_revisions=0),
    )
    assert result.total is None


def decision(item=None, *, available=None, config=None, service="printing", notes=False):
    p = config or policy()
    items = [item or basis()]
    return evaluate(
        p,
        printing_cost(p, items, "pickup"),
        items,
        service_type=service,
        special_notes=notes,
        availability=available if available is not None else fixture(),
        today=date(2026, 11, 12),
    )


def test_fully_known_synthetic_candidate_pass_is_not_binding_authorization():
    value = decision()
    assert value.decision == "pass" and all(rule.result == "pass" for rule in value.rules)
    # This pure fixture explicitly models completed checks, unlike real M06's
    # self_intersections_not_checked warning. No native analysis result is fabricated.


@pytest.mark.parametrize(
    "changes",
    [
        {"authoritative": False},
        {"unit_confirmed": False},
        {"dimensions_confirmed": False},
        {"requirements_confirmed": False},
        {"safety_critical": None},
        {"safety_critical": True},
        {"unusual_tolerance": None},
        {"unusual_tolerance": True},
        {"quantity": 3},
        {"required_by": "2026-11-13"},
        {"required_by": "2026-01-01"},
        {"material_key": "not-sure"},
        {"quality_key": "not-sure"},
        {"color_key": "not-sure"},
        {"profile_id": "unknown"},
        {"print_seconds": 4000},
        {"special_requirements": "Owner review needed"},
        {
            "geometry": {
                "watertight": True,
                "volume_mm3": 8000,
                "build_volume_compatible": True,
                "warnings": ["self_intersections_not_checked"],
                "review_reasons": [],
            }
        },
        {
            "geometry": {
                "watertight": False,
                "volume_mm3": None,
                "build_volume_compatible": False,
                "warnings": [],
                "review_reasons": ["open_mesh"],
            }
        },
    ],
)
def test_uncertain_stale_or_special_print_inputs_require_review(changes):
    assert decision(basis(**changes)).decision == "review"


@pytest.mark.parametrize(
    "stock,capacity", [("0", 10000), (None, 10000), ("1000", 0), ("1000", None), ("1", 1)]
)
def test_simulated_stock_and_capacity_fail_closed(stock, capacity):
    assert decision(available=fixture(stock, capacity)).decision == "review"


def test_thresholds_are_explicit_not_production_defaults_and_combined_is_not_level2():
    assert decision(config=policy(eligibility={})).decision == "review"
    assert (
        decision(
            config=policy(
                eligibility=policy().eligibility.model_dump(mode="json") | {"max_total": "1"}
            )
        ).decision
        == "review"
    )
    assert decision(service="design_and_print").decision == "review"
    assert decision(notes=True).decision == "review"
    result = evaluate(
        policy(),
        printing_cost(policy(), [basis()], "pickup"),
        [basis()],
        service_type="printing",
        special_notes=False,
        availability=None,
        today=date(2026, 11, 12),
    )
    assert result.decision == "review"


def test_urgent_threshold_boundary_is_deterministic():
    assert (
        decision(basis(required_by=(date(2026, 11, 12) + timedelta(days=7)).isoformat())).decision
        == "pass"
    )


def test_currency_rounding_cannot_exceed_total_accounting_limit():
    result = printing_cost(
        policy(minimum_total="1000000000000000", rounding_step="999999999999999"),
        [basis()],
        "pickup",
    )
    assert result.total is None and "rounded_total_limit_exceeded" in result.unknown


@pytest.mark.parametrize("quantity", [0, -1])
def test_invalid_quantity_cannot_yield_complete_price(quantity):
    assert printing_cost(policy(), [basis(quantity=quantity)], "pickup").total is None


@pytest.mark.parametrize("volume", [None, 0, -1, float("nan"), float("inf")])
def test_invalid_geometry_volume_cannot_pass_eligibility(volume):
    item = basis()
    item["geometry"]["volume_mm3"] = volume
    result = evaluate(
        policy(),
        printing_cost(policy(), [item], "pickup"),
        [item],
        service_type="printing",
        special_notes=False,
        availability=fixture(),
        today=date.today(),
    )
    assert result.decision == "review"


@pytest.mark.parametrize("reason", ["Bad nul\x00 in configuration", "Invalid surrogate \ud800"])
def test_invalid_policy_reason_is_rejected_before_persistence(reason):
    with pytest.raises(ValidationError):
        policy(zero_cost_reasons={"tax_fraction": reason})


@pytest.mark.parametrize(
    "reason", ["Bad nul\x00 in configuration", "Invalid surrogate \ud800", "        "]
)
def test_fixture_reason_is_validated_in_the_api_schema(reason):
    from app.api.pricing_schemas import PublishAvailability

    with pytest.raises(ValidationError):
        PublishAvailability.model_validate(
            {"expected_version": 0, "configuration": {"ttl_seconds": 60}, "reason": reason}
        )
