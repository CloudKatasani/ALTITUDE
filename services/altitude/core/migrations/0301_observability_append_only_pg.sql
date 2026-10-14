-- PostgreSQL-only: suggestion status transitions and value measurements are append-only.
-- (The DuckDB dev store enforces the same rule through altitude.core.store.register_append_only.)
-- @dialect: postgres
CREATE TRIGGER obs_suggestion_status_append_only BEFORE UPDATE OR DELETE ON obs_suggestion_status
  FOR EACH ROW EXECUTE FUNCTION altitude_reject_mutation();
CREATE TRIGGER obs_value_measurement_append_only BEFORE UPDATE OR DELETE ON obs_value_measurement
  FOR EACH ROW EXECUTE FUNCTION altitude_reject_mutation();
