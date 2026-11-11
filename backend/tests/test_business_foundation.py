"""M03 vertical slice against real PostgreSQL, including cross-worker races."""

import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.business_schemas import CreateRequest
from app.core.errors import AuthError
from app.database.business_models import (
    AuditLog,
    NotificationOutbox,
    ServiceRequest,
)
from app.main import create_app
from app.services.auth import resolve_session, revoke_session
from app.services.requests import create_request
from tests.conftest import make_settings
from tests.signing import CUSTOMER_ID, ORIGIN, OWNER_ID
from tests.test_auth_api import login


async def headers(client: AsyncClient, user_id: int = CUSTOMER_ID) -> dict[str, str]:
    session = await login(client, user_id)
    return {"X-CSRF-Token": str(session["csrf_token"]), "Idempotency-Key": uuid4().hex}


async def create(client: AsyncClient, command: dict[str, str], kind: str = "printing") -> dict:
    response = await client.post(
        "/api/v1/requests",
        headers=command,
        json={"service_type": kind, "customer_notes": "Test draft"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def counts(app: FastAPI) -> list[int]:
    async with app.state.session_factory() as db:
        return [
            await db.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in [
                "service_projects",
                "service_requests",
                "audit_logs",
                "notification_outbox",
                "idempotency_records",
            ]
        ]


@pytest.mark.parametrize(
    ("kind", "stage"),
    [("printing", "printing"), ("custom_design", "design"), ("design_and_print", "design")],
)
async def test_initial_project_stage_lineage_and_atomic_events(
    client: AsyncClient, app: FastAPI, kind: str, stage: str
) -> None:
    command = await headers(client)
    result = await create(client, command, kind)
    project, request = result["project"], result["request"]
    assert request["stage_kind"] == stage
    assert request["service_project_id"] == project["id"]
    assert request["customer_id"] == project["customer_id"]
    assert request["mode"] == project["mode"] == "simulation"
    assert request["status"] == "draft" and request["version"] == request["revision"] == 1
    assert len(request["canonical_spec_sha256"]) == 64
    assert await counts(app) == [1, 1, 1, 1, 1]
    async with app.state.session_factory() as db:
        audit = await db.scalar(select(AuditLog))
        outbox = await db.scalar(select(NotificationOutbox))
        assert audit and outbox and outbox.audit_log_id == audit.id
        assert outbox.status == "pending" and outbox.recipient_user_id == audit.actor_user_id
        assert "customer_notes" not in outbox.payload_minimized
        assert "Test draft" not in str(audit.metadata_snapshot)
    assert (await client.get(f"/api/v1/projects/{project['id']}")).json() == project
    assert (await client.get(f"/api/v1/requests/{request['id']}")).json() == request


async def test_cross_customer_isolation_and_owner_read_cancel_permissions(
    client: AsyncClient, app: FastAPI
) -> None:
    result = await create(client, await headers(client))
    request_id = result["request"]["id"]
    project_id = result["project"]["id"]
    stranger = await headers(client, CUSTOMER_ID + 1)
    assert (await client.get("/api/v1/requests")).json()["items"] == []
    assert (await client.get("/api/v1/projects")).json()["items"] == []
    assert (await client.get("/api/v1/owner/requests")).status_code == 403
    assert (await client.get(f"/api/v1/requests/{request_id}")).status_code == 404
    assert (await client.get(f"/api/v1/projects/{project_id}")).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/requests/{request_id}",
            headers=stranger,
            json={"expected_version": 1, "customer_notes": "Stolen"},
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/requests/{request_id}/transitions",
            headers=stranger,
            json={"expected_version": 1, "target": "cancelled", "reason": "Stolen"},
        )
    ).status_code == 404
    owner = await headers(client, OWNER_ID)
    assert (await client.get("/api/v1/owner/requests")).json()["items"][0]["id"] == request_id
    assert (await client.get(f"/api/v1/requests/{request_id}")).status_code == 200
    assert (await client.get(f"/api/v1/projects/{project_id}")).status_code == 200
    assert (await client.get("/api/v1/requests")).json()["items"] == []
    assert (
        await client.patch(
            f"/api/v1/requests/{request_id}",
            headers=owner,
            json={"expected_version": 1, "customer_notes": "Impersonation"},
        )
    ).status_code == 403
    cancelled = await client.post(
        f"/api/v1/requests/{request_id}/transitions",
        headers=owner,
        json={"expected_version": 1, "target": "cancelled", "reason": "Duplicate test request"},
    )
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    async with app.state.session_factory() as db:
        audit = await db.scalar(select(AuditLog).where(AuditLog.action == "request.cancelled"))
        assert audit and audit.reason == "Duplicate test request"
        assert str(audit.actor_user_id) != result["request"]["customer_id"]
    assert await counts(app) == [1, 1, 2, 2, 2]


