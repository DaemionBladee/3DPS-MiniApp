# ruff: noqa: F811
"""M07 real PostgreSQL security, provenance and transaction integration."""

import asyncio
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.analysis.orchestrator import process_one
from app.database.business_models import AuditLog, NotificationOutbox
from app.database.pricing_models import PricingEstimate, PricingEstimateLine
from tests.signing import CUSTOMER_ID, ORIGIN, OWNER_ID
from tests.test_analysis import registry, sandbox, submitted  # noqa: F401
from tests.test_business_foundation import headers
from tests.test_design_intake import SCOPE, scoped, step
from tests.test_printing_intake import command


async def configure(client, stage="printing", version=0):
    auth = await headers(client, OWNER_ID)
    template = (
        await client.get(f"/api/v1/owner/pricing/hypothetical-policy?stage_kind={stage}")
    ).json()
    response = await client.post(
        "/api/v1/owner/pricing/policies",
        headers=command(auth),
        json={
            "expected_version": version,
            "configuration": template,
            "reason": "Explicit hypothetical test policy",
        },
    )
    assert response.status_code == 201, response.text
    return auth, response.json()


async def calculate(client, auth, rid, basis=None, key=None):
    row = (await client.get(f"/api/v1/requests/{rid}")).json()
    return await client.post(
        f"/api/v1/requests/{rid}/estimates",
        headers=key or command(auth),
        json={"expected_version": row["version"], **({"design_basis": basis} if basis else {})},
    )


async def estimate(client, rid, owner=False):
    response = await client.get(f"/api/v1/{'owner/' if owner else ''}requests/{rid}/estimates")
    assert response.status_code == 200, response.text
    return response.json()["estimate"]


async def test_real_native_cost_provenance_private_projection_and_idempotency(client, app, sandbox):
    customer = await headers(client)
    data = await submitted(client, customer)
    rid = data["request"]["id"]
    assert await process_one(app.state.session_factory, app.state.storage, sandbox, "m07-test")
    owner, policy = await configure(client)
    customer = await headers(client)
    key = command(customer)
    first = await calculate(client, customer, rid, key=key)
    assert first.status_code == 201, first.text
    assert (await calculate(client, customer, rid, key=key)).json() == first.json()
    public = await estimate(client, rid)
    assert public["priced"] and Decimal(public["estimated_total"]) > 0
    assert public["decision"] == "review" and not public["acceptable"]
    assert public["kind"] == "test_estimate" and not public["binding_authorized"]
    assert not {"lines", "source_snapshot", "policy_snapshot", "subtotal"} & public.keys()
    await headers(client, OWNER_ID)
    private = await estimate(client, rid, True)
    assert private["policy_id"] == policy["id"]
    assert private["source_snapshot"]["items"][0]["analysis_id"]
    assert sum(Decimal(line["amount"]) for line in private["lines"]) == Decimal(
        private["estimated_total"]
    )
    assert any(
        rule["code"].endswith("manufacturability") and rule["result"] != "pass"
        for rule in private["eligibility_rules"]
    )
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(PricingEstimate)) == 1
        audit = await db.scalar(
            select(AuditLog).where(AuditLog.action == "pricing.estimate_evaluated")
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(NotificationOutbox)
                .where(NotificationOutbox.audit_log_id == audit.id)
            )
            == 1
        )
        for table in ("quotes", "orders", "payments", "printers"):
            assert (
                await db.scalar(text("SELECT to_regclass(:name)"), {"name": "public." + table})
                is None
            )


async def test_missing_policy_and_analysis_never_become_free_price(client):
    customer = await headers(client)
    data = await submitted(client, customer)
    rid = data["request"]["id"]
    response = await calculate(client, customer, rid)
    assert response.status_code == 409 and response.json()["code"] == "pricing_policy_missing"
    await configure(client)
    customer = await headers(client)
    assert (await calculate(client, customer, rid)).status_code == 201
    value = await estimate(client, rid)
    assert value["estimated_total"] is None and not value["priced"]
    assert value["decision"] == "review"


async def test_design_only_scope_costs_integral_stars_and_no_print_dependencies(client, app):
    data, customer, owner = await scoped(client)
    owner, _ = await configure(client, "design")
    rid = data["request"]["id"]
    basis = {
        "scope_id": data["scopes"][-1]["id"],
        "estimated_hours": "1.5",
        "hours_per_revision": "0.5",
        "complexity": "standard",
        "usage_rights": "commercial",
    }
    assert (await calculate(client, owner, rid, basis)).status_code == 201
    private = await estimate(client, rid, True)
    assert private["estimated_total"] == "136.00000000" and private["currency_code"] == "XTR"
    assert all(
        line["item_kind"] == "design_service" and line["request_item_id"] is None
        for line in private["lines"]
    )
    async with app.state.session_factory() as db:
        assert await db.scalar(text("SELECT count(*) FROM request_items")) == 0
        assert await db.scalar(text("SELECT count(*) FROM slicing_runs")) == 0
    customer = await headers(client)
    assert (await calculate(client, customer, rid, basis)).status_code == 403
    assert (await estimate(client, rid))["estimated_total"] == private["estimated_total"]


