"""M05 integration tests use actual PostgreSQL, verified sessions and private blobs."""

import asyncio
import hashlib
import io
from urllib.parse import quote
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.database.business_models import AuditLog, ServiceRequest
from app.database.design_models import DesignReview
from app.database.intake_models import ProcessingTask, RequestItem
from tests.model_fixtures import BINARY_STL, COMPLETE_SPEC
from tests.signing import CUSTOMER_ID, OWNER_ID
from tests.test_business_foundation import headers
from tests.test_printing_intake import command

BRIEF = {
    "description": "Design a small bracket",
    "intended_use": "Indoor test fixture",
    "dimensions": "30 x 20 x 10",
    "units": "mm",
    "tolerances": "Owner to advise",
    "delivery_kind": "digital",
    "special_requirements": "Rounded edges",
}
SCOPE = {
    "deliverables": "One preview proof and an agreed model",
    "permitted_revisions": 2,
    "exclusions": "No structural certification",
    "includes_digital_delivery": True,
}


def image_bytes(kind: str = "PNG") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (16, 16), "orange").save(output, format=kind)
    return output.getvalue()


async def new_design(
    client: AsyncClient, auth: dict[str, str], kind: str = "custom_design"
) -> dict:
    created = await client.post(
        "/api/v1/requests", headers=command(auth), json={"service_type": kind}
    )
    assert created.status_code == 201, created.text
    request = created.json()["request"]
    result = await client.get(f"/api/v1/requests/{request['id']}/design")
    assert result.status_code == 200, result.text
    return result.json()


async def act(
    client: AsyncClient,
    auth: dict[str, str],
    data: dict,
    action: str,
    extra: dict | None = None,
    owner: bool = False,
    key: str | None = None,
):
    return await client.request(
        "PATCH" if action == "brief" else "POST",
        f"/api/v1/{'owner/' if owner else ''}design-projects/{data['id']}/{action}",
        headers={**command(auth), **({"Idempotency-Key": key} if key else {})},
        json={"expected_version": data["request"]["version"], **(extra or {})},
    )


async def step(
    client: AsyncClient,
    auth: dict[str, str],
    data: dict,
    action: str,
    extra: dict | None = None,
    owner: bool = False,
) -> dict:
    response = await act(client, auth, data, action, extra, owner)
    assert response.status_code == 200, response.text
    return response.json()


async def upload(
    client: AsyncClient,
    auth: dict[str, str],
    data: dict,
    purpose: str,
    content: bytes,
    name: str,
    key: str | None = None,
):
    return await client.post(
        f"/api/v1/requests/{data['request']['id']}/design/files?purpose={purpose}&expected_version={data['request']['version']}",
        headers={
            **command(auth),
            "Idempotency-Key": key or uuid4().hex,
            "Content-Type": "application/octet-stream",
            "X-File-Name": quote(name, safe=""),
            "X-File-Size": str(len(content) or 1),
            "X-Content-SHA256": hashlib.sha256(content).hexdigest(),
        },
        content=content,
    )


async def scoped(client: AsyncClient, combined: bool = False) -> tuple[dict, dict, dict]:
    customer = await headers(client)
    data = await new_design(client, customer, "design_and_print" if combined else "custom_design")
    data = await step(
        client,
        customer,
        data,
        "brief",
        {"brief": {**BRIEF, "delivery_kind": "printing" if combined else "digital"}},
    )
    data = await step(client, customer, data, "submit")
    owner = await headers(client, OWNER_ID)
    data = await step(
        client,
        owner,
        data,
        "scopes",
        {
            "scope": {**SCOPE, "includes_digital_delivery": not combined},
            "reason": "Simulation scope proposal",
        },
        True,
    )
    customer = await headers(client)
    data = await step(
        client, customer, data, "scope-agreements", {"scope_id": data["scopes"][-1]["id"]}
    )
    owner = await headers(client, OWNER_ID)
    return data, customer, owner