async def test_draft_revision_hash_version_cancel_and_terminal_guards(
    client: AsyncClient, app: FastAPI
) -> None:
    command = await headers(client)
    original = (await create(client, command))["request"]
    path = f"/api/v1/requests/{original['id']}"
    changed = await client.patch(
        path, headers=command, json={"expected_version": 1, "customer_notes": "Revised test note"}
    )
    assert changed.status_code == 200
    assert changed.json()["version"] == changed.json()["revision"] == 2
    assert changed.json()["canonical_spec_sha256"] != original["canonical_spec_sha256"]
    stale = await client.patch(
        path,
        headers={**command, "Idempotency-Key": uuid4().hex},
        json={"expected_version": 1, "customer_notes": "Stale update"},
    )
    assert stale.status_code == 409 and stale.json()["code"] == "stale_version"
    cancelled = await client.post(
        path + "/transitions",
        headers=command,
        json={"expected_version": 2, "target": "cancelled", "reason": "No longer needed"},
    )
    assert (
        cancelled.status_code == 200
        and cancelled.json()["version"] == 3
        and cancelled.json()["revision"] == 2
    )
    assert (
        await client.post(
            path + "/transitions",
            headers={**command, "Idempotency-Key": uuid4().hex},
            json={"expected_version": 3, "target": "cancelled", "reason": "Try twice"},
        )
    ).status_code == 409
    assert (
        await client.patch(
            path,
            headers={**command, "Idempotency-Key": uuid4().hex},
            json={"expected_version": 3, "customer_notes": "After cancellation"},
        )
    ).status_code == 409
    assert await counts(app) == [1, 1, 3, 3, 3]


async def test_submission_fails_closed_without_future_intake_validation(
    client: AsyncClient, app: FastAPI
) -> None:
    command = await headers(client)
    row = (await create(client, command))["request"]
    path = f"/api/v1/requests/{row['id']}/transitions"
    blocked = await client.post(
        path,
        headers=command,
        json={"expected_version": 1, "target": "submitted", "reason": "Ready for review"},
    )
    assert blocked.status_code == 409 and blocked.json()["code"] == "intake_not_available"
    future = await client.post(
        path,
        headers=command,
        json={"expected_version": 1, "target": "analyzing", "reason": "Skip validation"},
    )
    assert future.status_code == 422
    assert await counts(app) == [1, 1, 1, 1, 1]


@pytest.mark.parametrize(
    "field,value",
    [
        ("customer_id", str(uuid4())),
        ("role", "owner"),
        ("mode", "live"),
        ("status", "submitted"),
        ("service_project_id", str(uuid4())),
        ("stage_kind", "printing"),
    ],
)
async def test_client_cannot_choose_trusted_business_fields(
    client: AsyncClient, app: FastAPI, field: str, value: str
) -> None:
    response = await client.post(
        "/api/v1/requests",
        headers=await headers(client),
        json={"service_type": "printing", field: value},
    )
    assert response.status_code == 422
    assert await counts(app) == [0] * 5


