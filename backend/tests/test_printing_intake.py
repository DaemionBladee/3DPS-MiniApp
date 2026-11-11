import hashlib
from urllib.parse import quote
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from app.database.business_models import AuditLog, NotificationOutbox, ServiceRequest
from app.database.intake_models import ProcessingTask, UploadedFile
from tests.model_fixtures import ASCII_STL, BINARY_STL, COMPLETE_SPEC, OBJ, three_mf
from tests.signing import CUSTOMER_ID, OWNER_ID
from tests.test_business_foundation import headers


def command(auth: dict[str, str]) -> dict[str, str]:
    return {**auth, "Idempotency-Key": uuid4().hex}


async def draft(client: AsyncClient, auth: dict[str, str]) -> dict:
    response = await client.post(
        "/api/v1/requests", headers=command(auth), json={"service_type": "printing"}
    )
    assert response.status_code == 201, response.text
    return response.json()["request"]


async def item(
    client: AsyncClient, auth: dict[str, str], row: dict, spec: dict | None = None
) -> dict:
    response = await client.post(
        f"/api/v1/requests/{row['id']}/items",
        headers=command(auth),
        json={"expected_version": row["version"], "specification": spec or COMPLETE_SPEC},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def upload(
    client: AsyncClient,
    auth: dict[str, str],
    details: dict,
    data: bytes = BINARY_STL,
    name: str = "triangle.stl",
    key: str | None = None,
):
    row = details["request"]
    item_id = details["items"][-1]["id"]
    return await client.post(
        f"/api/v1/requests/{row['id']}/files?item_id={item_id}&expected_version={row['version']}",
        content=data,
        headers={
            **command(auth),
            "Idempotency-Key": key or uuid4().hex,
            "Content-Type": "application/octet-stream",
            "X-File-Name": quote(name, safe=""),
            "X-File-Size": str(len(data) or 1),
            "X-Content-SHA256": hashlib.sha256(data).hexdigest(),
        },
    )


@pytest.mark.parametrize(
    ("data", "name", "format"),
    [
        (BINARY_STL, "triangle.stl", "stl"),
        (ASCII_STL, "ascii.stl", "stl"),
        (OBJ, "mesh.obj", "obj"),
        (three_mf(), "mesh.3mf", "3mf"),
    ],
)
async def test_valid_model_upload_is_private_and_submits_pending(
    client: AsyncClient, app: FastAPI, data: bytes, name: str, format: str
) -> None:
    auth = await headers(client)
    details = await item(client, auth, await draft(client, auth))
    response = await upload(client, auth, details, data, name)
    assert response.status_code == 201, response.text
    details = response.json()
    model = details["items"][0]["model_file"]
    assert model["format"] == format and model["sha256"] == hashlib.sha256(data).hexdigest()
    assert model["validation_status"] == "validated" and model["storage_state"] == "ready"
    assert "storage_key" not in response.text and str(app.state.storage.root) not in response.text
    downloaded = await client.get(f"/api/v1/files/{model['id']}/download")
    assert downloaded.status_code == 200 and downloaded.content == data
    assert "attachment;" in downloaded.headers["content-disposition"]
    assert (
        downloaded.headers["cache-control"] == "no-store"
        and downloaded.headers["x-content-type-options"] == "nosniff"
    )
    assert (await client.get(f"/api/v1/files/{model['id']}")).json()["sha256"] == model["sha256"]
    row = details["request"]
    submitted = await client.post(
        f"/api/v1/requests/{row['id']}/submit",
        headers=command(auth),
        json={"expected_version": row["version"]},
    )
    assert submitted.status_code == 200, submitted.text
    result = submitted.json()
    assert result["request"]["status"] == "submitted"
    assert result["request"]["submitted_revision"] == row["revision"]
    assert result["request"]["submitted_spec"]["items"][0]["file"]["sha256"] == model["sha256"]
    assert len(result["tasks"]) == 1 and result["tasks"][0]["state"] == "pending"
    status = (await client.get(f"/api/v1/requests/{row['id']}/analysis")).json()
    assert status["state"] == "pending" and not status["processing_available"]
    assert "analyzed" not in submitted.text and "price" not in submitted.text
    async with app.state.session_factory() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "request.submitted")
            )
            == 1
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(NotificationOutbox)
                .where(NotificationOutbox.event_type == "request.submitted")
            )
            == 1
        )