async def published(client: AsyncClient, combined: bool = False) -> tuple[dict, dict, dict]:
    data, customer, owner = await scoped(client, combined)
    data = await step(
        client,
        owner,
        data,
        "simulation-fixture",
        {"confirm_simulation": True, "reason": "Explicit test-only quote and paid fixture"},
        True,
    )
    proof = await upload(client, owner, data, "design_proof", image_bytes(), "proof.png")
    assert proof.status_code == 201, proof.text
    data = proof.json()
    preview = data["working_files"][-1]["id"]
    if combined:
        model = await upload(
            client, owner, data, "design_manufacturing", BINARY_STL, "manufacturing.stl"
        )
        assert model.status_code == 201, model.text
        data = model.json()
        extra = {
            "manufacturing_file_id": data["working_files"][-1]["id"],
            "manufacturing_ready": True,
        }
    else:
        extra = {}
    data = await step(
        client,
        owner,
        data,
        "versions",
        {"preview_file_id": preview, "release_notes": "First simulation proof", **extra},
        True,
    )
    return data, customer, owner


async def test_design_only_has_zero_print_items_and_private_reference(
    client: AsyncClient, app: FastAPI
) -> None:
    customer = await headers(client)
    data = await new_design(client, customer)
    assert data["state"] == "draft"
    data = await step(client, customer, data, "brief", {"brief": BRIEF})
    response = await upload(client, customer, data, "design_reference", image_bytes(), "sketch.png")
    assert response.status_code == 201, response.text
    data = response.json()
    file = data["references"][0]
    assert file["purpose"] == "design_reference" and file["request_item_id"] is None
    assert (await client.get(f"/api/v1/files/{file['id']}/download")).content == image_bytes()
    submitted = await step(client, customer, data, "submit")
    assert submitted["state"] == "brief_received" and submitted["request"]["status"] == "submitted"
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(RequestItem)) == 0
        assert await db.scalar(select(func.count()).select_from(ProcessingTask)) == 0
    await headers(client, CUSTOMER_ID + 99)
    assert (await client.get(f"/api/v1/design-projects/{data['id']}")).status_code == 404
    assert (await client.get(f"/api/v1/files/{file['id']}/download")).status_code == 404


async def test_scope_fixture_proof_review_and_combined_printing_lineage(
    client: AsyncClient, app: FastAPI
) -> None:
    data, customer, owner = await published(client, True)
    version = data["versions"][-1]
    model = version["manufacturing_file"]
    customer = await headers(client)
    visible = (await client.get(f"/api/v1/design-projects/{data['id']}")).json()
    assert visible["versions"][-1]["manufacturing_file"] is None
    assert (await client.get(f"/api/v1/files/{model['id']}/download")).status_code == 404
    assert (
        await client.get(f"/api/v1/files/{version['preview']['id']}/download")
    ).status_code == 200
    data = await step(
        client,
        customer,
        visible,
        "reviews",
        {"design_version_id": version["id"], "decision": "approved"},
    )
    owner = await headers(client, OWNER_ID)
    key = uuid4().hex
    converted = await act(
        client, owner, data, "create-print-request", {"design_version_id": version["id"]}, True, key
    )
    assert converted.status_code == 200, converted.text
    assert (
        await act(
            client,
            owner,
            data,
            "create-print-request",
            {"design_version_id": version["id"]},
            True,
            key,
        )
    ).json() == converted.json()
    data = converted.json()
    printing = data["linked_print_request"]
    assert printing["source_design_version_id"] == version["id"]
    assert printing["service_project_id"] == data["request"]["service_project_id"]
    assert printing["status"] == "draft" and data["state"] == "approved"
    attached = await client.post(
        f"/api/v1/owner/design-projects/{data['id']}/attach-print-model",
        headers=command(owner),
        json={"expected_version": printing["version"]},
    )
    assert attached.status_code == 200, attached.text
    customer = await headers(client)
    details = (await client.get(f"/api/v1/requests/{printing['id']}/intake")).json()
    print_item = details["items"][0]
    assert print_item["model_file"]["download_allowed"] is False
    assert (
        await client.get(f"/api/v1/files/{print_item['model_file']['id']}/download")
    ).status_code == 403
    failed = await client.post(
        f"/api/v1/requests/{printing['id']}/submit",
        headers=command(customer),
        json={"expected_version": details["request"]["version"]},
    )
    assert failed.status_code == 422
    updated = await client.patch(
        f"/api/v1/requests/{printing['id']}/items/{print_item['id']}",
        headers=command(customer),
        json={"expected_version": details["request"]["version"], "specification": COMPLETE_SPEC},
    )
    assert updated.status_code == 200, updated.text
    submitted = await client.post(
        f"/api/v1/requests/{printing['id']}/submit",
        headers=command(customer),
        json={"expected_version": updated.json()["request"]["version"]},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["tasks"][0]["state"] == "pending"
    assert (await client.get(f"/api/v1/design-projects/{data['id']}")).json()["state"] == "approved"
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(ServiceRequest)) == 2


