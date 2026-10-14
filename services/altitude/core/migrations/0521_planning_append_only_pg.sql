-- PostgreSQL-only: factory transitions are append-only (the DuckDB store enforces the
-- same rule via altitude.planning registering the table with register_append_only).
-- @dialect: postgres
CREATE TRIGGER factory_transition_append_only BEFORE UPDATE OR DELETE ON factory_transition
  FOR EACH ROW EXECUTE FUNCTION altitude_reject_mutation();
