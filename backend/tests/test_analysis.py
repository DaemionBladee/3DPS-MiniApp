"""M06 SQL/API security and real Docker/PrusaSlicer integration (explicit opt-in image)."""

import asyncio
import json
import os
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.analysis.orchestrator import process_one
from app.analysis.registry import seed_profiles
from app.analysis.sandbox import DockerSandbox, SandboxFailure, command, container_arguments
from app.analysis.tasks import LeaseLost, claim, failed, publish, recover, started
from app.database.analysis_models import ModelAnalysis, SlicingRun
from app.database.business_models import AuditLog, NotificationOutbox, ServiceRequest
from app.database.intake_models import ProcessingTask
from tests.analysis_fixtures import FACES, cube
from tests.model_fixtures import COMPLETE_SPEC
from tests.signing import CUSTOMER_ID, ORIGIN, OWNER_ID
from tests.test_business_foundation import headers
from tests.test_printing_intake import command as cmd
from tests.test_printing_intake import draft, item, upload


@pytest.fixture
async def registry(app):
    image = os.environ.get("M06_TEST_WORKER_IMAGE", "")
    if image:
        assert image.startswith("sha256:"), "Tests require immutable image ID"
        probe = json.loads(
            await command("run", "--rm", *container_arguments(image), "--probe=base")
        )
        executable = probe["executable_sha256"]
    else:
        image, executable = "sha256:" + "a" * 64, "b" * 64
    async with app.state.session_factory() as db, db.begin():
        await seed_profiles(db, image, executable, 1)
        await db.execute(text("UPDATE slicer_profiles SET active=true"))
    return image


@pytest.fixture
async def sandbox(registry, tmp_path):
    if not os.environ.get("M06_TEST_WORKER_IMAGE"):
        pytest.skip(
            "Real sandbox requires explicitly built M06_TEST_WORKER_IMAGE; never substitute a mock"
        )
    return DockerSandbox(tmp_path / "jobs")


