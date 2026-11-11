"""Secure printing intake

Revision ID: 0003_printing_intake
Revises: 0002_business_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_printing_intake"
down_revision: str | None = "0002_business_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "service_requests",
        sa.Column("spec_schema_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "service_requests",
        sa.Column(
            "fulfillment_method", sa.String(length=16), server_default="pickup", nullable=False
        ),
    )
    op.add_column(
        "service_requests",
        sa.Column("fulfillment_notes", sa.String(length=1000), server_default="", nullable=False),
    )
    op.add_column("service_requests", sa.Column("submitted_revision", sa.Integer(), nullable=True))
    op.add_column(
        "service_requests", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "service_requests",
        sa.Column("submitted_spec", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_unique_constraint(
        "uq_request_owner_stage", "service_requests", ["id", "customer_id", "stage_kind"]
    )
    op.drop_constraint("ck_request_status", "service_requests", type_="check")
    op.create_check_constraint(
        "ck_request_status", "service_requests", "status IN ('draft','submitted','cancelled')"
    )
    op.create_check_constraint(
        "ck_request_fulfillment", "service_requests", "fulfillment_method IN ('pickup','delivery')"
    )
    op.create_check_constraint(
        "ck_request_spec_schema", "service_requests", "spec_schema_version IN (1,2)"
    )
    op.create_check_constraint(
        "ck_request_submission_snapshot",
        "service_requests",
        "(submitted_spec IS NULL AND submitted_at IS NULL AND submitted_revision IS NULL AND status != 'submitted') OR (submitted_spec IS NOT NULL AND submitted_at IS NOT NULL AND submitted_revision IS NOT NULL AND submitted_revision = revision AND status IN ('submitted','cancelled'))",
    )
    op.create_table(
        "request_items",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("stage_kind", sa.String(length=16), server_default="printing", nullable=False),
        sa.Column("request_revision", sa.Integer(), nullable=False),
        sa.Column("model_file_id", sa.Uuid(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("description", sa.String(length=300), server_default="", nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("material_key", sa.String(length=32), nullable=True),
        sa.Column("color_key", sa.String(length=32), nullable=True),
        sa.Column("quality_key", sa.String(length=32), nullable=True),
        sa.Column("unit_key", sa.String(length=8), server_default="mm", nullable=False),
        sa.Column("unit_confirmed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "special_requirements", sa.String(length=2000), server_default="", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("stage_kind = 'printing'", name="ck_item_printing"),
        sa.CheckConstraint("unit_key IN ('mm','cm','inch','um','ft','m')", name="ck_item_units"),
        sa.CheckConstraint(
            "quantity BETWEEN 1 AND 1000 AND request_revision > 0", name="ck_item_spec_bounds"
        ),
        sa.ForeignKeyConstraint(
            ["request_id", "customer_id", "stage_kind"],
            ["service_requests.id", "service_requests.customer_id", "service_requests.stage_kind"],
            name="fk_item_print_request",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "request_id", "customer_id", name="uq_item_request_owner"),
    )
    op.create_index(
        "ix_request_items_request", "request_items", ["request_id", "active"], unique=False
    )
    op.create_table(
        "uploaded_files",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("request_item_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("request_revision", sa.Integer(), nullable=False),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("upload_key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=32), nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reserved_bytes", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expected_sha256", sa.String(length=64), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("original_name", sa.String(length=200), nullable=False),
        sa.Column("format", sa.String(length=8), nullable=True),
        sa.Column("mime_detected", sa.String(length=100), nullable=True),
        sa.Column(
            "format_details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "validation_status", sa.String(length=16), server_default="pending", nullable=False
        ),
        sa.Column(
            "storage_state", sa.String(length=16), server_default="receiving", nullable=False
        ),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "expected_sha256 ~ '^[0-9a-f]{64}$' AND (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$')",
            name="ck_file_hash",
        ),
        sa.CheckConstraint(
            "storage_state IN ('receiving','ready','delete_pending','deleted')",
            name="ck_file_storage",
        ),
        sa.CheckConstraint(
            "validation_status != 'validated' OR (sha256 IS NOT NULL AND sha256 = expected_sha256 AND size_bytes = reserved_bytes AND format IS NOT NULL)",
            name="ck_file_validated",
        ),
        sa.CheckConstraint(
            "validation_status IN ('pending','validated','rejected','removed')",
            name="ck_file_validation",
        ),
        sa.CheckConstraint(
            "reserved_bytes > 0 AND size_bytes >= 0 AND request_revision > 0",
            name="ck_file_size_revision",
        ),
        sa.ForeignKeyConstraint(
            ["request_item_id", "request_id", "owner_id"],
            ["request_items.id", "request_items.request_id", "request_items.customer_id"],
            name="fk_file_item_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "request_id", "owner_id", name="uq_file_request_owner"),
        sa.UniqueConstraint(
            "id", "request_item_id", "request_id", "owner_id", name="uq_file_item_lineage"
        ),
        sa.UniqueConstraint("owner_id", "request_id", "upload_key", name="uq_upload_command"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        "ix_uploaded_files_cleanup",
        "uploaded_files",
        ["storage_state", "lease_expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_uploaded_files_quota",
        "uploaded_files",
        ["owner_id", "request_id", "storage_state"],
        unique=False,
    )
    op.create_table(
        "processing_tasks",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_file_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("request_revision", sa.Integer(), nullable=False),
        sa.Column("spec_sha256", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), server_default="model_analysis", nullable=False),
        sa.Column("state", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind = 'model_analysis' AND request_revision > 0", name="ck_task_kind_revision"
        ),
        sa.CheckConstraint("state IN ('pending','superseded')", name="ck_task_pending_only"),
        sa.ForeignKeyConstraint(
            ["uploaded_file_id", "request_id", "customer_id"],
            ["uploaded_files.id", "uploaded_files.request_id", "uploaded_files.owner_id"],
            name="fk_task_file_lineage",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "request_id",
            "request_revision",
            "uploaded_file_id",
            "kind",
            name="uq_task_revision_file_kind",
        ),
    )
    op.create_index(
        "ix_processing_tasks_request_revision",
        "processing_tasks",
        ["request_id", "request_revision"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_item_current_model",
        "request_items",
        "uploaded_files",
        ["model_file_id", "id", "request_id", "customer_id"],
        ["id", "request_item_id", "request_id", "owner_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint("ck_task_hash", "processing_tasks", "spec_sha256 ~ '^[0-9a-f]{64}$'")
    op.execute("""
        CREATE FUNCTION freeze_submitted_print_spec() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.submitted_spec IS NOT NULL AND
               (NEW.submitted_spec, NEW.submitted_at, NEW.submitted_revision,
                NEW.revision, NEW.canonical_spec_sha256, NEW.customer_notes,
                NEW.fulfillment_method, NEW.fulfillment_notes, NEW.spec_schema_version,
                NEW.service_project_id, NEW.customer_id, NEW.stage_kind, NEW.service_type, NEW.mode)
               IS DISTINCT FROM
               (OLD.submitted_spec, OLD.submitted_at, OLD.submitted_revision,
                OLD.revision, OLD.canonical_spec_sha256, OLD.customer_notes,
                OLD.fulfillment_method, OLD.fulfillment_notes, OLD.spec_schema_version,
                OLD.service_project_id, OLD.customer_id, OLD.stage_kind, OLD.service_type, OLD.mode) THEN
                RAISE EXCEPTION 'Submitted specification is immutable' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute(
        "CREATE TRIGGER request_submission_frozen BEFORE UPDATE ON service_requests FOR EACH ROW EXECUTE FUNCTION freeze_submitted_print_spec()"
    )
    op.execute("""
        CREATE FUNCTION guard_print_item_edit() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE parent_id uuid;
        BEGIN
            IF TG_OP = 'DELETE' THEN parent_id := OLD.request_id;
            ELSE parent_id := NEW.request_id; END IF;
            IF TG_OP = 'UPDATE' AND EXISTS (SELECT 1 FROM service_requests WHERE id=OLD.request_id AND submitted_spec IS NOT NULL) THEN
                RAISE EXCEPTION 'Submitted print items are immutable' USING ERRCODE='23514';
            END IF;
            IF EXISTS (SELECT 1 FROM service_requests WHERE id=parent_id AND submitted_spec IS NOT NULL) THEN
                RAISE EXCEPTION 'Submitted print items are immutable' USING ERRCODE='23514';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute(
        "CREATE TRIGGER item_submission_frozen BEFORE INSERT OR UPDATE OR DELETE ON request_items FOR EACH ROW EXECUTE FUNCTION guard_print_item_edit()"
    )
    op.execute("""
        CREATE FUNCTION freeze_validated_file() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.sha256 IS NOT NULL AND
                (NEW.request_id,NEW.request_item_id,NEW.owner_id,NEW.storage_key,NEW.sha256,
                 NEW.size_bytes,NEW.expected_sha256,NEW.original_name,NEW.format,NEW.format_details)
                IS DISTINCT FROM
                (OLD.request_id,OLD.request_item_id,OLD.owner_id,OLD.storage_key,OLD.sha256,
                 OLD.size_bytes,OLD.expected_sha256,OLD.original_name,OLD.format,OLD.format_details) THEN
                RAISE EXCEPTION 'Validated file provenance is immutable' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute(
        "CREATE TRIGGER file_provenance_frozen BEFORE UPDATE ON uploaded_files FOR EACH ROW EXECUTE FUNCTION freeze_validated_file()"
    )


def downgrade() -> None:
    # Never silently discard M04 history. Recovery of populated schemas needs
    # reviewed restore/forward migration rather than an in-place downgrade.
    op.execute("""DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM request_items) OR EXISTS(SELECT 1 FROM uploaded_files)
           OR EXISTS(SELECT 1 FROM processing_tasks)
           OR EXISTS(SELECT 1 FROM service_requests WHERE submitted_spec IS NOT NULL) THEN
            RAISE EXCEPTION 'Refusing downgrade with M04 intake data; use reviewed recovery';
        END IF;
    END $$""")
    for trigger, table in [
        ("file_provenance_frozen", "uploaded_files"),
        ("item_submission_frozen", "request_items"),
        ("request_submission_frozen", "service_requests"),
    ]:
        op.execute(f"DROP TRIGGER {trigger} ON {table}")
    for function in [
        "freeze_validated_file",
        "guard_print_item_edit",
        "freeze_submitted_print_spec",
    ]:
        op.execute(f"DROP FUNCTION {function}()")
    op.drop_constraint("fk_item_current_model", "request_items", type_="foreignkey")
    op.drop_table("processing_tasks")
    op.drop_table("uploaded_files")
    op.drop_table("request_items")
    for name in [
        "ck_request_submission_snapshot",
        "ck_request_spec_schema",
        "ck_request_fulfillment",
        "ck_request_status",
    ]:
        op.drop_constraint(name, "service_requests", type_="check")
    op.create_check_constraint(
        "ck_request_status", "service_requests", "status IN ('draft','cancelled')"
    )
    op.drop_constraint("uq_request_owner_stage", "service_requests", type_="unique")
    for name in [
        "submitted_spec",
        "submitted_at",
        "submitted_revision",
        "fulfillment_notes",
        "fulfillment_method",
        "spec_schema_version",
    ]:
        op.drop_column("service_requests", name)