async def test_concurrent_evaluations_reuse_one_immutable_record(client, app):
    customer = await headers(client)
    data = await submitted(client, customer)
    await configure(client)
    customer = await headers(client)
    rid = data["request"]["id"]
    responses = await asyncio.gather(*(calculate(client, customer, rid) for _ in range(5)))
    assert all(r.status_code == 201 for r in responses), [r.text for r in responses]
    assert len({r.json()["estimate_id"] for r in responses}) == 1
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(PricingEstimate)) == 1
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "pricing.estimate_evaluated")
            )
            == 1
        )


async def test_policy_change_stales_history_and_database_rejects_promotion(client, app):
    customer = await headers(client)
    data = await submitted(client, customer)
    await configure(client)
    customer = await headers(client)
    rid = data["request"]["id"]
    pointer = (await calculate(client, customer, rid)).json()
    await configure(client, version=1)
    old = await estimate(client, rid, True)
    assert not old["current"] and "pricing_policy_changed" in old["stale_reasons"]
    assert old["estimated_total"] is None
    assert (await calculate(client, await headers(client), rid)).json()["number"] == 2
    await headers(client, OWNER_ID)
    history = await client.get(f"/api/v1/owner/requests/{rid}/estimates/{pointer['estimate_id']}")
    assert history.status_code == 200 and not history.json()["current"]
    for assignment in (
        "mode='live'",
        "kind='binding_offer'",
        "binding_authorized=true",
        "total=10",
    ):
        with pytest.raises(IntegrityError):
            async with app.state.session_factory() as db, db.begin():
                await db.execute(text(f"UPDATE pricing_estimates SET {assignment}"))
    with pytest.raises(IntegrityError):
        async with app.state.session_factory() as db, db.begin():
            await db.execute(text("UPDATE pricing_policies SET configuration='{}'::jsonb"))


async def test_scope_replacement_invalidates_manual_basis(client):
    data, _, owner = await scoped(client)
    owner, _ = await configure(client, "design")
    rid = data["request"]["id"]
    basis = {
        "scope_id": data["scopes"][-1]["id"],
        "estimated_hours": "1",
        "hours_per_revision": "0",
        "complexity": "simple",
        "usage_rights": "personal",
    }
    assert (await calculate(client, owner, rid, basis)).status_code == 201
    await step(
        client, owner, data, "scopes", {"scope": SCOPE, "reason": "Updated simulation scope"}, True
    )
    assert not (await estimate(client, rid, True))["current"]
    assert (await calculate(client, owner, rid, basis)).status_code == 409


async def test_pricing_resource_auth_csrf_origin_and_frontend_price_rejected(client, app):
    auth = await headers(client)
    data = await submitted(client, auth)
    rid = data["request"]["id"]
    for path in ("/owner/pricing/configuration", f"/owner/requests/{rid}/estimates"):
        assert (await client.get("/api/v1" + path)).status_code == 403
    await configure(client)
    auth = await headers(client)
    row = (await client.get(f"/api/v1/requests/{rid}")).json()
    body = {"expected_version": row["version"]}
    path = f"/api/v1/requests/{rid}/estimates"
    assert (
        await client.post(path, headers={"Idempotency-Key": "test-missing-csrf"}, json=body)
    ).status_code == 403
    assert (
        await client.post(
            path, headers=command(auth) | {"Origin": "https://evil.invalid"}, json=body
        )
    ).status_code == 403
    assert (
        await client.post(path, headers=command(auth), json=body | {"total": "1"})
    ).status_code == 422
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=ORIGIN, headers={"Origin": ORIGIN}
    ) as other:
        other_auth = await headers(other, CUSTOMER_ID + 99)
        assert (await other.get(path)).status_code == 404
        assert (await other.post(path, headers=command(other_auth), json=body)).status_code == 404


async def test_outbox_failure_rolls_back_entire_estimate(client, app):
    auth = await headers(client)
    data = await submitted(client, auth)
    await configure(client)
    auth = await headers(client)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO notification_outbox"):
            raise SQLAlchemyError("Synthetic outbox failure")

    engine = app.state.engine.sync_engine
    event.listen(engine, "before_cursor_execute", fail)
    try:
        response = await calculate(client, auth, data["request"]["id"])
        assert response.status_code == 503
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(PricingEstimate)) == 0
        assert await db.scalar(select(func.count()).select_from(PricingEstimateLine)) == 0
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "pricing.estimate_evaluated")
            )
            == 0
        )


async def test_live_flag_toggle_cannot_promote_simulation(client, app):
    auth = await headers(client)
    data = await submitted(client, auth)
    await configure(client)
    auth = await headers(client)
    rid = data["request"]["id"]
    assert (await calculate(client, auth, rid)).status_code == 201
    app.state.settings.binding_quotes_enabled = True
    try:
        assert (await calculate(client, auth, rid)).status_code == 409
        assert not (await estimate(client, rid))["binding_authorized"]
    finally:
        app.state.settings.binding_quotes_enabled = False