async def submitted(client, auth, kind="stl", spec=None, data=None):
    details = await item(client, auth, await draft(client, auth), spec)
    response = await upload(
        client, auth, details, cube(kind) if data is None else data, "cube." + kind
    )
    assert response.status_code == 201, response.text
    row = response.json()["request"]
    response = await client.post(
        f"/api/v1/requests/{row['id']}/submit",
        headers=cmd(auth),
        json={"expected_version": row["version"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def counts(app):
    async with app.state.session_factory() as db:
        return [
            await db.scalar(select(func.count()).select_from(model))
            for model in (ModelAnalysis, SlicingRun, AuditLog, NotificationOutbox)
        ]


@pytest.mark.parametrize("kind", ["stl", "3mf", "obj"])
async def test_actual_isolated_analysis_full_api_privacy_and_provenance(client, app, sandbox, kind):
    auth = await headers(client)
    data = await submitted(client, auth, kind)
    rid = data["request"]["id"]
    before = (await client.get(f"/api/v1/requests/{rid}/analysis")).json()
    assert before["state"] == "pending" and not before["processing_available"]
    assert await process_one(
        app.state.session_factory, app.state.storage, sandbox, "test-real-worker"
    )
    status = (await client.get(f"/api/v1/requests/{rid}/analysis")).json()
    assert status["state"] == "completed" and status["tasks"][0]["attempts"] == 1
    response = await client.get(f"/api/v1/requests/{rid}/analysis/results")
    result = response.json()["items"][0]
    assert result["outcome"] == "estimated" and result["simulation_only"]
    assert result["geometry"]["dimensions_mm"] == dict(x=20, y=20, z=20)
    assert result["geometry"]["volume_mm3"] == pytest.approx(8000)
    assert result["geometry"]["watertight"] and result["estimate"]["filament_g"] > 0
    assert result["estimate"]["print_seconds"] > 0 and result["estimate"]["support_g"] is None
    assert result["input_sha256"] == data["items"][0]["model_file"]["sha256"]
    assert result["spec_sha256"] == data["request"]["canonical_spec_sha256"]
    assert result["profile_snapshot"]["config_sha256"] == result["profile"]["config_sha256"]
    assert result["notice"] == "Simulation estimate — not a final quotation."
    assert result["quantity"] == 2 and not result["profile"]["calibrated"]
    assert "lease_token" not in response.text and "storage_key" not in response.text
    iid = data["items"][0]["id"]
    assert (await client.get(f"/api/v1/requests/{rid}/items/{iid}/analysis")).json()["items"][0][
        "id"
    ] == result["id"]
    async with app.state.session_factory() as db:
        assert (await db.get(ServiceRequest, UUID(rid))).status == "manual_review"
        audit = await db.scalar(select(AuditLog).where(AuditLog.action == "analysis.completed"))
        assert audit.actor_user_id is None and audit.actor_kind == "system"
        assert audit.metadata_snapshot["profile_id"] == result["profile"]["id"]
        assert audit.metadata_snapshot["result_id"] == result["id"]
        assert (
            await db.scalar(
                select(func.count())
                .select_from(NotificationOutbox)
                .where(NotificationOutbox.audit_log_id == audit.id)
            )
            == 1
        )
        assert await db.scalar(text("SELECT to_regclass('public.printers')")) is None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=ORIGIN, headers={"Origin": ORIGIN}
    ) as other:
        await headers(other, CUSTOMER_ID + 10)
        for path in [
            f"/requests/{rid}/analysis",
            f"/requests/{rid}/analysis/results",
            f"/requests/{rid}/items/{iid}/analysis",
        ]:
            assert (await other.get("/api/v1" + path)).status_code == 404
        assert (await other.get("/api/v1/owner/processing-tasks")).status_code == 403
        owner_auth = await headers(other, OWNER_ID)
        queue = (await other.get("/api/v1/owner/processing-tasks")).json()
        assert queue["items"][0]["state"] == "succeeded"
        assert (await other.get(f"/api/v1/requests/{rid}/analysis/results")).status_code == 200
        # Security controls apply to cached and new retries alike.
        body = {
            "expected_version": (await other.get(f"/api/v1/requests/{rid}")).json()["version"],
            "reason": "Review simulation again",
        }
        path = f"/api/v1/owner/processing-tasks/{data['tasks'][0]['id']}/retry"
        assert (
            await other.post(path, json=body, headers={"Idempotency-Key": uuid4().hex})
        ).status_code == 403
        assert (
            await other.post(
                path, json=body, headers=cmd(owner_auth) | {"Origin": "https://evil.test"}
            )
        ).status_code == 403


async def test_concurrent_claims_global_bound_and_no_premature_analyzing(client, app, registry):
    auth = await headers(client)
    rows = [await submitted(client, auth) for _ in range(3)]
    jobs = await asyncio.gather(
        *(claim(app.state.session_factory, f"worker-{i}") for i in range(6))
    )
    claimed = [j for j in jobs if j]
    assert len(claimed) == 2 and len({j.task_id for j in claimed}) == 2
    for r in rows:
        assert (await client.get("/api/v1/requests/" + r["request"]["id"])).json()[
            "status"
        ] == "submitted"
    async with app.state.session_factory() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ProcessingTask)
                .where(ProcessingTask.state == "leased")
            )
            == 2
        )


async def test_expired_lease_recovery_fencing_and_bounded_retries(client, app, registry):
    auth = await headers(client)
    await submitted(client, auth)
    first = await claim(app.state.session_factory, "worker-1")
    await started(app.state.session_factory, first)
    async with app.state.session_factory() as db, db.begin():
        await db.execute(
            text("UPDATE processing_tasks SET lease_expires_at=now()-interval '1 second'")
        )
    with pytest.raises(LeaseLost):
        await started(app.state.session_factory, first)
    assert await recover(app.state.session_factory) == 1
    assert await recover(app.state.session_factory) == 0
    for _attempt in range(2, 4):
        async with app.state.session_factory() as db, db.begin():
            await db.execute(text("UPDATE processing_tasks SET next_available_at=now()"))
        job = await claim(app.state.session_factory, "worker-new")
        assert job.lease_token != first.lease_token
        with pytest.raises(LeaseLost):
            await failed(app.state.session_factory, first, "worker_timeout")
        await failed(app.state.session_factory, job, "worker_crashed")
    async with app.state.session_factory() as db:
        task = await db.get(ProcessingTask, first.task_id)
        assert task.state == "failed" and task.attempts == 3 and task.error_code == "worker_crashed"
        audit = await db.scalar(select(AuditLog).where(AuditLog.action == "analysis.failed"))
        assert audit.metadata_snapshot["profile_id"] == str(task.selected_profile_id)
    assert await claim(app.state.session_factory, "worker-last") is None


