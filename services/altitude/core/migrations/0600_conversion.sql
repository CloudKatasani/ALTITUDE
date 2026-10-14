-- M5 Conversion orchestrator: detail tables that extend the canonical conversion entities
-- (conversion_run, converted_artifact, conversion_issue, ai_change, review) without altering them.

-- Factory state machine (Section 9.2): every transition records actor, timestamp, evidence and confidence.
-- Append-only (registered in altitude.conversion and guarded by trigger in 0601 on PostgreSQL).
CREATE TABLE factory_transition (
  transition_id    VARCHAR PRIMARY KEY,
  engagement_id    VARCHAR NOT NULL,
  object_id        VARCHAR NOT NULL,
  artifact_id      VARCHAR,
  lane             VARCHAR NOT NULL,      -- schema|code|etl|data|validation|bi|security|ops
  seq              INTEGER NOT NULL,      -- 0-based position in the object's lane history
  from_state       VARCHAR,
  to_state         VARCHAR NOT NULL,
  actor            VARCHAR NOT NULL,
  actor_type       VARCHAR NOT NULL,      -- human|agent|system
  evidence_ref     VARCHAR NOT NULL,
  confidence       NUMERIC(4,3) NOT NULL,
  occurred_at      TIMESTAMP NOT NULL
);

-- Tool-level detail for each conversion_issue (EWI/FDM/PRF code family, source location, snippet).
CREATE TABLE conversion_issue_detail (
  issue_id         VARCHAR PRIMARY KEY,
  run_id           VARCHAR NOT NULL,
  category         VARCHAR NOT NULL,      -- EWI|FDM|PRF|OOS
  tool_severity    VARCHAR,
  source_file      VARCHAR,
  source_line      INTEGER,
  source_column    INTEGER,
  snippet          TEXT,
  region_end_line  INTEGER,               -- last converted-output line of the annotated statement
  known_issue_id   VARCHAR,
  detector_id      VARCHAR
);

-- Content of each artifact version: converted (tool output), remediated (all AI changes), promoted.
CREATE TABLE artifact_content (
  artifact_id      VARCHAR NOT NULL,
  kind             VARCHAR NOT NULL,      -- converted|remediated|promoted
  content_hash     VARCHAR NOT NULL,
  content          TEXT NOT NULL,
  created_at       TIMESTAMP NOT NULL,
  PRIMARY KEY (artifact_id, kind)
);

-- The patch behind each ai_change, so promotion re-applies only approved changes.
CREATE TABLE ai_change_patch (
  change_id        VARCHAR PRIMARY KEY,
  artifact_id      VARCHAR NOT NULL,
  rule_ids         VARCHAR[],
  line_start       INTEGER NOT NULL,
  line_end         INTEGER NOT NULL,
  before_text      TEXT NOT NULL,
  after_text       TEXT NOT NULL,
  final_text       TEXT,                  -- reviewer-modified text (decision = modified)
  below_floor      BOOLEAN NOT NULL,
  inference_id     VARCHAR NOT NULL
);

-- PR packs: remediation lands as a reviewable directory, never in production.
CREATE TABLE pr_pack (
  pack_id          VARCHAR PRIMARY KEY,
  artifact_id      VARCHAR NOT NULL,
  run_id           VARCHAR NOT NULL,
  path             VARCHAR NOT NULL,
  manifest_hash    VARCHAR NOT NULL,
  tests_total      INTEGER,
  tests_passed     INTEGER,
  tested_at        TIMESTAMP,
  created_at       TIMESTAMP NOT NULL
);

-- SnowConvert assessment (TopLevelCodeUnits) per run.
CREATE TABLE conversion_assessment (
  run_id           VARCHAR NOT NULL,
  code_unit_id     VARCHAR NOT NULL,
  file_name        VARCHAR,
  category         VARCHAR,
  code_unit        VARCHAR,
  lines_of_code    INTEGER,
  ewi_count        INTEGER,
  fdm_count        INTEGER,
  prf_count        INTEGER,
  highest_ewi_severity VARCHAR,
  conversion_status VARCHAR,
  PRIMARY KEY (run_id, code_unit_id)
);