async def test_multiple_models_resume_and_idempotent_submission(
    client: AsyncClient, app: FastAPI
) -> None:
    auth = await headers(client)
    details = await item(client, auth, await draft(client, auth))
    uploaded = await upload(client, auth, details)
    assert uploaded.status_code == 201, uploaded.text
    details = await item(client, auth, uploaded.json()["request"])
    uploaded = await upload(client, auth, details, OBJ, "second.obj")
    assert uploaded.status_code == 201, uploaded.text
    details = uploaded.json()
    row = details["request"]
    resumed = await client.get(f"/api/v1/requests/{row['id']}/intake")
    assert resumed.status_code == 200 and len(resumed.json()["items"]) == 2
    key = command(auth)
    body = {"expected_version": row["version"]}
    first = await client.post(f"/api/v1/requests/{row['id']}/submit", headers=key, json=body)
    assert first.status_code == 200, first.text
    assert (
        await client.post(f"/api/v1/requests/{row['id']}/submit", headers=key, json=body)
    ).json() == first.json()
    assert (
        await client.post(f"/api/v1/requests/{row['id']}/submit", headers=command(auth), json=body)
    ).status_code == 409
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(ProcessingTask)) == 2


@pytest.mark.parametrize(
    ("data", "name", "status"),
    [
        (b"", "empty.stl", 422),
        (b"random invalid", "bad.stl", 415),
        (BINARY_STL[:-2], "truncated.stl", 422),
        (OBJ + b"mtllib ../secrets.mtl\n", "unsafe.obj", 415),
        (OBJ, "wrong.stl", 415),
        (three_mf({"../escape": b"x"}), "escape.3mf", 422),
    ],
)
async def test_bad_models_leave_draft_unchanged(
    client: AsyncClient, app: FastAPI, data: bytes, name: str, status: int
) -> None:
    auth = await headers(client)
    before = await item(client, auth, await draft(client, auth))
    response = await upload(client, auth, before, data, name)
    assert response.status_code == status, response.text
    after = (await client.get(f"/api/v1/requests/{before['request']['id']}/intake")).json()
    assert after["request"] == before["request"] and after["items"][0]["model_file"] is None
    assert not list((app.state.storage.root / "ready").iterdir())
    async with app.state.session_factory() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(UploadedFile)
                .where(UploadedFile.storage_state != "deleted")
            )
            == 0
        )


async def test_cross_customer_cannot_access_model_or_owner_api(client: AsyncClient) -> None:
    auth = await headers(client)
    details = await item(client, auth, await draft(client, auth))
    response = await upload(client, auth, details)
    assert response.status_code == 201, response.text
    result = response.json()
    file_id = result["items"][0]["model_file"]["id"]
    request_id = result["request"]["id"]
    stranger = await headers(client, CUSTOMER_ID + 1)
    for path in [
        f"/api/v1/files/{file_id}",
        f"/api/v1/files/{file_id}/download",
        f"/api/v1/requests/{request_id}/intake",
        f"/api/v1/requests/{request_id}/analysis",
    ]:
        assert (await client.get(path)).status_code == 404
    assert (await client.get("/api/v1/owner/requests")).status_code == 403
    assert (
        await client.post(
            f"/api/v1/requests/{request_id}/submit",
            headers=command(stranger),
            json={"expected_version": 3},
        )
    ).status_code == 404
    await headers(client, OWNER_ID)
    assert (await client.get(f"/api/v1/requests/{request_id}/intake")).status_code == 200
    assert (await client.get(f"/api/v1/files/{file_id}/download")).status_code == 200


async def test_incomplete_items_and_stale_submission_fail_without_tasks(
    client: AsyncClient, app: FastAPI
) -> None:
    auth = await headers(client)
    row = await draft(client, auth)
    assert (
        await client.post(
            f"/api/v1/requests/{row['id']}/submit",
            headers=command(auth),
            json={"expected_version": row["version"]},
        )
    ).status_code == 422
    details = await item(client, auth, row, {"quantity": 1})
    uploaded = await upload(client, auth, details)
    assert uploaded.status_code == 201
    row = uploaded.json()["request"]
    assert (
        await client.post(
            f"/api/v1/requests/{row['id']}/submit",
            headers=command(auth),
            json={"expected_version": row["version"] - 1},
        )
    ).status_code == 409
    assert (
        await client.post(
            f"/api/v1/requests/{row['id']}/submit",
            headers=command(auth),
            json={"expected_version": row["version"]},
        )
    ).status_code == 422
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(ProcessingTask)) == 0