async def test_duplicate_delivery_and_stale_output_cannot_publish(client, app, sandbox):
    auth = await headers(client)
    await submitted(client, auth)
    job = await claim(app.state.session_factory, "worker")
    output = await sandbox.execute(
        job, app.state.storage, lambda: started(app.state.session_factory, job)
    )
    bad = json.loads(output)
    bad["input_sha256"] = "f" * 64
    before = await counts(app)
    with pytest.raises(ValueError):
        await publish(app.state.session_factory, job, json.dumps(bad).encode())
    assert await counts(app) == before
    run = await publish(app.state.session_factory, job, output)
    after = await counts(app)
    with pytest.raises(LeaseLost):
        await publish(app.state.session_factory, job, output)
    assert await counts(app) == after
    async with app.state.session_factory() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(SlicingRun).where(SlicingRun.id == run)
            )
            == 1
        )
    for statement in [
        "UPDATE model_analyses SET analyzer_version='forged'",
        "UPDATE slicing_runs SET estimate='{}'::jsonb",
        "UPDATE slicer_profiles SET configuration='{}'::jsonb",
        "UPDATE virtual_printer_models SET calibrated=true",
    ]:
        with pytest.raises(IntegrityError):
            async with app.state.engine.begin() as db:
                await db.execute(text(statement))
    # Superseded pointers are historical, never authoritative.
    async with app.state.session_factory() as db, db.begin():
        task = await db.get(ProcessingTask, job.task_id)
        task.state = "superseded"
    assert (await client.get(f"/api/v1/requests/{job.request_id}/analysis/results")).json()[
        "items"
    ] == []


