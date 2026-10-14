-- PostgreSQL-only: factory transitions are append-only (DuckDB store enforces via register_append_only).
-- @dialect: postgres
CREATE TRIGGER factory_transition_append_only BEFORE UPDATE OR DELETE ON factory_transition
  FOR EACH ROW EXECUTE FUNCTION altitude_reject_mutation();