async def test_spec_autosave_revision_hash_and_resume(client: AsyncClient) -> None:
    auth = await headers(client)
    data = await item(client, auth, await draft(client, auth))
    uploaded = await upload(client, auth, data)
    assert uploaded.status_code == 201
    data = uploaded.json()
    row = data["request"]
    item_id = data["items"][0]["id"]
    changed = await client.patch(
        f"/api/v1/requests/{row['id']}/items/{item_id}",
        headers=command(auth),
        json={
            "expected_version": row["version"],
            "specification": {
                **COMPLETE_SPEC,
                "quantity": 7,
                "special_requirements": "Text must be legible",
            },
        },
    )
    assert changed.status_code == 200, changed.text
    value = changed.json()
    assert value["request"]["revision"] == row["revision"] + 1
    assert value["request"]["canonical_spec_sha256"] != row["canonical_spec_sha256"]
    assert value["items"][0]["request_revision"] == value["request"]["revision"]
    preferences = await client.patch(
        f"/api/v1/requests/{row['id']}/intake",
        headers=command(auth),
        json={
            "expected_version": value["request"]["version"],
            "customer_notes": "For a test fit",
            "fulfillment_method": "delivery",
            "fulfillment_notes": "Township preference only",
        },
    )
    assert preferences.status_code == 200, preferences.text
    await headers(client)  # Fresh legitimate session, same customer and saved draft.
    resumed = (await client.get(f"/api/v1/requests/{row['id']}/intake")).json()
    assert resumed == preferences.json()
    assert resumed["items"][0]["specification"]["quantity"] == 7
    assert resumed["request"]["fulfillment_method"] == "delivery"


async def test_concurrent_edits_and_submissions_have_single_winners(
    client: AsyncClient, app: FastAPI
) -> None:
    import asyncio

    auth = await headers(client)
    details = await item(client, auth, await draft(client, auth))
    uploaded = await upload(client, auth, details)
    assert uploaded.status_code == 201
    details = uploaded.json()
    row = details["request"]
    identity = details["items"][0]["id"]
    responses = await asyncio.gather(
        *(
            client.patch(
                f"/api/v1/requests/{row['id']}/items/{identity}",
                headers=command(auth),
                json={
                    "expected_version": row["version"],
                    "specification": {**COMPLETE_SPEC, "quantity": quantity},
                },
            )
            for quantity in [3, 4]
        )
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    saved = (await client.get(f"/api/v1/requests/{row['id']}/intake")).json()["request"]
    key = command(auth)
    submitted = await asyncio.gather(
        *(
            client.post(
                f"/api/v1/requests/{row['id']}/submit",
                headers=key,
                json={"expected_version": saved["version"]},
            )
            for _ in range(3)
        )
    )
    assert all(response.status_code == 200 for response in submitted)
    assert all(response.json() == submitted[0].json() for response in submitted)
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(ProcessingTask)) == 1
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "request.submitted")
            )
            == 1
        )


async def test_upload_key_replay_cannot_duplicate_attachment_or_change_bytes(
    client: AsyncClient, app: FastAPI
) -> None:
    auth = await headers(client)
    details = await item(client, auth, await draft(client, auth))
    key = uuid4().hex
    first = await upload(client, auth, details, key=key)
    assert first.status_code == 201, first.text
    second = await upload(client, auth, details, key=key)
    assert second.status_code == 201 and second.json() == first.json()
    assert (await upload(client, auth, details, ASCII_STL, key=key)).status_code == 409
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(UploadedFile)) == 1
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "request.file_attached")
            )
            == 1
        )