async def test_database_publication_failure_rolls_back_results_audit_and_outbox(
    client, app, sandbox
):
    auth = await headers(client)
    await submitted(client, auth)
    job = await claim(app.state.session_factory, "worker")
    output = await sandbox.execute(
        job, app.state.storage, lambda: started(app.state.session_factory, job)
    )
    before = await counts(app)

    def reject(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO notification_outbox"):
            raise SQLAlchemyError("Synthetic publication failure")

    event.listen(app.state.engine.sync_engine, "before_cursor_execute", reject)
    try:
        with pytest.raises(SQLAlchemyError):
            await publish(app.state.session_factory, job, output)
    finally:
        event.remove(app.state.engine.sync_engine, "before_cursor_execute", reject)
    assert await counts(app) == before
    await publish(app.state.session_factory, job, output)


@pytest.mark.parametrize(
    "spec,expected",
    [
        ({"dimension_x_mm": 10, "dimension_y_mm": 10, "dimension_z_mm": 10}, "needs_clarification"),
        ({"unit_key": "cm"}, "completed"),
        ({"unit_key": "m"}, "manual_review"),
    ],
)
async def test_scale_and_dimensions_fail_closed(client, app, sandbox, spec, expected):
    auth = await headers(client)
    data = await submitted(client, auth, spec=COMPLETE_SPEC | spec)
    await process_one(app.state.session_factory, app.state.storage, sandbox, "worker")
    status = (await client.get(f"/api/v1/requests/{data['request']['id']}/analysis")).json()
    assert status["state"] == expected
    result = (
        await client.get(f"/api/v1/requests/{data['request']['id']}/analysis/results")
    ).json()["items"][0]
    if expected != "completed":
        assert result["estimate"] is None


async def test_open_mesh_is_review_not_successful_slicing(client, app, sandbox):
    auth = await headers(client)
    data = await submitted(client, auth, data=cube(faces=FACES[:-1]))
    await process_one(app.state.session_factory, app.state.storage, sandbox, "worker")
    result = (
        await client.get(f"/api/v1/requests/{data['request']['id']}/analysis/results")
    ).json()["items"][0]
    assert result["outcome"] == "manual_review" and result["estimate"] is None
    assert "open_mesh" in result["geometry"]["review_reasons"]


async def test_unknown_material_has_no_fallback(client, app, registry):
    auth = await headers(client)
    data = await submitted(
        client, auth, spec=COMPLETE_SPEC | {"material_key": "not-sure", "color_key": "not-sure"}
    )
    assert await claim(app.state.session_factory, "worker") is None
    result = (await client.get(f"/api/v1/requests/{data['request']['id']}/analysis")).json()
    assert result["state"] == "failed" and result["tasks"][0]["error_code"] == "profile_unavailable"
    totals = await counts(app)
    assert totals[:2] == [0, 0] and totals[2] == totals[3]


async def test_owner_retry_is_idempotent_and_budgeted(client, app, sandbox):
    auth = await headers(client)
    data = await submitted(client, auth)
    await process_one(app.state.session_factory, app.state.storage, sandbox, "worker")
    rid = data["request"]["id"]
    tid = data["tasks"][0]["id"]
    owner_auth = await headers(client, OWNER_ID)
    row = (await client.get(f"/api/v1/requests/{rid}")).json()
    path = f"/api/v1/owner/processing-tasks/{tid}/retry"
    body = {"expected_version": row["version"], "reason": "Inspect a repeat simulation"}
    key = cmd(owner_auth)
    responses = await asyncio.gather(*(client.post(path, json=body, headers=key) for _ in range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    assert (await client.get(f"/api/v1/requests/{rid}/analysis/results")).json()["items"] == []
    async with app.state.session_factory() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "analysis.rescheduled")
            )
            == 1
        )
    # Current server authorization still guards an idempotency replay.
    await headers(client, CUSTOMER_ID)
    assert (await client.post(path, json=body, headers=key)).status_code in {401, 403}


async def test_real_worker_crash_timeout_and_partial_output_fail_closed(client, app, sandbox):
    auth = await headers(client)
    await submitted(client, auth)
    job = await claim(app.state.session_factory, "worker")
    with pytest.raises(ValueError):
        await publish(app.state.session_factory, job, b'{"estimate":{"filament_g":1}}')
    assert (await counts(app))[:2] == [0, 0]
    # A real wall timeout tears down the container, never falls back to host slicing.
    short = DockerSandbox(sandbox.staging_root, wall_seconds=0.001)
    with pytest.raises(SandboxFailure, match="worker_timeout"):
        await short.execute(job, app.state.storage, lambda: started(app.state.session_factory, job))
    assert list(sandbox.staging_root.iterdir()) == []


async def test_real_repeatability_and_profile_specific_results(client, app, sandbox):
    auth = await headers(client)
    values = []
    for quality in ["dev-standard", "dev-standard", "dev-fine"]:
        data = await submitted(client, auth, spec=COMPLETE_SPEC | {"quality_key": quality})
        await process_one(app.state.session_factory, app.state.storage, sandbox, "repeat-worker")
        response = (
            await client.get(f"/api/v1/requests/{data['request']['id']}/analysis/results")
        ).json()
        values.append(response["items"][0])
    a, b, fine = values
    assert a["estimate"]["filament_g"] == b["estimate"]["filament_g"]
    assert a["estimate"]["print_seconds"] == b["estimate"]["print_seconds"]
    assert a["estimate"]["canonical_gcode_sha256"] == b["estimate"]["canonical_gcode_sha256"]
    assert a["profile"]["config_sha256"] == b["profile"]["config_sha256"]
    assert fine["profile"]["id"] != a["profile"]["id"]
    assert fine["profile"]["config_sha256"] != a["profile"]["config_sha256"]
    assert fine["estimate"]["print_seconds"] > a["estimate"]["print_seconds"]