async def test_scope_history_and_fixture_are_exact_and_simulation_only(
    client: AsyncClient, app: FastAPI
) -> None:
    data, customer, owner = await scoped(client)
    assert data["state"] == "awaiting_payment" and not data["simulation_fixture"]
    assert data["scopes"][-1]["agreed"] and not data["scopes"][-1]["binding"]
    blocked = await upload(client, owner, data, "design_proof", image_bytes(), "too-early.png")
    assert blocked.status_code == 409
    assert (
        await act(
            client,
            owner,
            data,
            "simulation-fixture",
            {"confirm_simulation": False, "reason": "Test invalid fixture"},
            True,
        )
    ).status_code == 422
    customer = await headers(client)
    assert (
        await act(
            client,
            customer,
            data,
            "simulation-fixture",
            {"confirm_simulation": True, "reason": "Unauthorized fixture"},
            True,
        )
    ).status_code == 403
    owner = await headers(client, OWNER_ID)
    old_scope = data["approved_scope_id"]
    changed = await step(
        client,
        owner,
        data,
        "scopes",
        {"scope": {**SCOPE, "permitted_revisions": 0}, "reason": "Revised scope proposal"},
        True,
    )
    assert len(changed["scopes"]) == 2 and changed["scopes"][0]["agreed"]
    assert changed["approved_scope_id"] is None and not changed["simulation_fixture"]
    customer = await headers(client)
    assert (
        await act(client, customer, changed, "scope-agreements", {"scope_id": old_scope})
    ).status_code == 409
    async with app.state.session_factory() as db:
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(
                    text("UPDATE design_scopes SET specification='{}'::jsonb WHERE id=:id"),
                    {"id": UUID(old_scope)},
                )


async def test_new_proof_does_not_inherit_old_approval_and_concurrent_reviews_conflict(
    client: AsyncClient, app: FastAPI
) -> None:
    data, customer, owner = await published(client)
    first = data["latest_version_id"]
    customer = await headers(client)
    approved = await step(
        client, customer, data, "reviews", {"design_version_id": first, "decision": "approved"}
    )
    owner = await headers(client, OWNER_ID)
    proof = await upload(
        client, owner, approved, "design_proof", b"Second proof notes\n", "version-two.txt"
    )
    assert proof.status_code == 201, proof.text
    data = proof.json()
    data = await step(
        client,
        owner,
        data,
        "versions",
        {
            "preview_file_id": data["working_files"][-1]["id"],
            "release_notes": "New immutable revision",
        },
        True,
    )
    assert data["approved_version_id"] is None and data["latest_version_id"] != first
    customer = await headers(client)
    assert (
        await act(
            client, customer, data, "reviews", {"design_version_id": first, "decision": "approved"}
        )
    ).status_code == 409
    responses = await asyncio.gather(
        act(
            client,
            customer,
            data,
            "reviews",
            {"design_version_id": data["latest_version_id"], "decision": "approved"},
        ),
        act(
            client,
            customer,
            data,
            "reviews",
            {
                "design_version_id": data["latest_version_id"],
                "decision": "changes_requested",
                "feedback": "Please change radius",
            },
        ),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(DesignReview)) == 2
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(
                    text("UPDATE design_versions SET release_notes='changed' WHERE id=:id"),
                    {"id": UUID(first)},
                )