@pytest.mark.parametrize("boundary", ["csrf", "origin", "type", "size", "checksum", "path"])
async def test_upload_auth_transport_and_size_boundaries(
    client: AsyncClient, app: FastAPI, boundary: str
) -> None:
    auth = await headers(client)
    data = await item(client, auth, await draft(client, auth))
    row = data["request"]
    supplied = {
        **command(auth),
        "Content-Type": "application/octet-stream",
        "X-File-Name": "triangle.stl",
        "X-File-Size": str(len(BINARY_STL)),
        "X-Content-SHA256": hashlib.sha256(BINARY_STL).hexdigest(),
    }
    expected = {"csrf": 403, "origin": 403, "type": 415, "size": 413, "checksum": 422, "path": 422}[
        boundary
    ]
    if boundary == "csrf":
        supplied.pop("X-CSRF-Token")
    if boundary == "origin":
        supplied["Origin"] = "https://attacker.invalid"
    if boundary == "type":
        supplied["Content-Type"] = "image/png"
    if boundary == "size":
        supplied["X-File-Size"] = str(app.state.settings.upload_max_bytes + 1)
    if boundary == "checksum":
        supplied["X-Content-SHA256"] = "0" * 64
    if boundary == "path":
        supplied["X-File-Name"] = "..%2Fsecret.stl"
    response = await client.post(
        f"/api/v1/requests/{row['id']}/files?item_id={data['items'][0]['id']}&expected_version={row['version']}",
        headers=supplied,
        content=BINARY_STL,
    )
    assert response.status_code == expected, response.text
    assert (await client.get(f"/api/v1/requests/{row['id']}/intake")).json()["request"] == row
    assert not list((app.state.storage.root / "ready").iterdir())


@pytest.mark.parametrize("scope", ["request", "user", "total"])
async def test_private_byte_quotas_are_enforced(
    client: AsyncClient, app: FastAPI, scope: str
) -> None:
    app.state.settings = app.state.settings.model_copy(update={f"{scope}_storage_bytes": 200})
    auth = await headers(client)
    data = await item(client, auth, await draft(client, auth))
    first = await upload(client, auth, data)
    assert first.status_code == 201
    next_row = first.json()["request"] if scope == "request" else await draft(client, auth)
    second = await item(client, auth, next_row)
    blocked = await upload(client, auth, second)
    assert blocked.status_code == 429 and blocked.json()["code"] == "storage_quota_exceeded"


async def test_global_quota_counts_concurrent_inflight_reservations(
    client: AsyncClient, app: FastAPI
) -> None:
    import asyncio

    from httpx import ASGITransport

    from tests.signing import ORIGIN

    app.state.settings = app.state.settings.model_copy(
        update={"total_storage_bytes": len(BINARY_STL)}
    )
    auth = await headers(client)
    first = await item(client, auth, await draft(client, auth))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=ORIGIN, headers={"Origin": ORIGIN}
    ) as other:
        other_auth = await headers(other, CUSTOMER_ID + 1)
        second = await item(other, other_auth, await draft(other, other_auth))
        responses = await asyncio.gather(
            upload(client, auth, first), upload(other, other_auth, second)
        )
    assert sorted(response.status_code for response in responses) == [201, 429]
    async with app.state.session_factory() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(UploadedFile)
                .where(UploadedFile.storage_state == "ready")
            )
            == 1
        )


async def test_intake_and_upload_rates_are_server_side(client: AsyncClient, app: FastAPI) -> None:
    app.state.settings = app.state.settings.model_copy(update={"upload_rate_limit": 1})
    auth = await headers(client)
    details = await item(client, auth, await draft(client, auth))
    assert (await upload(client, auth, details, b"bad", "bad.stl")).status_code == 415
    assert (await upload(client, auth, details)).status_code == 429


