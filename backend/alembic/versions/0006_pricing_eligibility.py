"""M07 simulation pricing and fail-closed eligibility snapshots.

No offers, payment obligations, physical inventory or live state is introduced.
"""

from alembic import op

revision = "0006_pricing_eligibility"
down_revision = "0005_isolated_slicing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE pricing_policies (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	stage_kind VARCHAR(16) NOT NULL,
	version INTEGER NOT NULL,
	currency_code VARCHAR(3) NOT NULL,
	mode VARCHAR(16) DEFAULT 'simulation' NOT NULL,
	configuration JSONB NOT NULL,
	checksum VARCHAR(64) NOT NULL,
	active BOOLEAN DEFAULT true NOT NULL,
	created_by UUID NOT NULL,
	reason VARCHAR(500) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_pricing_policy_version UNIQUE (stage_kind, version),
	CONSTRAINT ck_pricing_policy_mode CHECK (stage_kind IN ('printing','design') AND version>0 AND mode='simulation'),
	CONSTRAINT ck_pricing_policy_currency CHECK ((stage_kind='printing' AND currency_code='MMK') OR (stage_kind='design' AND currency_code='XTR')),
	CONSTRAINT ck_pricing_policy_hash CHECK (checksum ~ '^[0-9a-f]{64}$'),
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT
)""")
    op.execute(
        """CREATE UNIQUE INDEX uq_active_pricing_stage ON pricing_policies (stage_kind) WHERE active"""
    )
    op.execute("""CREATE TABLE pricing_availability_fixtures (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	version INTEGER NOT NULL,
	mode VARCHAR(16) DEFAULT 'simulation' NOT NULL,
	configuration JSONB NOT NULL,
	checksum VARCHAR(64) NOT NULL,
	active BOOLEAN DEFAULT true NOT NULL,
	created_by UUID NOT NULL,
	reason VARCHAR(500) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_pricing_fixture_version UNIQUE (version),
	CONSTRAINT ck_pricing_fixture_mode CHECK (mode='simulation' AND version>0 AND expires_at>created_at),
	CONSTRAINT ck_pricing_fixture_hash CHECK (checksum ~ '^[0-9a-f]{64}$'),
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT
)""")
    op.execute(
        """CREATE UNIQUE INDEX uq_active_pricing_fixture ON pricing_availability_fixtures (active) WHERE active"""
    )
    op.execute("""CREATE TABLE pricing_estimates (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	request_id UUID NOT NULL,
	customer_id UUID NOT NULL,
	stage_kind VARCHAR(16) NOT NULL,
	number INTEGER NOT NULL,
	kind VARCHAR(24) DEFAULT 'test_estimate' NOT NULL,
	mode VARCHAR(16) DEFAULT 'simulation' NOT NULL,
	binding_authorized BOOLEAN DEFAULT false NOT NULL,
	currency_code VARCHAR(3) NOT NULL,
	payment_category VARCHAR(24) NOT NULL,
	request_revision INTEGER NOT NULL,
	spec_sha256 VARCHAR(64) NOT NULL,
	source_sha256 VARCHAR(64) NOT NULL,
	pricing_policy_id UUID NOT NULL,
	policy_checksum VARCHAR(64) NOT NULL,
	availability_fixture_id UUID,
	design_scope_id UUID,
	policy_snapshot JSONB NOT NULL,
	source_snapshot JSONB NOT NULL,
	eligibility_decision VARCHAR(16) NOT NULL,
	eligibility_rules JSONB NOT NULL,
	unknown_costs JSONB NOT NULL,
	assumptions JSONB NOT NULL,
	subtotal NUMERIC(28, 8),
	total NUMERIC(28, 8),
	created_by UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT fk_estimate_request FOREIGN KEY(request_id, customer_id, stage_kind) REFERENCES service_requests (id, customer_id, stage_kind) ON DELETE RESTRICT,
	CONSTRAINT uq_pricing_estimate_number UNIQUE (request_id, number),
	CONSTRAINT uq_pricing_estimate_lineage UNIQUE (id, request_id, customer_id),
	CONSTRAINT ck_estimate_nonbinding CHECK (kind='test_estimate' AND mode='simulation' AND NOT binding_authorized),
	CONSTRAINT ck_estimate_currency_category CHECK ((stage_kind='printing' AND currency_code='MMK' AND payment_category='physical_goods') OR (stage_kind='design' AND currency_code='XTR' AND payment_category='digital_goods')),
	CONSTRAINT ck_estimate_bounds CHECK (number>0 AND request_revision>0 AND expires_at>created_at),
	CONSTRAINT ck_estimate_hashes CHECK (spec_sha256 ~ '^[0-9a-f]{64}$' AND source_sha256 ~ '^[0-9a-f]{64}$' AND policy_checksum ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_estimate_eligibility CHECK (eligibility_decision IN ('pass','review','error')),
	CONSTRAINT ck_estimate_money CHECK ((total IS NULL AND subtotal IS NULL) OR (total IS NOT NULL AND subtotal IS NOT NULL AND total>=0 AND total<=1000000000000000 AND subtotal>=0 AND (currency_code!='XTR' OR total=trunc(total)))),
	FOREIGN KEY(pricing_policy_id) REFERENCES pricing_policies (id) ON DELETE RESTRICT,
	FOREIGN KEY(availability_fixture_id) REFERENCES pricing_availability_fixtures (id) ON DELETE RESTRICT,
	FOREIGN KEY(design_scope_id) REFERENCES design_scopes (id) ON DELETE RESTRICT,
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT
)""")
    op.execute(
        """CREATE INDEX ix_pricing_estimate_request ON pricing_estimates (request_id, number)"""
    )
    op.execute("""CREATE TABLE pricing_estimate_lines (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	estimate_id UUID NOT NULL,
	request_id UUID NOT NULL,
	customer_id UUID NOT NULL,
	request_item_id UUID,
	item_kind VARCHAR(24) NOT NULL,
	position INTEGER NOT NULL,
	component_code VARCHAR(80) NOT NULL,
	quantity NUMERIC(28, 8),
	rate NUMERIC(28, 8),
	amount NUMERIC(28, 8),
	assumption VARCHAR(100),
	PRIMARY KEY (id),
	CONSTRAINT fk_pricing_line_estimate FOREIGN KEY(estimate_id, request_id, customer_id) REFERENCES pricing_estimates (id, request_id, customer_id) ON DELETE RESTRICT,
	CONSTRAINT fk_pricing_line_item FOREIGN KEY(request_item_id, request_id, customer_id) REFERENCES request_items (id, request_id, customer_id) ON DELETE RESTRICT,
	CONSTRAINT ck_pricing_line_kind CHECK ((item_kind='design_service' AND request_item_id IS NULL) OR item_kind='print_item'),
	CONSTRAINT ck_pricing_line_money CHECK (amount IS NULL OR (component_code='rounding_adjustment' OR amount>=0)),
	CONSTRAINT ck_pricing_line_parameters CHECK ((quantity IS NULL OR quantity>=0) AND (rate IS NULL OR rate>=0) AND position>0),
	CONSTRAINT uq_pricing_line_position UNIQUE (estimate_id, position)
)""")
    op.execute(
        """ALTER TABLE request_items ADD COLUMN required_by date, ADD COLUMN safety_critical boolean, ADD COLUMN unusual_tolerance boolean, ADD COLUMN requirements_confirmed boolean NOT NULL DEFAULT false"""
    )
    op.execute(
        """ALTER TABLE audit_logs ALTER COLUMN entity_id DROP NOT NULL, ADD COLUMN entity_kind varchar(24) NOT NULL DEFAULT 'request', ADD COLUMN pricing_policy_id uuid REFERENCES pricing_policies(id) ON DELETE RESTRICT, ADD COLUMN availability_fixture_id uuid REFERENCES pricing_availability_fixtures(id) ON DELETE RESTRICT"""
    )
    op.execute(
        """ALTER TABLE audit_logs ADD CONSTRAINT ck_audit_target CHECK ((entity_kind='request' AND entity_id IS NOT NULL AND pricing_policy_id IS NULL AND availability_fixture_id IS NULL) OR (entity_kind='pricing_policy' AND entity_id IS NULL AND pricing_policy_id IS NOT NULL AND availability_fixture_id IS NULL) OR (entity_kind='pricing_fixture' AND entity_id IS NULL AND pricing_policy_id IS NULL AND availability_fixture_id IS NOT NULL))"""
    )
    op.execute("""CREATE FUNCTION m07_frozen() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Immutable simulation pricing history' USING ERRCODE='23514'; END $$""")
    op.execute(
        """CREATE TRIGGER pricing_estimates_frozen BEFORE UPDATE OR DELETE ON pricing_estimates FOR EACH ROW EXECUTE FUNCTION m07_frozen()"""
    )
    op.execute(
        """CREATE TRIGGER pricing_estimate_lines_frozen BEFORE UPDATE OR DELETE ON pricing_estimate_lines FOR EACH ROW EXECUTE FUNCTION m07_frozen()"""
    )
    op.execute("""CREATE FUNCTION m07_configuration_frozen() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN IF TG_OP='DELETE' OR (to_jsonb(NEW)-'active') IS DISTINCT FROM (to_jsonb(OLD)-'active')
THEN RAISE EXCEPTION 'Publish a new simulation configuration version' USING ERRCODE='23514'; END IF;
RETURN NEW; END $$""")
    op.execute(
        """CREATE TRIGGER pricing_policies_frozen BEFORE UPDATE OR DELETE ON pricing_policies FOR EACH ROW EXECUTE FUNCTION m07_configuration_frozen()"""
    )
    op.execute(
        """CREATE TRIGGER pricing_availability_fixtures_frozen BEFORE UPDATE OR DELETE ON pricing_availability_fixtures FOR EACH ROW EXECUTE FUNCTION m07_configuration_frozen()"""
    )
    op.execute("""CREATE FUNCTION m07_owner_configuration() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN IF NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.created_by AND role='owner' AND active)
OR (NEW.configuration->>'simulation_only') IS DISTINCT FROM 'true'
THEN RAISE EXCEPTION 'Owner simulation configuration required' USING ERRCODE='23514'; END IF;
RETURN NEW; END $$""")
    op.execute(
        """CREATE TRIGGER pricing_policies_owner BEFORE INSERT ON pricing_policies FOR EACH ROW EXECUTE FUNCTION m07_owner_configuration()"""
    )
    op.execute(
        """CREATE TRIGGER pricing_availability_fixtures_owner BEFORE INSERT ON pricing_availability_fixtures FOR EACH ROW EXECUTE FUNCTION m07_owner_configuration()"""
    )
    op.execute("""CREATE FUNCTION m07_estimate_provenance() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r service_requests; p pricing_policies; source jsonb; run slicing_runs; analysis model_analyses;
        task processing_tasks; file uploaded_files; scope design_scopes; project design_projects;
BEGIN
 SELECT * INTO r FROM service_requests WHERE id=NEW.request_id FOR UPDATE;
 SELECT * INTO p FROM pricing_policies WHERE id=NEW.pricing_policy_id;
 IF r.mode!='simulation' OR r.status NOT IN ('submitted','analyzing','manual_review') OR r.customer_id!=NEW.customer_id
 OR r.stage_kind!=NEW.stage_kind OR r.revision!=NEW.request_revision OR r.canonical_spec_sha256!=NEW.spec_sha256
 OR NOT p.active OR p.stage_kind!=NEW.stage_kind OR p.currency_code!=NEW.currency_code
 OR p.checksum!=NEW.policy_checksum OR NEW.policy_snapshot IS DISTINCT FROM p.configuration
 OR (NEW.eligibility_decision='pass' AND (r.service_type!='printing' OR NEW.total IS NULL
 OR jsonb_array_length(NEW.unknown_costs)>0 OR jsonb_array_length(NEW.eligibility_rules)=0
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(NEW.eligibility_rules) x WHERE x->>'result' IS DISTINCT FROM 'pass')))
 THEN RAISE EXCEPTION 'Invalid pricing provenance' USING ERRCODE='23514'; END IF;
 IF NEW.stage_kind='printing' THEN
  IF NEW.design_scope_id IS NOT NULL OR jsonb_typeof(NEW.source_snapshot->'items') IS DISTINCT FROM 'array'
  OR jsonb_array_length(NEW.source_snapshot->'items') != (SELECT count(*) FROM request_items WHERE request_id=r.id AND active)
  OR jsonb_array_length(NEW.source_snapshot->'items') != (SELECT count(DISTINCT x->>'item_id') FROM jsonb_array_elements(NEW.source_snapshot->'items') x)
  THEN RAISE EXCEPTION 'Invalid print pricing items' USING ERRCODE='23514'; END IF;
  FOR source IN SELECT * FROM jsonb_array_elements(NEW.source_snapshot->'items') LOOP
   IF NOT EXISTS(SELECT 1 FROM request_items WHERE id=(source->>'item_id')::uuid AND request_id=r.id AND active)
   THEN RAISE EXCEPTION 'Wrong pricing item' USING ERRCODE='23514'; END IF;
   IF source->>'run_id' IS NOT NULL THEN
    SELECT * INTO run FROM slicing_runs WHERE id=(source->>'run_id')::uuid;
    SELECT * INTO analysis FROM model_analyses WHERE id=run.model_analysis_id;
    SELECT * INTO task FROM processing_tasks WHERE id=run.task_id;
    SELECT * INTO file FROM uploaded_files WHERE id=analysis.uploaded_file_id;
    IF run.id IS NULL OR task.state!='succeeded' OR task.result_run_id IS DISTINCT FROM run.id
    OR analysis.request_id IS DISTINCT FROM r.id OR analysis.customer_id IS DISTINCT FROM r.customer_id
    OR analysis.request_revision!=r.revision OR analysis.spec_sha256!=r.canonical_spec_sha256
    OR analysis.id IS DISTINCT FROM (source->>'analysis_id')::uuid
    OR analysis.request_item_id IS DISTINCT FROM (source->>'item_id')::uuid
    OR analysis.input_sha256 IS DISTINCT FROM file.sha256 OR file.storage_state!='ready' OR file.validation_status!='validated'
    THEN RAISE EXCEPTION 'Stale pricing analysis' USING ERRCODE='23514'; END IF;
   ELSIF NEW.total IS NOT NULL OR NEW.eligibility_decision='pass' THEN
    RAISE EXCEPTION 'Missing pricing analysis' USING ERRCODE='23514';
   END IF;
  END LOOP;
 ELSE
  SELECT * INTO scope FROM design_scopes WHERE id=NEW.design_scope_id;
  SELECT * INTO project FROM design_projects WHERE id=scope.design_project_id;
  IF NEW.design_scope_id IS NULL OR project.request_id IS DISTINCT FROM r.id
  OR scope.number != (SELECT max(number) FROM design_scopes WHERE design_project_id=project.id)
  OR NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.created_by AND role='owner' AND active)
  OR NEW.source_snapshot->'scope'->'specification' IS DISTINCT FROM scope.specification
  THEN RAISE EXCEPTION 'Wrong design pricing scope' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$""")
    op.execute(
        """CREATE TRIGGER pricing_estimate_provenance BEFORE INSERT ON pricing_estimates FOR EACH ROW EXECUTE FUNCTION m07_estimate_provenance()"""
    )
    op.execute("""CREATE FUNCTION m07_line_provenance() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE estimate pricing_estimates; created_xid xid;
BEGIN SELECT * INTO estimate FROM pricing_estimates WHERE id=NEW.estimate_id;
 SELECT xmin INTO created_xid FROM pricing_estimates WHERE id=NEW.estimate_id;
 IF age(created_xid) != 0 THEN
  RAISE EXCEPTION 'Immutable pricing cost set' USING ERRCODE='23514'; END IF;
 IF (estimate.stage_kind='design' AND (NEW.item_kind!='design_service' OR NEW.request_item_id IS NOT NULL))
 OR (estimate.stage_kind='printing' AND NEW.item_kind!='print_item')
 THEN RAISE EXCEPTION 'Wrong pricing cost line stage' USING ERRCODE='23514'; END IF;
 RETURN NEW; END $$""")
    op.execute(
        """CREATE TRIGGER pricing_line_provenance BEFORE INSERT ON pricing_estimate_lines FOR EACH ROW EXECUTE FUNCTION m07_line_provenance()"""
    )

    op.execute("""CREATE FUNCTION m07_estimate_balance() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE estimate pricing_estimates; target uuid; total_lines numeric;
    BEGIN
      IF TG_TABLE_NAME='pricing_estimates' THEN target:=NEW.id; ELSE target:=NEW.estimate_id; END IF;
      SELECT * INTO estimate FROM pricing_estimates WHERE id=target;
      IF estimate.total IS NOT NULL THEN
        IF EXISTS(SELECT 1 FROM pricing_estimate_lines WHERE estimate_id=target AND amount IS NULL)
        THEN RAISE EXCEPTION 'Unknown cost cannot have a complete price' USING ERRCODE='23514'; END IF;
        SELECT sum(amount) INTO total_lines FROM pricing_estimate_lines WHERE estimate_id=target;
        IF total_lines IS DISTINCT FROM estimate.total THEN
          RAISE EXCEPTION 'Cost lines do not balance to the estimate' USING ERRCODE='23514';
        END IF;
      END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE CONSTRAINT TRIGGER pricing_estimate_balance AFTER INSERT ON pricing_estimates DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION m07_estimate_balance()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER pricing_line_balance AFTER INSERT ON pricing_estimate_lines DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION m07_estimate_balance()"
    )


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN IF EXISTS(SELECT 1 FROM pricing_policies) OR EXISTS(SELECT 1 FROM pricing_availability_fixtures) OR EXISTS(SELECT 1 FROM pricing_estimates) OR EXISTS(SELECT 1 FROM audit_logs WHERE entity_kind!='request') OR EXISTS(SELECT 1 FROM request_items WHERE required_by IS NOT NULL OR safety_critical IS NOT NULL OR unusual_tolerance IS NOT NULL OR requirements_confirmed) THEN RAISE EXCEPTION 'Refusing to remove retained M07 history'; END IF; END $$"""
    )
    op.execute(
        "ALTER TABLE audit_logs DROP CONSTRAINT ck_audit_target, DROP COLUMN pricing_policy_id, DROP COLUMN availability_fixture_id, DROP COLUMN entity_kind, ALTER COLUMN entity_id SET NOT NULL"
    )
    op.execute(
        "DROP TABLE pricing_estimate_lines, pricing_estimates, pricing_availability_fixtures, pricing_policies"
    )
    op.execute(
        "DROP FUNCTION m07_estimate_balance(), m07_line_provenance(), m07_estimate_provenance(), m07_owner_configuration(), m07_configuration_frozen(), m07_frozen()"
    )
    op.execute(
        "ALTER TABLE request_items DROP COLUMN required_by, DROP COLUMN safety_critical, DROP COLUMN unusual_tolerance, DROP COLUMN requirements_confirmed"
    )