async def test_concurrent_conversion_and_duplicate_stage_guard(
    client: AsyncClient, app: FastAPI
) -> None:
    data, customer, owner = await published(client, True)
    customer = await headers(client)
    data = await step(
        client,
        customer,
        data,
        "reviews",
        {"design_version_id": data["latest_version_id"], "decision": "approved"},
    )
    owner = await headers(client, OWNER_ID)
    key = uuid4().hex
    commands = [
        act(
            client,
            owner,
            data,
            "create-print-request",
            {"design_version_id": data["latest_version_id"]},
            True,
            key,
        )
        for _ in range(2)
    ]
    responses = await asyncio.gather(*commands)
    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    converted = responses[0].json()
    assert (
        await act(
            client,
            owner,
            converted,
            "create-print-request",
            {"design_version_id": data["latest_version_id"]},
            True,
        )
    ).status_code == 409
    assert (
        await act(
            client,
            owner,
            converted,
            "scopes",
            {"scope": SCOPE, "reason": "Cannot replace approved lineage"},
            True,
        )
    ).status_code == 409
    async with app.state.session_factory() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ServiceRequest)
                .where(ServiceRequest.stage_kind == "printing")
            )
            == 1
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "design.print_draft_created")
            )
            == 1
        )
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(
                    text("UPDATE service_requests SET source_design_version_id=NULL WHERE id=:id"),
                    {"id": UUID(converted["linked_print_request"]["id"])},
                )


@pytest.mark.parametrize(
    "content,name",
    [
        (b"<svg><script>alert(1)</script></svg>", "bad.svg"),
        (b"%PDF-1.7 active", "bad.txt"),
        (image_bytes()[:-15], "truncated.png"),
        (b"v 0 0 0\n", "not-image.png"),
        (b"\x00binary", "bad.txt"),
    ],
)
async def test_unsafe_references_fail_without_changing_brief(
    client: AsyncClient, content: bytes, name: str
) -> None:
    customer = await headers(client)
    data = await new_design(client, customer)
    response = await upload(client, customer, data, "design_reference", content, name)
    assert response.status_code in {415, 422}, response.text
    refreshed = (await client.get(f"/api/v1/design-projects/{data['id']}")).json()
    assert (
        refreshed["request"]["version"] == data["request"]["version"]
        and not refreshed["references"]
    )


async def test_unpublished_proof_and_manufacturing_files_stay_owner_private(
    client: AsyncClient,
) -> None:
    data, customer, owner = await scoped(client, True)
    data = await step(
        client,
        owner,
        data,
        "simulation-fixture",
        {"confirm_simulation": True, "reason": "Test-only fixture"},
        True,
    )
    response = await upload(
        client, owner, data, "design_proof", image_bytes("JPEG"), "unpublished.jpg"
    )
    assert response.status_code == 201, response.text
    data = response.json()
    file_id = data["working_files"][-1]["id"]
    customer = await headers(client)
    assert (await client.get(f"/api/v1/files/{file_id}")).status_code == 404
    assert (await client.get(f"/api/v1/files/{file_id}/download")).status_code == 404
    assert (
        await upload(client, customer, data, "design_proof", image_bytes(), "customer.png")
    ).status_code == 403
    assert (
        await act(
            client,
            customer,
            data,
            "scopes",
            {"scope": SCOPE, "reason": "Customer cannot propose owner scope"},
            True,
        )
    ).status_code == 403