@pytest.mark.parametrize("phase", ["stage", "promote", "outbox"])
async def test_storage_and_database_failures_preserve_saved_draft(
    client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    from sqlalchemy import event
    from sqlalchemy.exc import SQLAlchemyError

    auth = await headers(client)
    before = await item(client, auth, await draft(client, auth))

    async def fail_io(*_args):
        raise OSError("Synthetic private storage failure")

    original_stage, original_promote = app.state.storage.stage, app.state.storage.promote

    def fail_outbox(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO notification_outbox"):
            raise SQLAlchemyError("Synthetic transaction failure")

    if phase == "outbox":
        event.listen(app.state.engine.sync_engine, "before_cursor_execute", fail_outbox)
    else:
        monkeypatch.setattr(app.state.storage, phase, fail_io)
    key = uuid4().hex
    try:
        failed = await upload(client, auth, before, key=key)
        assert failed.status_code == 503, failed.text
        assert "Synthetic" not in failed.text
    finally:
        if phase == "outbox":
            event.remove(app.state.engine.sync_engine, "before_cursor_execute", fail_outbox)
        else:
            monkeypatch.setattr(app.state.storage, "stage", original_stage)
            monkeypatch.setattr(app.state.storage, "promote", original_promote)
    saved = (await client.get(f"/api/v1/requests/{before['request']['id']}/intake")).json()
    assert saved["request"] == before["request"] and saved["items"][0]["model_file"] is None
    assert not list((app.state.storage.root / "ready").iterdir())
    retried = await upload(client, auth, before, key=key)
    assert retried.status_code == 201, retried.text


async def test_ambiguous_commit_never_unlinks_successful_upload(
    client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy.exc import SQLAlchemyError

    from app.services import uploads

    auth = await headers(client)
    data = await item(client, auth, await draft(client, auth))
    key = uuid4().hex
    execute = uploads.execute_command

    async def commit_then_fail(*args, **kwargs):
        await execute(*args, **kwargs)
        raise SQLAlchemyError("Synthetic lost commit acknowledgement")

    monkeypatch.setattr(uploads, "execute_command", commit_then_fail)
    response = await upload(client, auth, data, key=key)
    assert response.status_code == 503
    monkeypatch.setattr(uploads, "execute_command", execute)
    retried = await upload(client, auth, data, key=key)
    assert retried.status_code == 201, retried.text
    model = retried.json()["items"][0]["model_file"]
    assert (await client.get(f"/api/v1/files/{model['id']}/download")).content == BINARY_STL
    async with app.state.session_factory() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "request.file_attached")
            )
            == 1
        )


