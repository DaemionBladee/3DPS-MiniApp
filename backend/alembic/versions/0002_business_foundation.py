"""Business foundation

Revision ID: 0002_business_foundation
Revises: 0001_auth_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_business_foundation"
down_revision: str | None = "0001_auth_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("actor_user_id", "action", "key"),
    )
    op.create_table(
        "service_projects",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), server_default="simulation", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('printing','custom_design','design_and_print')", name="ck_project_kind"
        ),
        sa.CheckConstraint("mode = 'simulation'", name="ck_project_mode"),
        sa.ForeignKeyConstraint(["customer_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "customer_id", "kind", "mode", name="uq_project_lineage"),
    )
    op.create_index(
        op.f("ix_service_projects_customer_created"),
        "service_projects",
        ["customer_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "service_requests",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("service_project_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("service_type", sa.String(length=32), nullable=False),
        sa.Column("stage_kind", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=16), server_default="simulation", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("canonical_spec_sha256", sa.String(length=64), nullable=False),
        sa.Column("customer_notes", sa.String(length=2000), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(service_type = 'printing' AND stage_kind = 'printing') OR (service_type IN ('custom_design','design_and_print') AND stage_kind = 'design')",
            name="ck_request_initial_stage",
        ),
        sa.CheckConstraint("canonical_spec_sha256 ~ '^[0-9a-f]{64}$'", name="ck_request_hash"),
        sa.CheckConstraint("mode = 'simulation'", name="ck_request_mode"),
        sa.CheckConstraint("status IN ('draft','cancelled')", name="ck_request_status"),
        sa.CheckConstraint("version > 0 AND revision > 0", name="ck_request_versions"),
        sa.ForeignKeyConstraint(["customer_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["service_project_id", "customer_id", "service_type", "mode"],
            [
                "service_projects.id",
                "service_projects.customer_id",
                "service_projects.kind",
                "service_projects.mode",
            ],
            name="fk_request_project_lineage",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_project_id", "stage_kind", name="uq_request_project_stage"),
    )
    op.create_index(
        op.f("ix_service_requests_customer_created"),
        "service_requests",
        ["customer_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_service_requests_service_project_id"),
        "service_requests",
        ["service_project_id"],
        unique=False,
    )
    op.create_index(
        "ix_service_requests_created", "service_requests", ["created_at", "id"], unique=False
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("metadata_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entity_id"], ["service_requests.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_audit_logs_actor_user_id"), "audit_logs", ["actor_user_id"], unique=False
    )
    op.create_index(op.f("ix_audit_logs_entity_id"), "audit_logs", ["entity_id"], unique=False)
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "event_key", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("audit_log_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload_minimized", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status = 'pending'", name="ck_outbox_pending"),
        sa.ForeignKeyConstraint(["audit_log_id"], ["audit_logs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("audit_log_id"),
        sa.UniqueConstraint("event_key"),
    )
    op.create_index(
        op.f("ix_notification_outbox_recipient_user_id"),
        "notification_outbox",
        ["recipient_user_id"],
        unique=False,
    )

    # Append-only at the database boundary, including accidental ORM writes.
    # Table owners/superusers remain a trusted administrative boundary.
    op.execute("""
        CREATE FUNCTION reject_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Audit events are immutable' USING ERRCODE = '23514';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER audit_logs_immutable BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()
    """)


def downgrade() -> None:
    # Destructive recovery is for disposable databases only. Production recovery
    # requires backup/forward-migration review; it must not erase audit history.
    op.execute("DROP TRIGGER audit_logs_immutable ON audit_logs")
    op.execute("DROP FUNCTION reject_audit_mutation()")
    op.drop_index(
        op.f("ix_notification_outbox_recipient_user_id"), table_name="notification_outbox"
    )
    op.drop_table("notification_outbox")
    op.drop_index(op.f("ix_audit_logs_entity_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_user_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index(op.f("ix_service_requests_service_project_id"), table_name="service_requests")
    op.drop_index(op.f("ix_service_requests_customer_created"), table_name="service_requests")
    op.drop_index("ix_service_requests_created", table_name="service_requests")
    op.drop_table("service_requests")
    op.drop_index(op.f("ix_service_projects_customer_created"), table_name="service_projects")
    op.drop_table("service_projects")
    op.drop_table("idempotency_records")