async def test_owner_scope_failure_rolls_back_audit_outbox_and_version(
    client: AsyncClient, app: FastAPI
) -> None:
    customer = await headers(client)
    data = await new_design(client, customer)
    data = await step(client, customer, data, "brief", {"brief": BRIEF})
    data = await step(client, customer, data, "submit")
    owner = await headers(client, OWNER_ID)

    def fail(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO notification_outbox"):
            raise SQLAlchemyError("injected M05 test failure")

    event.listen(app.state.engine.sync_engine, "before_cursor_execute", fail)
    try:
        response = await act(
            client, owner, data, "scopes", {"scope": SCOPE, "reason": "Rollback test"}, True
        )
        assert response.status_code == 503
    finally:
        event.remove(app.state.engine.sync_engine, "before_cursor_execute", fail)
    refreshed = (await client.get(f"/api/v1/design-projects/{data['id']}")).json()
    assert not refreshed["scopes"] and refreshed["request"]["version"] == data["request"]["version"]


@pytest.mark.parametrize(
    "action,extra,owner_path",
    [
        ("brief", {"brief": BRIEF}, False),
        ("submit", {}, False),
        ("scope-agreements", {"scope_id": "00000000-0000-4000-8000-000000000001"}, False),
        (
            "reviews",
            {"design_version_id": "00000000-0000-4000-8000-000000000001", "decision": "approved"},
            False,
        ),
        ("scopes", {"scope": SCOPE, "reason": "Unauthorized scope"}, True),
        (
            "create-print-request",
            {"design_version_id": "00000000-0000-4000-8000-000000000001"},
            True,
        ),
    ],
)
async def test_cross_customer_commands_cannot_reach_private_design(
    client: AsyncClient, action: str, extra: dict, owner_path: bool
) -> None:
    customer = await headers(client)
    data = await new_design(client, customer)
    stranger = await headers(client, CUSTOMER_ID + 88)
    response = await act(client, stranger, data, action, extra, owner_path)
    assert response.status_code == 404
    assert (await client.get("/api/v1/design-projects")).json()["items"] == []


async def test_rejected_upload_can_be_replaced_without_poisoning_draft(client: AsyncClient) -> None:
    customer = await headers(client)
    data = await new_design(client, customer)
    assert (
        await upload(client, customer, data, "design_reference", b"\x00invalid", "bad.txt")
    ).status_code == 415
    data = await step(client, customer, data, "brief", {"brief": BRIEF})
    uploaded = await upload(
        client,
        customer,
        data,
        "design_reference",
        b"Valid replacement drawing notes\n",
        "notes.txt",
    )
    assert uploaded.status_code == 201
    submitted = await step(client, customer, uploaded.json(), "submit")
    assert submitted["state"] == "brief_received" and len(submitted["references"]) == 1


async def test_design_submission_enforces_csrf_origin_and_current_version(
    client: AsyncClient,
) -> None:
    customer = await headers(client)
    data = await new_design(client, customer)
    assert (await act(client, customer, data, "submit")).status_code == 422
    changed = await step(client, customer, data, "brief", {"brief": BRIEF})
    assert (
        await act(
            client, customer, data, "brief", {"brief": {**BRIEF, "description": "stale edit"}}
        )
    ).status_code == 409
    path = f"/api/v1/design-projects/{data['id']}/submit"
    body = {"expected_version": changed["request"]["version"]}
    assert (
        await client.post(path, headers={"Idempotency-Key": uuid4().hex}, json=body)
    ).status_code == 403
    assert (
        await client.post(
            path, headers={**command(customer), "Origin": "https://untrusted.example"}, json=body
        )
    ).status_code == 403
    assert (
        await act(
            client, customer, changed, "brief", {"brief": {**BRIEF, "description": "bad\x00brief"}}
        )
    ).status_code == 422


async def test_design_only_never_converts_to_print_even_after_proof_approval(
    client: AsyncClient,
) -> None:
    data, customer, owner = await published(client)
    customer = await headers(client)
    data = await step(
        client,
        customer,
        data,
        "reviews",
        {"design_version_id": data["latest_version_id"], "decision": "approved"},
    )
    owner = await headers(client, OWNER_ID)
    response = await act(
        client,
        owner,
        data,
        "create-print-request",
        {"design_version_id": data["latest_version_id"]},
        True,
    )
    assert response.status_code == 409
    assert (await client.get(f"/api/v1/design-projects/{data['id']}")).json()[
        "linked_print_request"
    ] is None


async def test_combined_conversion_requires_approval_and_rejects_wrong_manufacturing_bytes(
    client: AsyncClient,
) -> None:
    data, customer, owner = await published(client, True)
    assert (
        await act(
            client,
            owner,
            data,
            "create-print-request",
            {"design_version_id": data["latest_version_id"]},
            True,
        )
    ).status_code == 409
    customer = await headers(client)
    data = await step(
        client,
        customer,
        data,
        "reviews",
        {"design_version_id": data["latest_version_id"], "decision": "approved"},
    )
    assert (
        await act(
            client,
            customer,
            data,
            "create-print-request",
            {"design_version_id": data["latest_version_id"]},
            True,
        )
    ).status_code == 403
    owner = await headers(client, OWNER_ID)
    data = await step(
        client,
        owner,
        data,
        "create-print-request",
        {"design_version_id": data["latest_version_id"]},
        True,
    )
    customer = await headers(client)
    printing = data["linked_print_request"]
    wrong = BINARY_STL.replace(b"\x00", b"\x01", 1)
    response = await client.post(
        f"/api/v1/requests/{printing['id']}/files?item_id={data['linked_print_item_id']}&expected_version={printing['version']}",
        headers={
            **command(customer),
            "Content-Type": "application/octet-stream",
            "X-File-Name": "wrong.stl",
            "X-File-Size": str(len(wrong)),
            "X-Content-SHA256": hashlib.sha256(wrong).hexdigest(),
        },
        content=wrong,
    )
    assert response.status_code == 422
    unchanged = (await client.get(f"/api/v1/requests/{printing['id']}/intake")).json()
    assert (
        unchanged["items"][0]["model_file"] is None
        and unchanged["request"]["version"] == printing["version"]
    )


async def test_customer_requesting_revision_preserves_published_proof_and_records_feedback(
    client: AsyncClient, app: FastAPI
) -> None:
    data, customer, owner = await published(client)
    version = data["latest_version_id"]
    customer = await headers(client)
    changed = await step(
        client,
        customer,
        data,
        "reviews",
        {
            "design_version_id": version,
            "decision": "changes_requested",
            "feedback": "Please round the corner more.",
        },
    )
    assert changed["state"] == "designing" and changed["approved_version_id"] is None
    assert changed["versions"][-1]["review"]["feedback"] == "Please round the corner more."
    owner = await headers(client, OWNER_ID)
    assert (
        await act(
            client,
            owner,
            changed,
            "reviews",
            {"design_version_id": version, "decision": "approved"},
        )
    ).status_code == 403
    async with app.state.session_factory() as db:
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(
                    text("DELETE FROM design_reviews WHERE design_version_id=:id"),
                    {"id": UUID(version)},
                )


async def test_draft_reference_removal_updates_revision_and_cleans_private_blob(
    client: AsyncClient, app: FastAPI
) -> None:
    customer = await headers(client)
    data = await new_design(client, customer)
    response = await upload(
        client, customer, data, "design_reference", b"A removable reference note\n", "reference.txt"
    )
    assert response.status_code == 201
    data = response.json()
    file = data["references"][0]
    removed = await step(client, customer, data, "remove-reference", {"file_id": file["id"]})
    assert not removed["references"]
    assert removed["request"]["revision"] == data["request"]["revision"] + 1
    assert (await client.get(f"/api/v1/files/{file['id']}/download")).status_code == 409
    async with app.state.session_factory() as db:
        from app.database.intake_models import UploadedFile

        row = await db.get(UploadedFile, UUID(file["id"]))
        assert row.storage_state == "deleted"


async def test_retained_m04_upload_key_and_cached_response_remain_compatible(
    client: AsyncClient, app: FastAPI
) -> None:
    import json

    from app.database.business_models import IdempotencyRecord
    from app.database.intake_models import UploadedFile
    from tests.test_printing_intake import draft, item
    from tests.test_printing_intake import upload as model_upload

    customer = await headers(client)
    details = await item(client, customer, await draft(client, customer))
    key = uuid4().hex
    result = await model_upload(client, customer, details, key=key)
    assert result.status_code == 201
    model = result.json()["items"][0]["model_file"]
    old_fingerprint = hashlib.sha256(
        json.dumps(
            {
                "item": details["items"][0]["id"],
                "name": "triangle.stl",
                "size": len(BINARY_STL),
                "sha256": hashlib.sha256(BINARY_STL).hexdigest(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    async with app.state.session_factory() as db, db.begin():
        file = await db.get(UploadedFile, UUID(model["id"]))
        assert file.fingerprint == old_fingerprint
        cached = await db.get(IdempotencyRecord, (file.owner_id, f"upload.attach:{file.id}", key))
        old_response = json.loads(json.dumps(cached.response_json))
        old_response["request"].pop("source_design_version_id", None)
        for field in ["model_file", "latest_upload"]:
            old_response["items"][0][field].pop("purpose", None)
            old_response["items"][0][field].pop("download_allowed", None)
        cached.response_json = old_response
    replay = await model_upload(client, customer, details, key=key)
    assert replay.status_code == 201, replay.text
    assert replay.json() == result.json()