async def test_worker_revalidates_malicious_archives_in_real_sandbox(client, app, sandbox):
    import hashlib

    from tests.model_fixtures import MODEL_XML, RELS, TYPES, three_mf

    auth = await headers(client)
    await submitted(client, auth)
    job = await claim(app.state.session_factory, "worker")
    # Fault injection below bypasses intake deliberately: defense in depth must
    # still reject an archive reaching the worker via a compromised input store.
    data = three_mf(
        {
            "[Content_Types].xml": TYPES,
            "_rels/.rels": RELS,
            "3D/3dmodel.model": MODEL_XML,
            "Metadata/Slic3r_PE.config": b"post_process=evil",
        }
    )
    key = uuid4().hex

    async def chunks():
        yield data

    checksum = hashlib.sha256(data).hexdigest()
    await app.state.storage.stage(key, chunks(), len(data), checksum)
    await app.state.storage.promote(key)
    manifest = job.manifest | {"input_sha256": checksum, "input_format": "3mf"}
    malicious = replace(
        job, storage_key=key, size_bytes=len(data), sha256=checksum, format="3mf", manifest=manifest
    )
    output = await sandbox.execute(
        malicious, app.state.storage, lambda: started(app.state.session_factory, job)
    )
    result = json.loads(output)
    assert "error" in result and not result["retryable"]
    assert "estimate" not in result


async def test_owner_retry_budget_and_cached_authorization_are_current(client, app, sandbox):
    auth = await headers(client)
    data = await submitted(client, auth)
    await process_one(app.state.session_factory, app.state.storage, sandbox, "worker")
    auth = await headers(client, OWNER_ID)
    rid, tid = data["request"]["id"], data["tasks"][0]["id"]
    row = (await client.get(f"/api/v1/requests/{rid}")).json()
    path = f"/api/v1/owner/processing-tasks/{tid}/retry"
    payload = {"expected_version": row["version"], "reason": "Inspect bounded simulation retry"}
    key = cmd(auth)
    assert (await client.post(path, headers=key, json=payload)).status_code == 200
    app.state.settings.owner_telegram_ids = ""
    assert (await client.post(path, headers=key, json=payload)).status_code == 403
    app.state.settings.owner_telegram_ids = str(OWNER_ID)
    # Test the upper bound without spending six native processing runs.
    async with app.state.session_factory() as db, db.begin():
        await db.execute(
            text(
                "UPDATE processing_tasks SET attempts=6,max_attempts=6,state='failed',error_code='worker_crashed',completed_at=now() WHERE id=:id"
            ),
            {"id": UUID(tid)},
        )
    payload["expected_version"] = (await client.get(f"/api/v1/requests/{rid}")).json()["version"]
    assert (await client.post(path, headers=cmd(auth), json=payload)).status_code == 409


async def test_orphan_recovery_removes_only_old_task_owned_staging(sandbox):
    import os
    import time

    from app.analysis.sandbox import cleanup_orphans

    root = sandbox.staging_root
    root.mkdir(mode=0o700)
    old = root / f"job-{uuid4().hex}-{uuid4().hex}-orphan"
    current = root / f"job-{uuid4().hex}-{uuid4().hex}-current"
    unrelated = root / "unrelated-private-data"
    for directory in [old, current, unrelated]:
        directory.mkdir()
        (directory / "model.bin").write_bytes(b"synthetic private fixture")
    for directory in [old, unrelated]:
        os.utime(directory, (time.time() - 600, time.time() - 600))
    assert await cleanup_orphans(root) == 1
    assert not old.exists() and current.exists() and unrelated.exists()
    assert await cleanup_orphans(root) == 0


async def test_public_profile_configuration_preserves_its_checksum(client, registry):
    from app.analysis.profile_config import canonical_hash

    await headers(client)
    response = await client.get("/api/v1/catalog/simulation-profiles")
    assert response.status_code == 200
    assert len(response.json()) == 4
    for profile in response.json():
        assert canonical_hash(profile["configuration"]) == profile["config_sha256"]
        assert profile["simulation_only"] and not profile["calibrated"]
