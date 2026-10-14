-- PostgreSQL-only: diagnostics evidence and lifecycle events are append-only.
-- (The DuckDB dev store enforces the same rule via altitude.core.store.register_append_only.)
-- @dialect: postgres
CREATE TRIGGER diag_evidence_append_only BEFORE UPDATE OR DELETE ON diag_evidence
  FOR EACH ROW EXECUTE FUNCTION altitude_reject_mutation();
CREATE TRIGGER diag_suggestion_event_append_only BEFORE UPDATE OR DELETE ON diag_suggestion_event
  FOR EACH ROW EXECUTE FUNCTION altitude_reject_mutation();
