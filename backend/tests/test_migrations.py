import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.signing import BOT_TOKEN, ORIGIN, SESSION_SECRET

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest_asyncio.fixture
async def migration_database(database_url: str) -> AsyncIterator[str]:
    """Create/drop only a uniquely named database this fixture itself owns."""
    parsed = make_url(database_url)
    admin_url = parsed.set(drivername="postgresql").render_as_string(hide_password=False)
    name = "3dps_test_migrations_" + uuid4().hex
    admin = await asyncpg.connect(admin_url)
    await admin.execute(f'CREATE DATABASE "{name}"')
    try:
        yield parsed.set(database=name).render_as_string(hide_password=False)
    finally:
        await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await admin.close()


def run_migration(url: str, direction: str, revision: str) -> None:
    environment = dict(os.environ)
    environment.update(
        DATABASE_URL=url,
        APP_ENV="test",
        BOT_TOKEN=BOT_TOKEN,
        SESSION_SECRET=SESSION_SECRET,
        PUBLIC_BASE_URL=ORIGIN,
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", direction, revision],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        check=True,
    )


@pytest.mark.asyncio
async def test_auth_migration_empty_upgrade_seed_preservation_and_disposable_recovery(
    migration_database: str,
) -> None:
    # Retain the M02 roundtrip against its immutable revision explicitly.
    run_migration(migration_database, "upgrade", "0001_auth_foundation")
    engine = create_async_engine(migration_database, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            tables = set(
                (
                    await connection.scalars(
                        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    )
                ).all()
            )
            assert tables == {"users", "sessions", "auth_rate_limits", "alembic_version"}
            user_id = await connection.scalar(
                text(
                    "INSERT INTO users (telegram_id, display_name) VALUES (123, 'Seeded test user') RETURNING id"
                )
            )
            assert isinstance(user_id, UUID)
            await connection.execute(
                text(
                    "INSERT INTO sessions (user_id, token_hash, init_data_hash, expires_at) "
                    "VALUES (:user_id, :token_hash, :proof_hash, now() + interval '1 hour')"
                ),
                {"user_id": user_id, "token_hash": "a" * 64, "proof_hash": "b" * 64},
            )
        await engine.dispose()
        run_migration(migration_database, "upgrade", "0001_auth_foundation")
        async with engine.begin() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM users")) == 1
            assert await connection.scalar(text("SELECT count(*) FROM sessions")) == 1
            assert await connection.scalar(text("SELECT role FROM users")) == "customer"
            assert await connection.scalar(text("SELECT count(*) FROM alembic_version")) == 1
        await engine.dispose()
        run_migration(migration_database, "downgrade", "base")
        async with engine.begin() as connection:
            tables_after = set(
                (
                    await connection.scalars(
                        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    )
                ).all()
            )
            assert tables_after == {"alembic_version"}
        await engine.dispose()
        run_migration(migration_database, "upgrade", "0001_auth_foundation")
        async with engine.begin() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM users")) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_rejects_duplicate_identity_invalid_roles_and_reused_proofs(
    migration_database: str,
) -> None:
    run_migration(migration_database, "upgrade", "head")
    engine = create_async_engine(migration_database, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            user_id = await connection.scalar(
                text(
                    "INSERT INTO users (telegram_id, display_name) VALUES (321, 'Test') RETURNING id"
                )
            )
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text("INSERT INTO users (telegram_id, display_name) VALUES (321, 'Duplicate')")
                )
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO users (telegram_id, display_name, role) VALUES (322, 'Bad role', 'operator')"
                    )
                )
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO sessions (user_id, token_hash, init_data_hash, expires_at) "
                    "VALUES (:user_id, :token_hash, :proof_hash, now() + interval '1 hour')"
                ),
                {"user_id": user_id, "token_hash": "a" * 64, "proof_hash": "b" * 64},
            )
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO sessions (user_id, token_hash, init_data_hash, expires_at) "
                        "VALUES (:user_id, :token_hash, :proof_hash, now() + interval '1 hour')"
                    ),
                    {"user_id": user_id, "token_hash": "c" * 64, "proof_hash": "b" * 64},
                )
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM users WHERE id=:user_id"), {"user_id": user_id}
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_business_upgrade_preserves_m02_auth_and_disposable_downgrade(
    migration_database: str,
) -> None:
    run_migration(migration_database, "upgrade", "0001_auth_foundation")
    engine = create_async_engine(migration_database, hide_parameters=True)
    try:
        async with engine.begin() as db:
            user_id = await db.scalar(
                text(
                    "INSERT INTO users (telegram_id, display_name) VALUES (4321, 'M02 seed') RETURNING id"
                )
            )
            await db.execute(
                text(
                    "INSERT INTO sessions (user_id, token_hash, init_data_hash, expires_at) VALUES (:user, :token, :proof, now()+interval '1 hour')"
                ),
                {"user": user_id, "token": "d" * 64, "proof": "e" * 64},
            )
        await engine.dispose()
        run_migration(migration_database, "upgrade", "0002_business_foundation")
        async with engine.begin() as db:
            assert (
                await db.scalar(text("SELECT version_num FROM alembic_version"))
                == "0002_business_foundation"
            )
            assert await db.scalar(text("SELECT id FROM users")) == user_id
            assert await db.scalar(text("SELECT token_hash FROM sessions")) == "d" * 64
            tables = set(
                (
                    await db.scalars(
                        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    )
                ).all()
            )
            assert tables == {
                "alembic_version",
                "users",
                "sessions",
                "auth_rate_limits",
                "service_projects",
                "service_requests",
                "audit_logs",
                "notification_outbox",
                "idempotency_records",
            }
            assert (
                await db.scalar(
                    text("SELECT count(*) FROM pg_trigger WHERE tgname='audit_logs_immutable'")
                )
                == 1
            )
        await engine.dispose()
        # This fixture owns an empty business schema. Never run destructive
        # downgrade against deployed data or retained audit events.
        run_migration(migration_database, "downgrade", "0001_auth_foundation")
        async with engine.begin() as db:
            assert await db.scalar(text("SELECT id FROM users")) == user_id
            assert await db.scalar(text("SELECT count(*) FROM sessions")) == 1
            assert await db.scalar(text("SELECT to_regclass('public.service_requests')")) is None
            assert (
                await db.scalar(text("SELECT to_regprocedure('reject_audit_mutation()')")) is None
            )
        await engine.dispose()
        run_migration(migration_database, "upgrade", "0002_business_foundation")
        async with engine.begin() as db:
            assert await db.scalar(text("SELECT count(*) FROM users")) == 1
            assert await db.scalar(text("SELECT count(*) FROM service_requests")) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_intake_upgrade_preserves_seeded_m03_history_and_guards_recovery(
    migration_database: str,
) -> None:
    run_migration(migration_database, "upgrade", "0002_business_foundation")
    engine = create_async_engine(migration_database, hide_parameters=True)
    try:
        async with engine.begin() as db:
            user = await db.scalar(
                text(
                    "INSERT INTO users (telegram_id,display_name) VALUES (424242,'Seeded M03 customer') RETURNING id"
                )
            )
            project = await db.scalar(
                text(
                    "INSERT INTO service_projects (customer_id,kind) VALUES (:user,'printing') RETURNING id"
                ),
                {"user": user},
            )
            request = await db.scalar(
                text(
                    "INSERT INTO service_requests (service_project_id,customer_id,service_type,stage_kind,canonical_spec_sha256,customer_notes) VALUES (:project,:user,'printing','printing',:sha,'preserved note') RETURNING id"
                ),
                {"project": project, "user": user, "sha": "a" * 64},
            )
            audit = await db.scalar(
                text(
                    "INSERT INTO audit_logs (actor_user_id,action,entity_id,metadata_snapshot) VALUES (:user,'request.created',:request,'{\"legacy\": true}'::jsonb) RETURNING id"
                ),
                {"user": user, "request": request},
            )
            await db.execute(
                text(
                    "INSERT INTO notification_outbox (audit_log_id,recipient_user_id,event_type,payload_minimized) VALUES (:audit,:user,'request.created','{}'::jsonb)"
                ),
                {"audit": audit, "user": user},
            )
            await db.execute(
                text(
                    "INSERT INTO idempotency_records (actor_user_id,action,key,request_hash,response_json) VALUES (:user,'request.create','legacy-test-key',:sha,'{\"preserved\": true}'::jsonb)"
                ),
                {"user": user, "sha": "b" * 64},
            )
            await db.execute(
                text(
                    "INSERT INTO sessions (user_id,token_hash,init_data_hash,expires_at) VALUES (:user,:token,:proof,now()+interval '1 hour')"
                ),
                {"user": user, "token": "c" * 64, "proof": "d" * 64},
            )
        await engine.dispose()
        run_migration(migration_database, "upgrade", "0003_printing_intake")
        async with engine.begin() as db:
            assert (
                await db.scalar(text("SELECT version_num FROM alembic_version"))
                == "0003_printing_intake"
            )
            assert (
                await db.scalar(text("SELECT canonical_spec_sha256 FROM service_requests"))
                == "a" * 64
            )
            assert (
                await db.scalar(text("SELECT customer_notes FROM service_requests"))
                == "preserved note"
            )
            assert await db.scalar(text("SELECT spec_schema_version FROM service_requests")) == 1
            assert await db.scalar(text("SELECT token_hash FROM sessions")) == "c" * 64
            assert (
                await db.scalar(text("SELECT response_json->>'preserved' FROM idempotency_records"))
                == "true"
            )
            for table in [
                "users",
                "sessions",
                "service_projects",
                "service_requests",
                "audit_logs",
                "notification_outbox",
                "idempotency_records",
            ]:
                assert await db.scalar(text(f"SELECT count(*) FROM {table}")) == 1
            assert (
                await db.scalar(
                    text("SELECT count(*) FROM pg_constraint WHERE conname='fk_item_current_model'")
                )
                == 1
            )
            assert (
                await db.scalar(text("SELECT count(*) FROM pg_tables WHERE schemaname='public'"))
                == 12
            )
        await engine.dispose()
        run_migration(migration_database, "downgrade", "0002_business_foundation")
        async with engine.begin() as db:
            assert await db.scalar(text("SELECT to_regclass('public.request_items')")) is None
            assert await db.scalar(text("SELECT count(*) FROM audit_logs")) == 1
            assert await db.scalar(text("SELECT count(*) FROM idempotency_records")) == 1
        await engine.dispose()
        run_migration(migration_database, "upgrade", "0003_printing_intake")
        async with engine.begin() as db:
            await db.execute(
                text(
                    "INSERT INTO request_items (request_id,customer_id,request_revision) VALUES (:request,:user,1)"
                ),
                {"request": request, "user": user},
            )
        await engine.dispose()
        with pytest.raises(subprocess.CalledProcessError):
            run_migration(migration_database, "downgrade", "0002_business_foundation")
        async with engine.begin() as db:
            assert await db.scalar(text("SELECT count(*) FROM request_items")) == 1
            assert (
                await db.scalar(text("SELECT version_num FROM alembic_version"))
                == "0003_printing_intake"
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_design_upgrade_preserves_m04_models_and_recovery_refuses_design_data(
    migration_database: str,
) -> None:
    run_migration(migration_database, "upgrade", "0003_printing_intake")
    engine = create_async_engine(migration_database, hide_parameters=True)
    try:
        async with engine.begin() as db:
            user = await db.scalar(
                text(
                    "INSERT INTO users(telegram_id,display_name) VALUES(50505,'M04 seed') RETURNING id"
                )
            )
            project = await db.scalar(
                text(
                    "INSERT INTO service_projects(customer_id,kind) VALUES(:user,'printing') RETURNING id"
                ),
                {"user": user},
            )
            request = await db.scalar(
                text(
                    "INSERT INTO service_requests(service_project_id,customer_id,service_type,stage_kind,canonical_spec_sha256) VALUES(:project,:user,'printing','printing',:sha) RETURNING id"
                ),
                {"project": project, "user": user, "sha": "a" * 64},
            )
            item = await db.scalar(
                text(
                    "INSERT INTO request_items(request_id,customer_id,request_revision) VALUES(:request,:user,1) RETURNING id"
                ),
                {"request": request, "user": user},
            )
            file = await db.scalar(
                text(
                    "INSERT INTO uploaded_files(request_id,request_item_id,owner_id,request_revision,expected_version,upload_key,fingerprint,storage_key,lease_token,lease_expires_at,reserved_bytes,expected_sha256,original_name) VALUES(:request,:item,:user,1,1,'m04-preserved-key',:sha,:key,gen_random_uuid(),now()+interval '1 hour',100,:sha,'seed.stl') RETURNING id"
                ),
                {"request": request, "item": item, "user": user, "sha": "b" * 64, "key": "c" * 32},
            )
            await db.execute(
                text(
                    "INSERT INTO sessions(user_id,token_hash,init_data_hash,expires_at) VALUES(:user,:token,:proof,now()+interval '1 hour')"
                ),
                {"user": user, "token": "d" * 64, "proof": "e" * 64},
            )
        await engine.dispose()
        run_migration(migration_database, "upgrade", "0004_design_intake")
        async with engine.begin() as db:
            assert (
                await db.scalar(text("SELECT version_num FROM alembic_version"))
                == "0004_design_intake"
            )
            assert (
                await db.scalar(
                    text("SELECT purpose FROM uploaded_files WHERE id=:id"), {"id": file}
                )
                == "model"
            )
            assert (
                await db.scalar(
                    text("SELECT request_item_id FROM uploaded_files WHERE id=:id"), {"id": file}
                )
                == item
            )
            assert (
                await db.scalar(
                    text("SELECT storage_key FROM uploaded_files WHERE id=:id"), {"id": file}
                )
                == "c" * 32
            )
            assert await db.scalar(text("SELECT token_hash FROM sessions")) == "d" * 64
            assert await db.scalar(text("SELECT count(*) FROM design_projects")) == 0
            assert (
                await db.scalar(text("SELECT canonical_spec_sha256 FROM service_requests"))
                == "a" * 64
            )
        await engine.dispose()
        run_migration(migration_database, "downgrade", "0003_printing_intake")
        async with engine.begin() as db:
            assert await db.scalar(text("SELECT id FROM uploaded_files")) == file
            assert await db.scalar(text("SELECT count(*) FROM request_items")) == 1
        await engine.dispose()
        run_migration(migration_database, "upgrade", "0004_design_intake")
        async with engine.begin() as db:
            service = await db.scalar(
                text(
                    "INSERT INTO service_projects(customer_id,kind) VALUES(:user,'custom_design') RETURNING id"
                ),
                {"user": user},
            )
            design_request = await db.scalar(
                text(
                    "INSERT INTO service_requests(service_project_id,customer_id,service_type,stage_kind,canonical_spec_sha256) VALUES(:project,:user,'custom_design','design',:sha) RETURNING id"
                ),
                {"project": service, "user": user, "sha": "f" * 64},
            )
            await db.execute(
                text(
                    "INSERT INTO design_projects(request_id,service_project_id,customer_id,brief) VALUES(:request,:project,:user,'{}'::jsonb)"
                ),
                {"request": design_request, "project": service, "user": user},
            )
        await engine.dispose()
        with pytest.raises(subprocess.CalledProcessError):
            run_migration(migration_database, "downgrade", "0003_printing_intake")
        async with engine.begin() as db:
            assert (
                await db.scalar(text("SELECT version_num FROM alembic_version"))
                == "0004_design_intake"
            )
            assert await db.scalar(text("SELECT count(*) FROM design_projects")) == 1
    finally:
        await engine.dispose()


async def test_analysis_upgrade_preserves_m05_data_and_guarded_recovery(
    migration_database: str,
) -> None:
    run_migration(migration_database, "upgrade", "0004_design_intake")
    engine = create_async_engine(migration_database, hide_parameters=True)
    try:
        async with engine.begin() as db:
            user = await db.scalar(
                text(
                    "INSERT INTO users(telegram_id,display_name) VALUES(60606,'M05 seed') RETURNING id"
                )
            )
            project = await db.scalar(
                text(
                    "INSERT INTO service_projects(customer_id,kind) VALUES(:u,'custom_design') RETURNING id"
                ),
                {"u": user},
            )
            request = await db.scalar(
                text(
                    "INSERT INTO service_requests(service_project_id,customer_id,service_type,stage_kind,canonical_spec_sha256) VALUES(:p,:u,'custom_design','design',repeat('a',64)) RETURNING id"
                ),
                {"p": project, "u": user},
            )
            design = await db.scalar(
                text(
                    "INSERT INTO design_projects(request_id,service_project_id,customer_id,brief) VALUES(:r,:p,:u,'{}'::jsonb) RETURNING id"
                ),
                {"r": request, "p": project, "u": user},
            )
            await db.execute(
                text(
                    "INSERT INTO sessions(user_id,token_hash,init_data_hash,expires_at) VALUES(:u,repeat('b',64),repeat('c',64),now()+interval '1 hour')"
                ),
                {"u": user},
            )
        await engine.dispose()
        run_migration(migration_database, "upgrade", "0005_isolated_slicing")
        async with engine.begin() as db:
            assert (
                await db.scalar(text("SELECT version_num FROM alembic_version"))
                == "0005_isolated_slicing"
            )
            assert await db.scalar(text("SELECT id FROM design_projects")) == design
            assert await db.scalar(text("SELECT token_hash FROM sessions")) == "b" * 64
            assert (
                await db.scalar(text("SELECT canonical_spec_sha256 FROM service_requests"))
                == "a" * 64
            )
            assert await db.scalar(text("SELECT count(*) FROM slicer_profiles")) == 0
            assert await db.scalar(text("SELECT to_regclass('public.printers')")) is None
        await engine.dispose()
        run_migration(migration_database, "downgrade", "0004_design_intake")
        run_migration(migration_database, "upgrade", "0005_isolated_slicing")
        async with engine.begin() as db:
            await db.execute(
                text(
                    "INSERT INTO virtual_printer_models(key,version,label,capabilities) VALUES('virtual-seed',1,'Synthetic virtual registry','{}')"
                )
            )
        await engine.dispose()
        with pytest.raises(subprocess.CalledProcessError):
            run_migration(migration_database, "downgrade", "0004_design_intake")
        async with engine.begin() as db:
            assert await db.scalar(text("SELECT count(*) FROM virtual_printer_models")) == 1
            assert await db.scalar(text("SELECT id FROM design_projects")) == design
    finally:
        await engine.dispose()


async def test_m07_upgrade_preserves_auth_and_prior_history_and_guards_recovery(migration_database):
    run_migration(migration_database, "upgrade", "0005_isolated_slicing")
    engine = create_async_engine(migration_database, hide_parameters=True)
    try:
        async with engine.begin() as db:
            identity = await db.scalar(
                text(
                    "INSERT INTO users(telegram_id,display_name,role) VALUES(111,'Synthetic Owner','owner') RETURNING id"
                )
            )
            await db.execute(
                text(
                    "INSERT INTO sessions(user_id,token_hash,init_data_hash,expires_at) VALUES(:u,repeat('a',64),repeat('b',64),now()+interval '1 hour')"
                ),
                {"u": identity},
            )
            project = await db.scalar(
                text(
                    "INSERT INTO service_projects(customer_id,kind) VALUES(:u,'printing') RETURNING id"
                ),
                {"u": identity},
            )
            request = await db.scalar(
                text(
                    "INSERT INTO service_requests(service_project_id,customer_id,service_type,stage_kind,canonical_spec_sha256) VALUES(:p,:u,'printing','printing',repeat('a',64)) RETURNING id"
                ),
                {"p": project, "u": identity},
            )
            audit = await db.scalar(
                text(
                    "INSERT INTO audit_logs(actor_user_id,action,entity_id,metadata_snapshot) VALUES(:u,'request.created',:r,jsonb_build_object('legacy',true)) RETURNING id"
                ),
                {"u": identity, "r": request},
            )
            await db.execute(
                text(
                    "INSERT INTO notification_outbox(audit_log_id,recipient_user_id,event_type,payload_minimized) VALUES(:a,:u,'request.created','{}')"
                ),
                {"a": audit, "u": identity},
            )
            await db.execute(
                text(
                    "INSERT INTO idempotency_records(actor_user_id,action,key,request_hash,response_json) VALUES(:u,'request.create','m07-migration-legacy',repeat('b',64),jsonb_build_object('preserved',true))"
                ),
                {"u": identity},
            )
        run_migration(migration_database, "upgrade", "head")
        async with engine.begin() as db:
            assert (
                await db.scalar(text("SELECT version_num FROM alembic_version"))
                == "0006_pricing_eligibility"
            )
            assert await db.scalar(text("SELECT token_hash FROM sessions")) == "a" * 64
            assert await db.scalar(text("SELECT id FROM users")) == identity
            assert await db.scalar(text("SELECT id FROM service_requests")) == request
            assert (
                await db.scalar(text("SELECT canonical_spec_sha256 FROM service_requests"))
                == "a" * 64
            )
            assert await db.scalar(text("SELECT entity_kind FROM audit_logs")) == "request"
            assert await db.scalar(text("SELECT entity_id FROM audit_logs")) == request
            assert await db.scalar(text("SELECT metadata_snapshot FROM audit_logs")) == {
                "legacy": True
            }
            assert await db.scalar(text("SELECT count(*) FROM notification_outbox")) == 1
            assert await db.scalar(text("SELECT response_json FROM idempotency_records")) == {
                "preserved": True
            }
            for table in (
                "pricing_policies",
                "pricing_availability_fixtures",
                "pricing_estimates",
                "pricing_estimate_lines",
            ):
                assert await db.scalar(text("SELECT to_regclass(:table)"), {"table": table})
            assert (
                await db.scalar(
                    text(
                        "SELECT count(*) FROM pg_trigger WHERE tgname IN ('pricing_estimate_balance','pricing_line_balance') AND tgdeferrable AND tginitdeferred"
                    )
                )
                == 2
            )
        run_migration(migration_database, "downgrade", "0005_isolated_slicing")
        run_migration(migration_database, "upgrade", "head")
        async with engine.begin() as db:
            await db.execute(
                text(
                    "INSERT INTO pricing_policies(stage_kind,version,currency_code,configuration,checksum,created_by,reason) VALUES('design',1,'XTR',jsonb_build_object('simulation_only',true),repeat('c',64),:u,'Synthetic migration recovery fixture')"
                ),
                {"u": identity},
            )
        with pytest.raises(subprocess.CalledProcessError):
            run_migration(migration_database, "downgrade", "0005_isolated_slicing")
        async with engine.begin() as db:
            assert await db.scalar(text("SELECT count(*) FROM pricing_policies")) == 1
            assert await db.scalar(text("SELECT count(*) FROM sessions")) == 1
    finally:
        await engine.dispose()
