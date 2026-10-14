-- PostgreSQL-only: agent run logs and tool calls are immutable (the DuckDB store enforces the same rule).
-- @dialect: postgres
CREATE TRIGGER agent_run_log_append_only BEFORE UPDATE OR DELETE ON agent_run_log
  FOR EACH ROW EXECUTE FUNCTION altitude_reject_mutation();
CREATE TRIGGER agent_tool_call_append_only BEFORE UPDATE OR DELETE ON agent_tool_call
  FOR EACH ROW EXECUTE FUNCTION altitude_reject_mutation();
CREATE TRIGGER agent_eval_result_append_only BEFORE UPDATE OR DELETE ON agent_eval_result
  FOR EACH ROW EXECUTE FUNCTION altitude_reject_mutation();