async def test_pending_delete_stays_charged_until_recovery(
    client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.uploads import cleanup_uploads

    app.state.settings = app.state.settings.model_copy(update={"total_storage_bytes": 200})
    auth = await headers(client)
    details = await item(client, auth, await draft(client, auth))
    first = await upload(client, auth, details)
    assert first.status_code == 201
    data = first.json()
    row = data["request"]
    item_id = data["items"][0]["id"]
    original = app.state.storage.delete

    async def fail_delete(*_args):
        raise OSError("Synthetic unlink failure")

    monkeypatch.setattr(app.state.storage, "delete", fail_delete)
    removed = await client.request(
        "DELETE",
        f"/api/v1/requests/{row['id']}/items/{item_id}",
        headers=command(auth),
        json={"expected_version": row["version"]},
    )
    assert removed.status_code == 200
    assert len(list((app.state.storage.root / "ready").iterdir())) == 1
    next_item = await item(client, auth, removed.json()["request"])
    assert (await upload(client, auth, next_item)).status_code == 429
    monkeypatch.setattr(app.state.storage, "delete", original)
    assert await cleanup_uploads(app.state.session_factory, app.state.storage) == 1
    assert not list((app.state.storage.root / "ready").iterdir())
    assert (await upload(client, auth, next_item)).status_code == 201


async def test_session_expiry_during_upload_cannot_attach_file(
    client: AsyncClient, app: FastAPI
) -> None:
    import asyncio
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from app.database.models import Session

    auth = await headers(client)
    data = await item(client, auth, await draft(client, auth))
    row = data["request"]
    started, resume = asyncio.Event(), asyncio.Event()

    async def content():
        yield BINARY_STL[:60]
        started.set()
        await resume.wait()
        yield BINARY_STL[60:]

    task = asyncio.create_task(
        client.post(
            f"/api/v1/requests/{row['id']}/files?item_id={data['items'][0]['id']}&expected_version={row['version']}",
            content=content(),
            headers={
                **command(auth),
                "Content-Type": "application/octet-stream",
                "X-File-Name": "test.stl",
                "X-File-Size": str(len(BINARY_STL)),
                "X-Content-SHA256": hashlib.sha256(BINARY_STL).hexdigest(),
            },
        )
    )
    await asyncio.wait_for(started.wait(), 5)
    async with app.state.session_factory() as db, db.begin():
        await db.execute(
            update(Session).values(
                created_at=datetime.now(UTC) - timedelta(hours=1),
                expires_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
    resume.set()
    response = await asyncio.wait_for(task, 10)
    assert response.status_code == 401, response.text
    async with app.state.session_factory() as db:
        saved = await db.get(ServiceRequest, UUID(row["id"]))
        assert saved and saved.version == row["version"]
        assert (
            await db.scalar(
                select(func.count())
                .select_from(UploadedFile)
                .where(UploadedFile.storage_state != "deleted")
            )
            == 0
        )
    assert not list((app.state.storage.root / "ready").iterdir())


async def test_missing_or_tampered_blob_cannot_submit_or_download(
    client: AsyncClient, app: FastAPI
) -> None:
    auth = await headers(client)
    data = await item(client, auth, await draft(client, auth))
    response = await upload(client, auth, data)
    assert response.status_code == 201
    data = response.json()
    row = data["request"]
    model = data["items"][0]["model_file"]
    async with app.state.session_factory() as db:
        file = await db.get(UploadedFile, UUID(model["id"]))
        assert file
        path = app.state.storage.path("ready", file.storage_key)
    path.write_bytes(b"tampered bytes")
    assert (await client.get(f"/api/v1/files/{model['id']}/download")).status_code == 404
    failed = await client.post(
        f"/api/v1/requests/{row['id']}/submit",
        headers=command(auth),
        json={"expected_version": row["version"]},
    )
    assert failed.status_code == 422
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(ProcessingTask)) == 0


async def test_submitted_revision_and_items_are_immutable_in_database(
    client: AsyncClient, app: FastAPI
) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    auth = await headers(client)
    data = await item(client, auth, await draft(client, auth))
    response = await upload(client, auth, data)
    assert response.status_code == 201
    row = response.json()["request"]
    result = await client.post(
        f"/api/v1/requests/{row['id']}/submit",
        headers=command(auth),
        json={"expected_version": row["version"]},
    )
    assert result.status_code == 200
    for statement in [
        "UPDATE service_requests SET customer_notes='Changed'",
        "UPDATE service_requests SET submitted_spec='{}'::jsonb",
        "UPDATE request_items SET quantity=8",
        "UPDATE uploaded_files SET sha256=repeat('a',64)",
        "UPDATE processing_tasks SET state='succeeded'",
    ]:
        with pytest.raises(IntegrityError):
            async with app.state.engine.begin() as connection:
                await connection.execute(text(statement))
    assert (
        await client.patch(
            f"/api/v1/requests/{row['id']}",
            headers=command(auth),
            json={
                "expected_version": result.json()["request"]["version"],
                "customer_notes": "Edit frozen data",
            },
        )
    ).status_code == 409


async def test_session_expiry_during_submission_rolls_back_tasks(
    client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from app.database.models import Session

    auth = await headers(client)
    data = await item(client, auth, await draft(client, auth))
    response = await upload(client, auth, data)
    assert response.status_code == 201
    row = response.json()["request"]
    async with app.state.session_factory() as db, db.begin():
        await db.execute(
            update(Session).values(expires_at=datetime.now(UTC) + timedelta(seconds=1))
        )
    verify = app.state.storage.verify

    async def delayed(*args):
        await verify(*args)
        await asyncio.sleep(1.1)

    monkeypatch.setattr(app.state.storage, "verify", delayed)
    response = await client.post(
        f"/api/v1/requests/{row['id']}/submit",
        headers=command(auth),
        json={"expected_version": row["version"]},
    )
    assert response.status_code == 401, response.text
    async with app.state.session_factory() as db:
        saved = await db.get(ServiceRequest, UUID(row["id"]))
        assert saved and saved.status == "draft" and saved.version == row["version"]
        assert await db.scalar(select(func.count()).select_from(ProcessingTask)) == 0


async def test_cleanup_recovers_crash_after_promotion_before_database_commit(
    client: AsyncClient, app: FastAPI
) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from app.services.auth import resolve_session
    from app.services.uploads import cleanup_uploads, reserve_upload

    auth = await headers(client)
    data = await item(client, auth, await draft(client, auth))
    row = data["request"]
    principal = await resolve_session(
        app.state.session_factory, app.state.settings, client.cookies.get("__Host-3dps_session")
    )
    checksum = hashlib.sha256(BINARY_STL).hexdigest()
    reservation = await reserve_upload(
        app.state.session_factory,
        app.state.settings,
        principal,
        UUID(row["id"]),
        UUID(data["items"][0]["id"]),
        row["version"],
        uuid4().hex,
        "crash.stl",
        len(BINARY_STL),
        checksum,
    )

    async def chunks():
        yield BINARY_STL

    await app.state.storage.stage(reservation.storage_key, chunks(), len(BINARY_STL), checksum)
    await app.state.storage.promote(reservation.storage_key)
    # Simulate process loss before attaching the file. The committed quota row
    # still names the otherwise orphaned ready-path blob.
    async with app.state.session_factory() as db, db.begin():
        await db.execute(
            update(UploadedFile)
            .where(UploadedFile.id == reservation.id)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert await cleanup_uploads(app.state.session_factory, app.state.storage) == 1
    assert not list((app.state.storage.root / "ready").iterdir())
    saved = (await client.get(f"/api/v1/requests/{row['id']}/intake")).json()
    assert saved["request"] == row and saved["items"][0]["model_file"] is None


async def test_database_rejects_cross_item_models_and_duplicate_tasks(
    client: AsyncClient, app: FastAPI
) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    auth = await headers(client)
    data = await item(client, auth, await draft(client, auth))
    first = await upload(client, auth, data)
    assert first.status_code == 201
    data = await item(client, auth, first.json()["request"])
    other_id = data["items"][-1]["id"]
    first_file = data["items"][0]["model_file"]["id"]
    with pytest.raises(IntegrityError):
        async with app.state.engine.begin() as db:
            await db.execute(
                text("UPDATE request_items SET model_file_id=:file WHERE id=:item"),
                {"file": first_file, "item": other_id},
            )
    with pytest.raises(IntegrityError):
        async with app.state.engine.begin() as db:
            await db.execute(text("UPDATE request_items SET stage_kind='design'"))
    second = await upload(client, auth, data, OBJ, "second.obj")
    assert second.status_code == 201
    row = second.json()["request"]
    submitted = await client.post(
        f"/api/v1/requests/{row['id']}/submit",
        headers=command(auth),
        json={"expected_version": row["version"]},
    )
    assert submitted.status_code == 200
    with pytest.raises(IntegrityError):
        async with app.state.engine.begin() as db:
            await db.execute(
                text(
                    "INSERT INTO processing_tasks (request_id,uploaded_file_id,customer_id,request_revision,spec_sha256) SELECT request_id,uploaded_file_id,customer_id,request_revision,spec_sha256 FROM processing_tasks LIMIT 1"
                )
            )


async def test_older_pending_analysis_is_superseded_on_new_draft_revision(
    client: AsyncClient, app: FastAPI
) -> None:
    auth = await headers(client)
    data = await item(client, auth, await draft(client, auth))
    uploaded = await upload(client, auth, data)
    assert uploaded.status_code == 201
    data = uploaded.json()
    row = data["request"]
    file = data["items"][0]["model_file"]
    async with app.state.session_factory() as db, db.begin():
        db.add(
            ProcessingTask(
                request_id=UUID(row["id"]),
                uploaded_file_id=UUID(file["id"]),
                customer_id=UUID(row["customer_id"]),
                request_revision=row["revision"],
                spec_sha256=row["canonical_spec_sha256"],
                state="pending",
            )
        )
    changed = await client.patch(
        f"/api/v1/requests/{row['id']}",
        headers=command(auth),
        json={"expected_version": row["version"], "customer_notes": "A meaningful new revision"},
    )
    assert changed.status_code == 200
    async with app.state.session_factory() as db:
        task = await db.scalar(select(ProcessingTask))
        assert task and task.state == "superseded" and task.request_revision == row["revision"]


async def test_owner_queue_filters_and_design_stage_are_separate(client: AsyncClient) -> None:
    auth = await headers(client)
    data = await item(client, auth, await draft(client, auth))
    uploaded = await upload(client, auth, data)
    assert uploaded.status_code == 201
    row = uploaded.json()["request"]
    assert (
        await client.post(
            f"/api/v1/requests/{row['id']}/submit",
            headers=command(auth),
            json={"expected_version": row["version"]},
        )
    ).status_code == 200
    design = await client.post(
        "/api/v1/requests", headers=command(auth), json={"service_type": "design_and_print"}
    )
    design_row = design.json()["request"]
    blocked = await client.post(
        f"/api/v1/requests/{design_row['id']}/items",
        headers=command(auth),
        json={"expected_version": 1},
    )
    assert blocked.status_code == 409
    await headers(client, OWNER_ID)
    listed = await client.get("/api/v1/owner/requests?status=submitted&stage_kind=printing")
    assert listed.status_code == 200 and [item["id"] for item in listed.json()["items"]] == [
        row["id"]
    ]
