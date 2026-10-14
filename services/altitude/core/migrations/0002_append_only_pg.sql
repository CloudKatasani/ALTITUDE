-- PostgreSQL-only: enforce append-only semantics at the database layer.
-- (The DuckDB dev store enforces the same rule in altitude.core.store.)
-- @dialect: postgres
CREATE OR REPLACE FUNCTION altitude_reject_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'append-only table %: % is not permitted', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER snapshot_append_only BEFORE UPDATE OR DELETE ON snapshot
  FOR EACH ROW EXECUTE FUNCTION altitude_reject_mutation();
CREATE TRIGGER audit_event_append_only BEFORE UPDATE OR DELETE ON audit_event
  FOR EACH ROW EXECUTE FUNCTION altitude_reject_mutation();
CREATE TRIGGER agent_action_append_only BEFORE UPDATE OR DELETE ON agent_action
  FOR EACH ROW EXECUTE FUNCTION altitude_reject_mutation();
CREATE TRIGGER validation_run_append_only BEFORE UPDATE OR DELETE ON validation_run
  FOR EACH ROW EXECUTE FUNCTION altitude_reject_mutation();
CREATE TRIGGER gate_append_only BEFORE UPDATE OR DELETE ON gate
  FOR EACH ROW EXECUTE FUNCTION altitude_reject_mutation();
CREATE TRIGGER approval_append_only BEFORE UPDATE OR DELETE ON approval
  FOR EACH ROW EXECUTE FUNCTION altitude_reject_mutation();

ALTER TABLE tenant ENABLE ROW LEVEL SECURITY;
ALTER TABLE engagement ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_engagement ON engagement
  USING (tenant_id = current_setting('altitude.tenant_id'));