async def test_cached_policy_replay_rechecks_current_server_owner(client, app):
    owner, _ = await configure(client, "design")
    template = (
        await client.get("/api/v1/owner/pricing/hypothetical-policy?stage_kind=design")
    ).json()
    key = command(owner)
    body = {
        "expected_version": 1,
        "configuration": template,
        "reason": "Explicit simulation policy revision",
    }
    path = "/api/v1/owner/pricing/policies"
    assert (await client.post(path, headers=key, json=body)).status_code == 201
    app.state.settings.owner_telegram_ids = ""
    try:
        assert (await client.post(path, headers=key, json=body)).status_code == 403
    finally:
        app.state.settings.owner_telegram_ids = str(OWNER_ID)


async def test_expected_version_and_idempotency_payload_conflict(client):
    auth = await headers(client)
    data = await submitted(client, auth)
    await configure(client)
    auth = await headers(client)
    rid = data["request"]["id"]
    key = command(auth)
    assert (await calculate(client, auth, rid, key=key)).status_code == 201
    path = f"/api/v1/requests/{rid}/estimates"
    wrong = {"expected_version": data["request"]["version"] + 1}
    assert (await client.post(path, headers=key, json=wrong)).status_code == 409
    assert (await client.post(path, headers=command(auth), json=wrong)).status_code == 409


async def test_availability_versions_expiry_and_current_evaluation(client, app):
    auth = await headers(client)
    data = await submitted(client, auth)
    owner, _ = await configure(client)
    body = {
        "expected_version": 0,
        "reason": "Explicit mock stock and capacity snapshot",
        "configuration": {"simulation_only": True, "ttl_seconds": 60, "stock": [], "capacity": []},
    }
    path = "/api/v1/owner/pricing/availability-fixtures"
    result = await client.post(path, headers=command(owner), json=body)
    assert result.status_code == 201, result.text
    customer = await headers(client)
    assert (await client.post(path, headers=command(customer), json=body)).status_code == 403
    rid = data["request"]["id"]
    assert (await calculate(client, customer, rid)).status_code == 201
    first = await estimate(client, rid)
    owner = await headers(client, OWNER_ID)
    assert (
        await client.post(path, headers=command(owner), json=body | {"expected_version": 1})
    ).status_code == 201
    stale = await estimate(client, rid, True)
    assert stale["id"] == first["id"] and not stale["current"]
    assert "source_or_availability_changed" in stale["stale_reasons"]
    assert (await client.post(path, headers=command(owner), json=body)).status_code == 409


async def test_deferred_cost_balance_rejects_estimate_without_lines(client, app):
    from uuid import uuid4

    from sqlalchemy import insert, literal

    data, _, _ = await scoped(client)
    owner, _ = await configure(client, "design")
    basis = {
        "scope_id": data["scopes"][-1]["id"],
        "estimated_hours": "1.5",
        "hours_per_revision": "0.5",
        "complexity": "standard",
        "usage_rights": "commercial",
    }
    assert (await calculate(client, owner, data["request"]["id"], basis)).status_code == 201
    table = PricingEstimate.__table__
    columns = list(table.columns)
    with pytest.raises(IntegrityError, match="balance"):
        async with app.state.session_factory() as db, db.begin():
            values = [
                literal(uuid4()) if col.name == "id" else col + 1 if col.name == "number" else col
                for col in columns
            ]
            await db.execute(
                insert(table).from_select([col.name for col in columns], select(*values))
            )
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(PricingEstimate)) == 1


async def test_expired_session_cannot_replay_pricing_command(client, app):
    auth = await headers(client)
    data = await submitted(client, auth)
    await configure(client)
    auth = await headers(client)
    rid = data["request"]["id"]
    key = command(auth)
    assert (await calculate(client, auth, rid, key=key)).status_code == 201
    async with app.state.session_factory() as db, db.begin():
        await db.execute(
            text(
                "UPDATE sessions SET created_at=now()-interval '2 hours', expires_at=now()-interval '1 second'"
            )
        )
    response = await client.post(
        f"/api/v1/requests/{rid}/estimates",
        headers=key,
        json={"expected_version": data["request"]["version"]},
    )
    assert response.status_code == 401


async def test_cost_lines_cannot_be_appended_after_estimate_commit(client, app):
    from uuid import uuid4

    from sqlalchemy import insert, literal

    data, _, _ = await scoped(client)
    owner, _ = await configure(client, "design")
    basis = {
        "scope_id": data["scopes"][-1]["id"],
        "estimated_hours": "1.5",
        "hours_per_revision": "0.5",
        "complexity": "standard",
        "usage_rights": "commercial",
    }
    assert (await calculate(client, owner, data["request"]["id"], basis)).status_code == 201
    table = PricingEstimateLine.__table__
    columns = list(table.columns)
    with pytest.raises(IntegrityError, match="Immutable pricing cost set"):
        async with app.state.session_factory() as db, db.begin():
            values = [
                literal(uuid4())
                if col.name == "id"
                else literal(999)
                if col.name == "position"
                else literal(Decimal(0))
                if col.name == "amount"
                else col
                for col in columns
            ]
            await db.execute(
                insert(table).from_select([col.name for col in columns], select(*values).limit(1))
            )
