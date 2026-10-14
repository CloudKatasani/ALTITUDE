-- M9 ETL & scheduler converters.

-- One row per parsed ETL job (SSIS data flow / Informatica mapping) with its classification.
CREATE TABLE etl_job (
  job_id           VARCHAR PRIMARY KEY,
  engagement_id    VARCHAR NOT NULL,
  tool             VARCHAR NOT NULL,      -- ssis|informatica
  source_file      VARCHAR NOT NULL,
  name             VARCHAR NOT NULL,
  classification   VARCHAR NOT NULL,      -- passthrough|transform|complex
  recommendation   VARCHAR NOT NULL,      -- retire|lift|re-engineer
  complexity_score NUMERIC(8,2) NOT NULL,
  confidence       NUMERIC(4,3) NOT NULL,
  rationale        TEXT NOT NULL,
  graph_hash       VARCHAR NOT NULL,
  issues           JSONB,
  rubric_version   VARCHAR NOT NULL,
  created_at       TIMESTAMP NOT NULL
);

-- One row per converted scheduler definition (Control-M folder / SQL Agent export).
CREATE TABLE scheduler_dag (
  dag_id           VARCHAR PRIMARY KEY,
  engagement_id    VARCHAR NOT NULL,
  tool             VARCHAR NOT NULL,      -- controlm|sqlagent
  source_file      VARCHAR NOT NULL,
  job_count        INTEGER NOT NULL,
  edge_count       INTEGER NOT NULL,
  task_sql_hash    VARCHAR NOT NULL,
  airflow_hash     VARCHAR NOT NULL,
  issues           JSONB,
  created_at       TIMESTAMP NOT NULL
);
