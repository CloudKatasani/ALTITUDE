-- PostgreSQL-only: factory transitions are append-only (DuckDB store enforces via register_append_only).
-- @dialect: postgres
CREATE TRIGGER conversion_lane_transition_append_only BEFORE UPDATE OR DELETE ON conversion_lane_transition
  FOR EACH ROW EXECUTE FUNCTION altitude_reject_mutation();