@pytest.mark.parametrize("kind", ["operator", "unknown", "", None])
async def test_unknown_service_types_rejected(client: AsyncClient, kind: str | None) -> None:
    response = await client.post(
        "/api/v1/requests", headers=await headers(client), json={"service_type": kind}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("note", ["\x00", "\ud800", "x" * 2001])
async def test_malformed_or_oversize_text_is_rejected(client: AsyncClient, note: str) -> None:
    # Escaped surrogate is valid JSON transport but invalid PostgreSQL UTF-8 text.
    import json

    response = await client.post(
        "/api/v1/requests",
        headers={**await headers(client), "Content-Type": "application/json"},
        content=json.dumps({"service_type": "printing", "customer_notes": note}),
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "boundary",
    [
        "anonymous",
        "missing_csrf",
        "wrong_csrf",
        "wrong_origin",
        "missing_origin",
        "missing_key",
        "bad_key",
        "oversize",
    ],
)
async def test_business_command_security_boundaries(
    client: AsyncClient, app: FastAPI, boundary: str
) -> None:
    command = {} if boundary == "anonymous" else await headers(client)
    if boundary == "missing_csrf":
        command.pop("X-CSRF-Token")
    if boundary == "wrong_csrf":
        command["X-CSRF-Token"] = "incorrect"
    if boundary == "wrong_origin":
        command["Origin"] = "https://attacker.example"
    if boundary == "missing_origin":
        del client.headers["Origin"]
    if boundary == "missing_key":
        command.pop("Idempotency-Key")
    if boundary == "bad_key":
        command["Idempotency-Key"] = "invalid/key"
    response = await client.post(
        "/api/v1/requests",
        headers=command,
        json={
            "service_type": "printing",
            "customer_notes": "x" * 33000 if boundary == "oversize" else "",
        },
    )
    expected = (
        401
        if boundary == "anonymous"
        else 422
        if boundary in {"missing_key", "bad_key"}
        else 413
        if boundary == "oversize"
        else 403
    )
    assert response.status_code == expected
    assert await counts(app) == [0] * 5


async def test_idempotent_retry_returns_original_response_and_rejects_changed_payload(
    client: AsyncClient, app: FastAPI
) -> None:
    command = await headers(client)
    result = await create(client, command)
    assert await create(client, command) == result
    conflict = await client.post(
        "/api/v1/requests", headers=command, json={"service_type": "custom_design"}
    )
    assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_conflict"
    row = result["request"]
    path = f"/api/v1/requests/{row['id']}"
    patch = {"expected_version": 1, "customer_notes": "Updated"}
    first = await client.patch(path, headers=command, json=patch)
    assert first.status_code == 200
    assert (await client.patch(path, headers=command, json=patch)).json() == first.json()
    assert await counts(app) == [1, 1, 2, 2, 2]


async def test_concurrent_duplicate_commands_across_application_instances(
    client: AsyncClient, app: FastAPI, clean_database: str
) -> None:
    command = await headers(client)
    token = client.cookies.get("__Host-3dps_session")
    second = create_app(make_settings(clean_database))
    async with (
        second.router.lifespan_context(second),
        AsyncClient(
            transport=ASGITransport(app=second),
            base_url=ORIGIN,
            headers={"Origin": ORIGIN, "Cookie": f"__Host-3dps_session={token}"},
        ) as other,
    ):
        body = {"service_type": "design_and_print"}
        results = await asyncio.gather(
            *(
                http.post("/api/v1/requests", headers=command, json=body)
                for http in [client, other, client, other]
            )
        )
    assert all(response.status_code == 201 for response in results)
    assert all(response.json() == results[0].json() for response in results)
    assert await counts(app) == [1] * 5


async def test_concurrent_different_commands_allow_one_version_winner(
    client: AsyncClient, app: FastAPI
) -> None:
    command = await headers(client)
    row = (await create(client, command))["request"]
    results = await asyncio.gather(
        *(
            client.patch(
                f"/api/v1/requests/{row['id']}",
                headers={**command, "Idempotency-Key": uuid4().hex},
                json={"expected_version": 1, "customer_notes": note},
            )
            for note in ["First writer", "Second writer"]
        )
    )
    assert sorted(response.status_code for response in results) == [200, 409]
    assert await counts(app) == [1, 1, 2, 2, 2]


@pytest.mark.parametrize(
    "failing_table", ["audit_logs", "notification_outbox", "idempotency_records"]
)
async def test_database_failure_rolls_back_entire_command_and_key_can_retry(
    client: AsyncClient, app: FastAPI, failing_table: str
) -> None:
    command = await headers(client)

    def fail_insert(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO " + failing_table):
            raise SQLAlchemyError("Synthetic transaction failure")

    event.listen(app.state.engine.sync_engine, "before_cursor_execute", fail_insert)
    try:
        response = await client.post(
            "/api/v1/requests",
            headers=command,
            json={"service_type": "printing", "customer_notes": "Test draft"},
        )
        assert response.status_code == 503
        assert "Synthetic" not in response.text
    finally:
        event.remove(app.state.engine.sync_engine, "before_cursor_execute", fail_insert)
    assert await counts(app) == [0] * 5
    await create(client, command)
    assert await counts(app) == [1] * 5


async def test_outbox_failure_rolls_back_existing_draft_version(
    client: AsyncClient, app: FastAPI
) -> None:
    command = await headers(client)
    original = (await create(client, command))["request"]

    def fail_insert(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO notification_outbox"):
            raise SQLAlchemyError("Synthetic failure")

    event.listen(app.state.engine.sync_engine, "before_cursor_execute", fail_insert)
    try:
        result = await client.patch(
            f"/api/v1/requests/{original['id']}",
            headers=command,
            json={"expected_version": 1, "customer_notes": "Must roll back"},
        )
        assert result.status_code == 503
    finally:
        event.remove(app.state.engine.sync_engine, "before_cursor_execute", fail_insert)
    assert (await client.get(f"/api/v1/requests/{original['id']}")).json() == original
    assert await counts(app) == [1] * 5


async def test_revocation_between_dependency_and_command_prevents_write(
    client: AsyncClient, app: FastAPI
) -> None:
    await headers(client)
    principal = await resolve_session(
        app.state.session_factory, app.state.settings, client.cookies.get("__Host-3dps_session")
    )
    await revoke_session(app.state.session_factory, principal.session.id)
    with pytest.raises(AuthError) as failure:
        await create_request(
            app.state.session_factory,
            app.state.settings,
            principal,
            uuid4().hex,
            CreateRequest(service_type="printing"),
        )
    assert failure.value.status == 401
    assert await counts(app) == [0] * 5


async def test_database_enforces_lineage_stage_mode_and_append_only_audits(
    client: AsyncClient, app: FastAPI
) -> None:
    command = await headers(client)
    result = await create(client, command, "design_and_print")
    other = await create(client, {**command, "Idempotency-Key": uuid4().hex}, "printing")
    statements = [
        (
            "UPDATE service_requests SET service_project_id=:other",
            {"other": other["project"]["id"]},
        ),
        ("UPDATE service_requests SET stage_kind='printing'", {}),
        ("UPDATE service_requests SET mode='live'", {}),
        ("UPDATE service_projects SET mode='live'", {}),
        ("UPDATE service_requests SET status='submitted'", {}),
        ("UPDATE service_requests SET version=0", {}),
        ("UPDATE audit_logs SET reason='Rewrite history'", {}),
        ("DELETE FROM audit_logs", {}),
    ]
    for statement, params in statements:
        with pytest.raises(IntegrityError):
            async with app.state.engine.begin() as db:
                await db.execute(text(statement), params)
    async with app.state.session_factory() as db:
        row = await db.get(ServiceRequest, UUID(result["request"]["id"]))
        assert row and row.stage_kind == "design"
    assert await counts(app) == [2] * 5


async def test_bounded_pagination_health_and_owner_readiness(client: AsyncClient) -> None:
    command = await headers(client)
    for _ in range(3):
        await create(client, {**command, "Idempotency-Key": uuid4().hex})
    for path in ["/api/v1/projects", "/api/v1/requests"]:
        first = (await client.get(path + "?limit=2")).json()
        second = (await client.get(path + "?limit=2&offset=2")).json()
        assert len(first["items"]) == 2 and first["next_offset"] == 2
        assert len(second["items"]) == 1 and second["next_offset"] is None
        assert not {row["id"] for row in first["items"]} & {row["id"] for row in second["items"]}
        assert (await client.get(path + "?limit=101")).status_code == 422
        assert (await client.get(path + "?offset=-1")).status_code == 422
        assert (await client.get(path + "?offset=10001")).status_code == 422
    assert (await client.get("/api/v1/health")).status_code == 200
    assert (await client.get("/api/v1/ready")).status_code == 403
    await headers(client, OWNER_ID)
    assert (await client.get("/api/v1/ready")).status_code == 200


async def test_removed_owner_cannot_replay_cached_customer_response(
    client: AsyncClient, app: FastAPI, clean_database: str
) -> None:
    original = await create(client, await headers(client))
    owner_command = await headers(client, OWNER_ID)
    path = f"/api/v1/requests/{original['request']['id']}/transitions"
    body = {"expected_version": 1, "target": "cancelled", "reason": "Owner test cancellation"}
    assert (await client.post(path, headers=owner_command, json=body)).status_code == 200
    token = client.cookies.get("__Host-3dps_session")
    replacement = create_app(make_settings(clean_database, owner_telegram_ids=""))
    async with (
        replacement.router.lifespan_context(replacement),
        AsyncClient(
            transport=ASGITransport(app=replacement),
            base_url=ORIGIN,
            headers={"Origin": ORIGIN, "Cookie": f"__Host-3dps_session={token}"},
        ) as demoted,
    ):
        assert (await demoted.post(path, headers=owner_command, json=body)).status_code == 404
        assert (
            await demoted.get(f"/api/v1/requests/{original['request']['id']}")
        ).status_code == 404
    assert await counts(app) == [1, 1, 2, 2, 2]


async def test_concurrent_login_rotation_and_business_command_do_not_deadlock(
    client: AsyncClient, app: FastAPI
) -> None:
    command = await headers(client)
    from tests.signing import signed_data

    results = await asyncio.wait_for(
        asyncio.gather(
            client.post("/api/v1/requests", headers=command, json={"service_type": "printing"}),
            client.post("/api/v1/auth/telegram", json={"init_data": signed_data()}),
        ),
        timeout=5,
    )
    assert results[1].status_code == 200
    assert results[0].status_code in {201, 401}
    assert await counts(app) == ([1] * 5 if results[0].status_code == 201 else [0] * 5)


async def test_idempotency_keys_are_scoped_to_customer(client: AsyncClient, app: FastAPI) -> None:
    first = await headers(client)
    first_row = await create(client, first)
    second = await headers(client, CUSTOMER_ID + 1)
    second["Idempotency-Key"] = first["Idempotency-Key"]
    second_row = await create(client, second)
    assert first_row["project"]["id"] != second_row["project"]["id"]
    assert first_row["project"]["customer_id"] != second_row["project"]["customer_id"]
    assert await counts(app) == [2] * 5


@pytest.mark.parametrize("method", ["PATCH", "POST"])
async def test_existing_request_mutations_require_csrf_and_exact_origin(
    client: AsyncClient, app: FastAPI, method: str
) -> None:
    command = await headers(client)
    row = (await create(client, command))["request"]
    path = f"/api/v1/requests/{row['id']}"
    body = (
        {"expected_version": 1, "customer_notes": "Unauthorized edit"}
        if method == "PATCH"
        else {"expected_version": 1, "target": "cancelled", "reason": "Unauthorized cancel"}
    )
    if method == "POST":
        path += "/transitions"
    missing_csrf = {"Idempotency-Key": uuid4().hex}
    assert (await client.request(method, path, headers=missing_csrf, json=body)).status_code == 403
    assert (
        await client.request(
            method, path, headers={**command, "Origin": "https://attacker.example"}, json=body
        )
    ).status_code == 403
    assert await counts(app) == [1] * 5


async def test_database_rejects_duplicate_stage_and_cross_customer_lineage(
    client: AsyncClient, app: FastAPI
) -> None:
    first = await create(client, await headers(client))
    second = await create(client, await headers(client, CUSTOMER_ID + 1))

    async with app.state.session_factory() as db:
        row = await db.get(ServiceRequest, UUID(first["request"]["id"]))
        assert row
        copy = {
            column.name: getattr(row, column.name)
            for column in ServiceRequest.__table__.columns
            if column.name != "id"
        }
    with pytest.raises(IntegrityError):
        async with app.state.engine.begin() as connection:
            await connection.execute(ServiceRequest.__table__.insert().values(**copy))
    with pytest.raises(IntegrityError):
        async with app.state.engine.begin() as connection:
            await connection.execute(
                text("UPDATE service_requests SET customer_id=:customer WHERE id=:request"),
                {"customer": second["request"]["customer_id"], "request": first["request"]["id"]},
            )
    assert await counts(app) == [2] * 5


async def test_blank_cancellation_reason_does_not_change_request(
    client: AsyncClient, app: FastAPI
) -> None:
    command = await headers(client)
    row = (await create(client, command))["request"]
    response = await client.post(
        f"/api/v1/requests/{row['id']}/transitions",
        headers=command,
        json={"expected_version": 1, "target": "cancelled", "reason": "   "},
    )
    assert response.status_code == 422
    assert await counts(app) == [1] * 5


async def test_owner_cancellation_races_customer_edit_without_deadlock(
    client: AsyncClient, app: FastAPI
) -> None:
    customer_command = await headers(client)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=ORIGIN, headers={"Origin": ORIGIN}
    ) as owner:
        owner_command = await headers(owner, OWNER_ID)
        for _ in range(5):
            row = (await create(client, {**customer_command, "Idempotency-Key": uuid4().hex}))[
                "request"
            ]
            path = f"/api/v1/requests/{row['id']}"
            results = await asyncio.wait_for(
                asyncio.gather(
                    client.patch(
                        path,
                        headers={**customer_command, "Idempotency-Key": uuid4().hex},
                        json={"expected_version": 1, "customer_notes": "Customer concurrent edit"},
                    ),
                    owner.post(
                        path + "/transitions",
                        headers={**owner_command, "Idempotency-Key": uuid4().hex},
                        json={
                            "expected_version": 1,
                            "target": "cancelled",
                            "reason": "Owner concurrent decision",
                        },
                    ),
                ),
                timeout=5,
            )
            assert sorted(response.status_code for response in results) == [200, 409]
    assert await counts(app) == [5, 5, 10, 10, 10]


@pytest.mark.parametrize("loss", ["revoked", "expired", "disabled"])
async def test_cached_creation_revalidates_actor_and_session_inside_transaction(
    client: AsyncClient, app: FastAPI, loss: str
) -> None:
    """A stale resolved principal must never unlock a stored private response."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from app.database.models import Session, User

    command = await headers(client)
    await create(client, command)
    principal = await resolve_session(
        app.state.session_factory, app.state.settings, client.cookies.get("__Host-3dps_session")
    )
    async with app.state.session_factory() as db, db.begin():
        if loss == "revoked":
            await db.execute(
                update(Session)
                .where(Session.id == principal.session.id)
                .values(revoked_at=datetime.now(UTC))
            )
        elif loss == "expired":
            await db.execute(
                update(Session)
                .where(Session.id == principal.session.id)
                .values(
                    created_at=datetime.now(UTC) - timedelta(hours=1),
                    expires_at=datetime.now(UTC) - timedelta(minutes=1),
                )
            )
        else:
            await db.execute(update(User).where(User.id == principal.user.id).values(active=False))
    with pytest.raises(AuthError) as failure:
        await create_request(
            app.state.session_factory,
            app.state.settings,
            principal,
            command["Idempotency-Key"],
            CreateRequest(service_type="printing", customer_notes="Test draft"),
        )
    assert failure.value.status == 401
    assert await counts(app) == [1] * 5
