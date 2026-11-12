"""M06 virtual simulation profiles, immutable results and fenced task leases.

Existing revisions remain untouched. Downgrade refuses retained M06 history.
"""

from alembic import op

revision = "0005_isolated_slicing"
down_revision = "0004_design_intake"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE virtual_printer_models (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    key VARCHAR(64) NOT NULL, 
    version INTEGER NOT NULL, 
    label VARCHAR(160) NOT NULL, 
    technology VARCHAR(8) DEFAULT 'FDM' NOT NULL, 
    capabilities JSONB NOT NULL, 
    calibrated BOOLEAN DEFAULT false NOT NULL, 
    simulation_only BOOLEAN DEFAULT true NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_virtual_model_version UNIQUE (key, version), 
    CONSTRAINT ck_virtual_simulation CHECK (technology = 'FDM' AND NOT calibrated AND simulation_only), 
    CONSTRAINT ck_virtual_version CHECK (version > 0)
)"""
    )
    op.execute(
        """CREATE TABLE slicer_profiles (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    virtual_printer_model_id UUID NOT NULL, 
    key VARCHAR(64) NOT NULL, 
    version INTEGER NOT NULL, 
    material_key VARCHAR(32) NOT NULL, 
    quality_key VARCHAR(32) NOT NULL, 
    configuration JSONB NOT NULL, 
    config_sha256 VARCHAR(64) NOT NULL, 
    engine_version VARCHAR(64) NOT NULL, 
    executable_sha256 VARCHAR(64) NOT NULL, 
    worker_image VARCHAR(71) NOT NULL, 
    approval_status VARCHAR(16) DEFAULT 'approved' NOT NULL, 
    active BOOLEAN DEFAULT true NOT NULL, 
    calibrated BOOLEAN DEFAULT false NOT NULL, 
    simulation_only BOOLEAN DEFAULT true NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_slicer_profile_version UNIQUE (key, version), 
    CONSTRAINT ck_profile_simulation CHECK (version > 0 AND approval_status = 'approved' AND NOT calibrated AND simulation_only), 
    CONSTRAINT ck_profile_checksums CHECK (config_sha256 ~ '^[0-9a-f]{64}$' AND executable_sha256 ~ '^[0-9a-f]{64}$' AND worker_image ~ '^sha256:[0-9a-f]{64}$'), 
    FOREIGN KEY(virtual_printer_model_id) REFERENCES virtual_printer_models (id) ON DELETE RESTRICT
)"""
    )
    op.execute(
        "ALTER TABLE audit_logs ALTER COLUMN actor_user_id DROP NOT NULL, ADD COLUMN actor_kind varchar(16) NOT NULL DEFAULT 'user', ADD COLUMN system_actor varchar(64), ADD CONSTRAINT ck_audit_actor CHECK ((actor_kind='user' AND actor_user_id IS NOT NULL AND system_actor IS NULL) OR (actor_kind='system' AND actor_user_id IS NULL AND system_actor='analysis-orchestrator'))"
    )
    op.execute(
        "ALTER TABLE request_items ADD COLUMN dimension_x_mm float8, ADD COLUMN dimension_y_mm float8, ADD COLUMN dimension_z_mm float8, ADD COLUMN dimension_tolerance_mm float8 NOT NULL DEFAULT 0.5"
    )
    op.execute(
        "ALTER TABLE request_items ADD CONSTRAINT ck_item_dimensions CHECK ((dimension_x_mm IS NULL AND dimension_y_mm IS NULL AND dimension_z_mm IS NULL) OR (dimension_x_mm > 0 AND dimension_x_mm <= 1000000 AND dimension_y_mm > 0 AND dimension_y_mm <= 1000000 AND dimension_z_mm > 0 AND dimension_z_mm <= 1000000 AND dimension_x_mm IS NOT NULL AND dimension_y_mm IS NOT NULL AND dimension_z_mm IS NOT NULL))"
    )
    op.execute(
        "ALTER TABLE request_items ADD CONSTRAINT ck_item_dimension_tolerance CHECK (dimension_tolerance_mm > 0 AND dimension_tolerance_mm <= 100)"
    )
    op.execute(
        "ALTER TABLE service_requests DROP CONSTRAINT ck_request_submission_snapshot, ADD CONSTRAINT ck_request_submission_snapshot CHECK ((submitted_spec IS NULL AND submitted_at IS NULL AND submitted_revision IS NULL AND status NOT IN ('submitted','analyzing','manual_review')) OR (submitted_spec IS NOT NULL AND submitted_at IS NOT NULL AND submitted_revision IS NOT NULL AND submitted_revision = revision AND status IN ('submitted','analyzing','manual_review','cancelled')))"
    )
    op.execute(
        "ALTER TABLE service_requests DROP CONSTRAINT ck_request_status, ADD CONSTRAINT ck_request_status CHECK (status IN ('draft','submitted','analyzing','manual_review','cancelled'))"
    )
    op.execute(
        "ALTER TABLE processing_tasks DROP CONSTRAINT ck_task_pending_only, ADD COLUMN attempts integer NOT NULL DEFAULT 0, ADD COLUMN max_attempts integer NOT NULL DEFAULT 3, ADD COLUMN lease_token uuid, ADD COLUMN lease_owner varchar(80), ADD COLUMN lease_expires_at timestamptz, ADD COLUMN next_available_at timestamptz NOT NULL DEFAULT now(), ADD COLUMN started_at timestamptz, ADD COLUMN completed_at timestamptz, ADD COLUMN error_code varchar(80), ADD COLUMN retryable boolean NOT NULL DEFAULT false, ADD COLUMN selected_profile_id uuid REFERENCES slicer_profiles(id) ON DELETE RESTRICT, ADD COLUMN result_run_id uuid"
    )
    op.execute(
        "ALTER TABLE processing_tasks ADD CONSTRAINT ck_task_state CHECK (state IN ('pending','leased','succeeded','failed','superseded'))"
    )
    op.execute(
        "ALTER TABLE processing_tasks ADD CONSTRAINT ck_task_attempts CHECK (attempts >= 0 AND max_attempts BETWEEN 3 AND 6 AND attempts <= max_attempts)"
    )
    op.execute(
        "ALTER TABLE processing_tasks ADD CONSTRAINT ck_task_running_result CHECK (state != 'leased' OR result_run_id IS NULL)"
    )
    op.execute(
        "ALTER TABLE processing_tasks ADD CONSTRAINT ck_task_success CHECK (state != 'succeeded' OR (result_run_id IS NOT NULL AND started_at IS NOT NULL AND completed_at IS NOT NULL))"
    )
    op.execute(
        "ALTER TABLE processing_tasks ADD CONSTRAINT ck_task_failure CHECK (state != 'failed' OR (error_code IS NOT NULL AND completed_at IS NOT NULL))"
    )
    op.execute(
        "ALTER TABLE processing_tasks ADD CONSTRAINT ck_task_lease CHECK ((state = 'leased' AND lease_token IS NOT NULL AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL) OR (state != 'leased' AND lease_token IS NULL AND lease_owner IS NULL AND lease_expires_at IS NULL))"
    )
    op.execute(
        """CREATE TABLE model_analyses (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    task_id UUID NOT NULL, 
    lease_token UUID NOT NULL, 
    request_id UUID NOT NULL, 
    customer_id UUID NOT NULL, 
    request_item_id UUID NOT NULL, 
    uploaded_file_id UUID NOT NULL, 
    request_revision INTEGER NOT NULL, 
    input_sha256 VARCHAR(64) NOT NULL, 
    spec_sha256 VARCHAR(64) NOT NULL, 
    analyzer_version VARCHAR(64) NOT NULL, 
    geometry JSONB NOT NULL, 
    simulation_only BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_analysis_attempt UNIQUE (task_id, lease_token), 
    CONSTRAINT uq_analysis_task_attempt UNIQUE (id, task_id, lease_token), 
    CONSTRAINT fk_analysis_item FOREIGN KEY(request_item_id, request_id, customer_id) REFERENCES request_items (id, request_id, customer_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_analysis_file FOREIGN KEY(uploaded_file_id, request_id, customer_id) REFERENCES uploaded_files (id, request_id, owner_id) ON DELETE RESTRICT, 
    CONSTRAINT ck_analysis_provenance CHECK (input_sha256 ~ '^[0-9a-f]{64}$' AND spec_sha256 ~ '^[0-9a-f]{64}$' AND request_revision > 0), 
    CONSTRAINT ck_analysis_simulation CHECK (simulation_only), 
    FOREIGN KEY(task_id) REFERENCES processing_tasks (id) ON DELETE RESTRICT
)"""
    )
    op.execute(
        """CREATE TABLE slicing_runs (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    task_id UUID NOT NULL, 
    lease_token UUID NOT NULL, 
    model_analysis_id UUID NOT NULL, 
    slicer_profile_id UUID NOT NULL, 
    outcome VARCHAR(24) NOT NULL, 
    profile_snapshot JSONB NOT NULL, 
    engine_version VARCHAR(64) NOT NULL, 
    executable_sha256 VARCHAR(64) NOT NULL, 
    worker_image VARCHAR(71) NOT NULL, 
    estimate JSONB, 
    sandbox_evidence JSONB NOT NULL, 
    simulation_only BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_slicing_attempt UNIQUE (task_id, lease_token), 
    CONSTRAINT uq_slicing_task_result UNIQUE (id, task_id), 
    CONSTRAINT fk_run_analysis_attempt FOREIGN KEY(model_analysis_id, task_id, lease_token) REFERENCES model_analyses (id, task_id, lease_token) ON DELETE RESTRICT, 
    CONSTRAINT ck_run_simulation CHECK (outcome IN ('estimated','manual_review') AND simulation_only), 
    CONSTRAINT ck_run_estimate CHECK ((outcome='estimated' AND estimate IS NOT NULL) OR (outcome='manual_review' AND estimate IS NULL)), 
    FOREIGN KEY(task_id) REFERENCES processing_tasks (id) ON DELETE RESTRICT, 
    FOREIGN KEY(slicer_profile_id) REFERENCES slicer_profiles (id) ON DELETE RESTRICT
)"""
    )
    op.execute(
        "ALTER TABLE processing_tasks ADD CONSTRAINT fk_task_result FOREIGN KEY(result_run_id,id) REFERENCES slicing_runs(id,task_id) ON DELETE RESTRICT"
    )
    op.execute("CREATE INDEX ix_task_claim ON processing_tasks(state,next_available_at,created_at)")
    op.execute(
        "CREATE FUNCTION m06_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Immutable simulation history' USING ERRCODE='23514'; END $$"
    )
    op.execute(
        "CREATE TRIGGER virtual_printer_models_immutable BEFORE UPDATE OR DELETE ON virtual_printer_models FOR EACH ROW EXECUTE FUNCTION m06_immutable()"
    )
    op.execute(
        "CREATE TRIGGER model_analyses_immutable BEFORE UPDATE OR DELETE ON model_analyses FOR EACH ROW EXECUTE FUNCTION m06_immutable()"
    )
    op.execute(
        "CREATE TRIGGER slicing_runs_immutable BEFORE UPDATE OR DELETE ON slicing_runs FOR EACH ROW EXECUTE FUNCTION m06_immutable()"
    )
    op.execute(
        "CREATE FUNCTION m06_profile_frozen() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF TG_OP='DELETE' OR (to_jsonb(NEW)-'active') IS DISTINCT FROM (to_jsonb(OLD)-'active') THEN RAISE EXCEPTION 'Create a new profile revision' USING ERRCODE='23514'; END IF; RETURN NEW; END $$"
    )
    op.execute(
        "CREATE TRIGGER slicer_profiles_frozen BEFORE UPDATE OR DELETE ON slicer_profiles FOR EACH ROW EXECUTE FUNCTION m06_profile_frozen()"
    )
    op.execute(
        """CREATE FUNCTION m06_result_provenance() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE t processing_tasks; f uploaded_files; r service_requests;
BEGIN
 SELECT * INTO t FROM processing_tasks WHERE id=NEW.task_id FOR UPDATE;
 SELECT * INTO r FROM service_requests WHERE id=t.request_id;
 SELECT * INTO f FROM uploaded_files WHERE id=t.uploaded_file_id;
 IF t.state!='leased' OR t.lease_token IS DISTINCT FROM NEW.lease_token OR t.lease_expires_at <= clock_timestamp()
 OR r.revision!=t.request_revision OR r.canonical_spec_sha256!=t.spec_sha256 OR r.status NOT IN ('submitted','analyzing','manual_review')
 OR NEW.request_id!=t.request_id OR NEW.customer_id!=t.customer_id OR NEW.uploaded_file_id!=t.uploaded_file_id
 OR NEW.request_item_id IS DISTINCT FROM f.request_item_id OR NEW.input_sha256 IS DISTINCT FROM f.sha256
 OR NEW.request_revision!=t.request_revision OR NEW.spec_sha256!=t.spec_sha256
 OR f.storage_state!='ready' OR f.validation_status!='validated' THEN
 RAISE EXCEPTION 'Invalid or stale result provenance' USING ERRCODE='23514'; END IF; RETURN NEW;
END $$"""
    )
    op.execute(
        "CREATE TRIGGER model_analysis_provenance BEFORE INSERT ON model_analyses FOR EACH ROW EXECUTE FUNCTION m06_result_provenance()"
    )
    op.execute(
        """CREATE FUNCTION m06_run_provenance() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE p slicer_profiles; t processing_tasks;
BEGIN SELECT * INTO t FROM processing_tasks WHERE id=NEW.task_id;
 SELECT * INTO p FROM slicer_profiles WHERE id=NEW.slicer_profile_id;
 IF t.selected_profile_id IS DISTINCT FROM p.id OR NEW.engine_version IS DISTINCT FROM p.engine_version
 OR NEW.worker_image IS DISTINCT FROM p.worker_image OR NEW.executable_sha256 IS DISTINCT FROM p.executable_sha256
 OR NEW.profile_snapshot IS DISTINCT FROM jsonb_build_object('id',p.id,'key',p.key,'version',p.version,'virtual_printer_model_id',p.virtual_printer_model_id,'config_sha256',p.config_sha256,'configuration',p.configuration)
 THEN RAISE EXCEPTION 'Invalid profile provenance' USING ERRCODE='23514'; END IF; RETURN NEW; END $$"""
    )
    op.execute(
        "CREATE TRIGGER slicing_run_provenance BEFORE INSERT ON slicing_runs FOR EACH ROW EXECUTE FUNCTION m06_run_provenance()"
    )

    op.execute("""CREATE FUNCTION m06_task_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE result slicing_runs;
    BEGIN
      IF (NEW.request_id,NEW.uploaded_file_id,NEW.customer_id,NEW.request_revision,NEW.spec_sha256,NEW.kind)
          IS DISTINCT FROM
         (OLD.request_id,OLD.uploaded_file_id,OLD.customer_id,OLD.request_revision,OLD.spec_sha256,OLD.kind)
      THEN RAISE EXCEPTION 'Task provenance is immutable' USING ERRCODE='23514'; END IF;
      IF NEW.state='succeeded' AND OLD.state IS DISTINCT FROM 'succeeded' THEN
        SELECT * INTO result FROM slicing_runs WHERE id=NEW.result_run_id;
        IF OLD.state!='leased' OR OLD.lease_expires_at <= clock_timestamp()
           OR OLD.lease_token IS DISTINCT FROM result.lease_token OR result.task_id IS DISTINCT FROM OLD.id
        THEN RAISE EXCEPTION 'Stale completion fence' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER processing_task_guard BEFORE UPDATE ON processing_tasks FOR EACH ROW EXECUTE FUNCTION m06_task_guard()"
    )


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN IF EXISTS(SELECT 1 FROM virtual_printer_models) OR EXISTS(SELECT 1 FROM model_analyses) OR EXISTS(SELECT 1 FROM processing_tasks WHERE attempts>0) OR EXISTS(SELECT 1 FROM audit_logs WHERE actor_kind='system') OR EXISTS(SELECT 1 FROM request_items WHERE dimension_x_mm IS NOT NULL) OR EXISTS(SELECT 1 FROM service_requests WHERE status IN ('analyzing','manual_review')) THEN RAISE EXCEPTION 'Refusing to remove retained M06 history'; END IF; END $$"""
    )
    op.execute("DROP TRIGGER processing_task_guard ON processing_tasks")
    op.execute("DROP FUNCTION m06_task_guard()")
    op.execute("ALTER TABLE processing_tasks DROP CONSTRAINT fk_task_result")
    op.execute("DROP TABLE slicing_runs, model_analyses")
    op.execute("DROP FUNCTION m06_run_provenance(), m06_result_provenance()")
    op.execute("ALTER TABLE processing_tasks DROP COLUMN selected_profile_id")
    op.execute("DROP TABLE slicer_profiles, virtual_printer_models")
    op.execute("DROP FUNCTION m06_profile_frozen(), m06_immutable()")
    op.execute("DROP INDEX ix_task_claim")
    op.execute(
        "ALTER TABLE processing_tasks DROP CONSTRAINT ck_task_state, DROP CONSTRAINT ck_task_attempts, DROP CONSTRAINT ck_task_lease, DROP CONSTRAINT ck_task_success, DROP CONSTRAINT ck_task_running_result, DROP CONSTRAINT ck_task_failure, ADD CONSTRAINT ck_task_pending_only CHECK(state IN ('pending','superseded'))"
    )
    for column in [
        "attempts",
        "max_attempts",
        "lease_token",
        "lease_owner",
        "lease_expires_at",
        "next_available_at",
        "started_at",
        "completed_at",
        "error_code",
        "retryable",
        "result_run_id",
    ]:
        op.execute(f"ALTER TABLE processing_tasks DROP COLUMN {column}")
    op.execute(
        "ALTER TABLE request_items DROP COLUMN dimension_x_mm, DROP COLUMN dimension_y_mm, DROP COLUMN dimension_z_mm, DROP COLUMN dimension_tolerance_mm"
    )
    op.execute(
        "ALTER TABLE audit_logs DROP CONSTRAINT ck_audit_actor, DROP COLUMN actor_kind, DROP COLUMN system_actor, ALTER COLUMN actor_user_id SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE service_requests DROP CONSTRAINT ck_request_status, ADD CONSTRAINT ck_request_status CHECK(status IN ('draft','submitted','cancelled')), DROP CONSTRAINT ck_request_submission_snapshot, ADD CONSTRAINT ck_request_submission_snapshot CHECK((submitted_spec IS NULL AND submitted_at IS NULL AND submitted_revision IS NULL AND status != 'submitted') OR (submitted_spec IS NOT NULL AND submitted_at IS NOT NULL AND submitted_revision IS NOT NULL AND submitted_revision = revision AND status IN ('submitted','cancelled')))"
    )
