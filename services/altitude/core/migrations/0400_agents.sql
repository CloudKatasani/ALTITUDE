-- M10 agent fleet: run logs, tool calls and eval results (complements the Run entities in 0001).
-- PostgreSQL 16 dialect; transpiled to DuckDB for the local store.
-- agent_run_log and agent_tool_call are append-only (registered by altitude_agents.runtime and guarded by
-- triggers in 0401_agents_append_only_pg.sql on PostgreSQL).

CREATE TABLE agent_run_log (
  run_id           VARCHAR PRIMARY KEY,
  agent_id         VARCHAR NOT NULL,
  tenant_id        VARCHAR NOT NULL,
  snapshot_ref     VARCHAR,               -- sealed snapshot id / telemetry content hash
  rubric_version   VARCHAR NOT NULL,
  inputs           JSONB NOT NULL,
  output           JSONB NOT NULL,        -- findings, recommendations, decisions
  decision_summary TEXT NOT NULL,
  recorded_at      TIMESTAMP NOT NULL
);

CREATE TABLE agent_tool_call (
  run_id           VARCHAR NOT NULL,
  seq              INTEGER NOT NULL,
  tool             VARCHAR NOT NULL,
  arguments        JSONB NOT NULL,
  tables_read      VARCHAR[] NOT NULL,
  rows_returned    INTEGER NOT NULL,
  result_hash      VARCHAR NOT NULL,
  called_at        TIMESTAMP NOT NULL,
  PRIMARY KEY (run_id, seq)
);

CREATE TABLE agent_eval_result (
  agent_id         VARCHAR NOT NULL,
  version          VARCHAR NOT NULL,
  case_id          VARCHAR NOT NULL,
  passed           BOOLEAN NOT NULL,
  details          JSONB NOT NULL,
  evaluated_at     TIMESTAMP NOT NULL,
  PRIMARY KEY (agent_id, version, case_id, evaluated_at)
);
