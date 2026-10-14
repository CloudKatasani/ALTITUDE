-- ALTITUDE canonical data model (Section 30). PostgreSQL 16 dialect.
-- The local/dev store transpiles this file to DuckDB with sqlglot, so keep it
-- to portable DDL. Append-only tables are listed in APPEND_ONLY (store.py) and
-- guarded by triggers in 0002_append_only_pg.sql on PostgreSQL.

-- ---------------------------------------------------------------- Engagement
CREATE TABLE tenant (
  tenant_id        VARCHAR PRIMARY KEY,
  name             VARCHAR NOT NULL,
  theme            VARCHAR NOT NULL DEFAULT 'default',
  llm_policy       JSONB,
  created_at       TIMESTAMP NOT NULL
);

CREATE TABLE client (
  client_id        VARCHAR PRIMARY KEY,
  tenant_id        VARCHAR NOT NULL,
  name             VARCHAR NOT NULL,
  industry         VARCHAR,
  spend_band       VARCHAR,
  created_at       TIMESTAMP NOT NULL
);

CREATE TABLE engagement (
  engagement_id    VARCHAR PRIMARY KEY,
  tenant_id        VARCHAR NOT NULL,
  client_id        VARCHAR NOT NULL,
  package          VARCHAR NOT NULL,   -- D0|D1|D2|D3|O1|O2|O3|migration|foundation|ai_ready
  name             VARCHAR NOT NULL,
  current_phase    VARCHAR,
  status           VARCHAR NOT NULL DEFAULT 'active',
  created_at       TIMESTAMP NOT NULL
);

CREATE TABLE phase (
  phase_id         VARCHAR PRIMARY KEY,
  engagement_id    VARCHAR NOT NULL,
  name             VARCHAR NOT NULL,
  ordinal          INTEGER NOT NULL,
  status           VARCHAR NOT NULL,
  started_at       TIMESTAMP,
  ended_at         TIMESTAMP
);

CREATE TABLE gate (
  gate_id          VARCHAR PRIMARY KEY,
  engagement_id    VARCHAR NOT NULL,
  gate_key         VARCHAR NOT NULL,   -- e.g. assess_exit (knowledge/rubrics/gates)
  snapshot_id      VARCHAR NOT NULL,
  rubric_version   VARCHAR NOT NULL,
  result           VARCHAR NOT NULL,   -- pass|fail
  details          JSONB NOT NULL,
  decided_by       VARCHAR,
  decided_at       TIMESTAMP NOT NULL
);

CREATE TABLE decision (
  decision_id      VARCHAR PRIMARY KEY,   -- ADR
  engagement_id    VARCHAR NOT NULL,
  title            VARCHAR NOT NULL,
  context          TEXT,
  recommendation   TEXT,
  perspectives     JSONB,              -- review-board lenses with votes
  dissent          JSONB,
  evidence_refs    VARCHAR[],
  status           VARCHAR NOT NULL,   -- proposed|accepted|rejected|superseded
  decided_by       VARCHAR,
  decided_at       TIMESTAMP
);

CREATE TABLE raid_item (
  raid_id          VARCHAR PRIMARY KEY,
  engagement_id    VARCHAR NOT NULL,
  kind             VARCHAR NOT NULL,   -- risk|assumption|issue|dependency
  title            VARCHAR NOT NULL,
  severity         VARCHAR,
  owner            VARCHAR,
  status           VARCHAR NOT NULL,
  created_at       TIMESTAMP NOT NULL
);

-- ---------------------------------------------------------------- Estate
CREATE TABLE source_system (
  source_system_id VARCHAR PRIMARY KEY,
  engagement_id    VARCHAR NOT NULL,
  dialect          VARCHAR NOT NULL,   -- teradata|oracle|sqlserver|snowflake|...
  name             VARCHAR NOT NULL,
  version          VARCHAR,
  permission_manifest JSONB
);

CREATE TABLE source_object (
  object_id        VARCHAR PRIMARY KEY,
  engagement_id    VARCHAR NOT NULL,
  source_system_id VARCHAR NOT NULL,
  object_type      VARCHAR NOT NULL,   -- table|view|procedure|function|macro|script|etl_job|schedule|report
  fq_name          VARCHAR NOT NULL,
  code_hash        VARCHAR,
  loc              INTEGER,
  last_used_at     TIMESTAMP,
  usage_90d        INTEGER,
  disposition      VARCHAR,            -- keep|retire|rewrite (AI-proposed, human-confirmed)
  disposition_conf NUMERIC(4,3),
  disposition_rationale VARCHAR,
  tier             VARCHAR,            -- tier1|tier2|tier3
  complexity_score NUMERIC(5,2),
  harvested_at     TIMESTAMP NOT NULL
);

CREATE TABLE object_version (
  object_id        VARCHAR NOT NULL,
  code_hash        VARCHAR NOT NULL,
  source_text      TEXT,
  harvested_at     TIMESTAMP NOT NULL,
  PRIMARY KEY (object_id, code_hash)
);

CREATE TABLE "column" (
  object_id        VARCHAR NOT NULL,
  column_name      VARCHAR NOT NULL,
  ordinal          INTEGER NOT NULL,
  data_type        VARCHAR NOT NULL,
  nullable         BOOLEAN,
  attributes       JSONB,              -- e.g. {"casespecific": false, "char_padded": true}
  sensitivity_tag  VARCHAR,
  PRIMARY KEY (object_id, column_name)
);

CREATE TABLE dependency_edge (
  from_object_id   VARCHAR NOT NULL,   -- consumer
  to_object_id     VARCHAR NOT NULL,   -- producer / referenced
  kind             VARCHAR NOT NULL,   -- reads|writes|calls|schedules
  evidence         VARCHAR,
  PRIMARY KEY (from_object_id, to_object_id, kind)
);

CREATE TABLE usage_stat (
  object_id        VARCHAR NOT NULL,
  period_start     DATE NOT NULL,
  period_end       DATE NOT NULL,
  query_count      INTEGER NOT NULL,
  distinct_users   INTEGER,
  PRIMARY KEY (object_id, period_start)
);

CREATE TABLE "grant" (
  grant_id         VARCHAR PRIMARY KEY,
  source_system_id VARCHAR NOT NULL,
  grantee          VARCHAR NOT NULL,
  grantee_type     VARCHAR NOT NULL,   -- user|role
  privilege        VARCHAR NOT NULL,
  object_fq_name   VARCHAR,
  mapped_to        VARCHAR,            -- target role / intentionally_retired
  mapping_status   VARCHAR
);

-- ---------------------------------------------------------------- Classification
CREATE TABLE object_disposition (
  object_id        VARCHAR NOT NULL,
  snapshot_id      VARCHAR NOT NULL,
  disposition      VARCHAR NOT NULL,
  confidence       NUMERIC(4,3) NOT NULL,
  rationale        TEXT NOT NULL,
  proposed_by      VARCHAR NOT NULL,   -- agent or human id
  confirmed_by     VARCHAR,
  PRIMARY KEY (object_id, snapshot_id)
);

CREATE TABLE complexity_score (
  object_id        VARCHAR NOT NULL,
  snapshot_id      VARCHAR NOT NULL,
  score            NUMERIC(5,2) NOT NULL,
  band             VARCHAR NOT NULL,   -- low|med|high
  factors          JSONB NOT NULL,
  rubric_version   VARCHAR NOT NULL,
  PRIMARY KEY (object_id, snapshot_id)
);

CREATE TABLE tier (
  object_id        VARCHAR PRIMARY KEY,
  tier             VARCHAR NOT NULL,
  set_by           VARCHAR NOT NULL,
  set_at           TIMESTAMP NOT NULL
);

CREATE TABLE sensitivity_tag (
  object_id        VARCHAR NOT NULL,
  column_name      VARCHAR NOT NULL,
  tag              VARCHAR NOT NULL,   -- PII|PHI|PCI|CONFIDENTIAL|...
  source           VARCHAR NOT NULL,   -- discovered|propagated|manual
  confidence       NUMERIC(4,3),
  PRIMARY KEY (object_id, column_name, tag)
);

-- ---------------------------------------------------------------- Planning
CREATE TABLE wave (
  wave_id          VARCHAR PRIMARY KEY,
  engagement_id    VARCHAR NOT NULL,
  ordinal          INTEGER NOT NULL,
  name             VARCHAR NOT NULL,
  pattern          VARCHAR NOT NULL,
  start_date       DATE,
  end_date         DATE,
  rationale        TEXT
);

CREATE TABLE wave_object (
  wave_id          VARCHAR NOT NULL,
  object_id        VARCHAR NOT NULL,
  state            VARCHAR NOT NULL,   -- factory state machine (Section 9.2)
  PRIMARY KEY (wave_id, object_id)
);

CREATE TABLE pattern_recommendation (
  recommendation_id VARCHAR PRIMARY KEY,
  engagement_id    VARCHAR NOT NULL,
  scope            VARCHAR NOT NULL,   -- programme|wave id
  pattern          VARCHAR NOT NULL,
  confidence       NUMERIC(4,3) NOT NULL,
  rationale        TEXT NOT NULL,
  dissent          JSONB,
  rubric_version   VARCHAR NOT NULL,
  snapshot_id      VARCHAR NOT NULL
);

CREATE TABLE estimate (
  estimate_id      VARCHAR PRIMARY KEY,
  engagement_id    VARCHAR NOT NULL,
  scope            VARCHAR NOT NULL,
  snapshot_id      VARCHAR NOT NULL,
  rubric_version   VARCHAR NOT NULL,
  p50_hours        NUMERIC(12,2) NOT NULL,
  p80_hours        NUMERIC(12,2) NOT NULL,
  confidence       NUMERIC(4,3) NOT NULL,
  rationale        TEXT NOT NULL,
  created_at       TIMESTAMP NOT NULL
);

CREATE TABLE estimate_factor (
  estimate_id      VARCHAR NOT NULL,
  factor           VARCHAR NOT NULL,
  quantity         NUMERIC(14,4) NOT NULL,
  unit_hours       NUMERIC(10,4) NOT NULL,
  hours            NUMERIC(12,2) NOT NULL,
  PRIMARY KEY (estimate_id, factor)
);

-- ---------------------------------------------------------------- Conversion
CREATE TABLE conversion_run (
  run_id           VARCHAR PRIMARY KEY,
  engagement_id    VARCHAR NOT NULL,
  tool             VARCHAR NOT NULL,   -- snowconvert|sqlglot|...
  tool_version     VARCHAR,
  started_at       TIMESTAMP NOT NULL,
  completed_at     TIMESTAMP,
  status           VARCHAR NOT NULL
);

CREATE TABLE converted_artifact (
  artifact_id      VARCHAR PRIMARY KEY,
  run_id           VARCHAR NOT NULL,
  object_id        VARCHAR NOT NULL,
  object_code_hash VARCHAR NOT NULL,   -- source_object version
  target_path      VARCHAR NOT NULL,
  content_hash     VARCHAR NOT NULL,
  status           VARCHAR NOT NULL,   -- converted|remediated|reviewed|promoted|rejected
  promoted_by      VARCHAR,
  promoted_at      TIMESTAMP
);

CREATE TABLE conversion_issue (
  issue_id         VARCHAR PRIMARY KEY,
  artifact_id      VARCHAR NOT NULL,
  code             VARCHAR NOT NULL,   -- EWI/FDM code or known-issue id
  severity         VARCHAR NOT NULL,   -- P1..P4 or S1..S4
  message          TEXT NOT NULL,
  line             INTEGER,
  status           VARCHAR NOT NULL    -- open|fixed|accepted
);

CREATE TABLE ai_change (
  change_id        VARCHAR PRIMARY KEY,
  artifact_id      VARCHAR NOT NULL,
  agent_id         VARCHAR NOT NULL,
  model_id         VARCHAR NOT NULL,
  prompt_template  VARCHAR NOT NULL,      -- id@version
  diff             TEXT NOT NULL,
  confidence       NUMERIC(4,3) NOT NULL,
  rationale        TEXT NOT NULL,
  linked_issue_ids VARCHAR[],
  tests_generated  VARCHAR[],
  reviewer         VARCHAR,               -- required before promotion
  decision         VARCHAR,               -- approved|rejected|modified
  decided_at       TIMESTAMP
);

CREATE TABLE review (
  review_id        VARCHAR PRIMARY KEY,
  subject_type     VARCHAR NOT NULL,      -- artifact|ai_change|suggestion|disposition|...
  subject_id       VARCHAR NOT NULL,
  reviewer         VARCHAR NOT NULL,
  decision         VARCHAR NOT NULL,      -- approved|rejected|modified
  comment          TEXT,
  reviewed_at      TIMESTAMP NOT NULL
);

-- ---------------------------------------------------------------- Movement
CREATE TABLE load_job (
  load_job_id      VARCHAR PRIMARY KEY,
  engagement_id    VARCHAR NOT NULL,
  object_id        VARCHAR NOT NULL,
  method           VARCHAR NOT NULL,      -- copy|snowpipe|cdc|openflow
  status           VARCHAR NOT NULL,
  credits_used     NUMERIC(12,4),
  started_at       TIMESTAMP,
  completed_at     TIMESTAMP
);

CREATE TABLE load_partition (
  load_job_id      VARCHAR NOT NULL,
  partition_key    VARCHAR NOT NULL,
  rows_loaded      BIGINT,
  checkpoint       VARCHAR,
  status           VARCHAR NOT NULL,
  PRIMARY KEY (load_job_id, partition_key)
);

CREATE TABLE cdc_stream (
  stream_id        VARCHAR PRIMARY KEY,
  engagement_id    VARCHAR NOT NULL,
  object_id        VARCHAR NOT NULL,
  tool             VARCHAR NOT NULL,
  lag_seconds      INTEGER,
  status           VARCHAR NOT NULL
);

-- ---------------------------------------------------------------- Validation
CREATE TABLE validation_suite (
  suite_id         VARCHAR PRIMARY KEY,
  engagement_id    VARCHAR NOT NULL,
  object_id        VARCHAR NOT NULL,
  tier             VARCHAR NOT NULL,
  levels           VARCHAR[] NOT NULL,
  generated_at     TIMESTAMP NOT NULL
);

CREATE TABLE validation_check (
  check_id         VARCHAR PRIMARY KEY,
  suite_id         VARCHAR NOT NULL,
  level            VARCHAR NOT NULL,
  definition       JSONB NOT NULL
);

CREATE TABLE validation_run (
  run_id           VARCHAR PRIMARY KEY,
  suite_id         VARCHAR NOT NULL,
  object_id        VARCHAR NOT NULL,
  level            VARCHAR NOT NULL,      -- L0..L5
  normalisation_rule_version VARCHAR NOT NULL,
  threshold_rubric_version   VARCHAR NOT NULL,
  result           VARCHAR NOT NULL,      -- pass|fail|accepted_deviation
  metrics          JSONB NOT NULL,        -- aggregates only; no row data
  mismatch_key_ref VARCHAR,               -- pointer to in-boundary storage
  executed_in      VARCHAR NOT NULL,      -- client_agent|snowflake
  completed_at     TIMESTAMP NOT NULL
);

CREATE TABLE mismatch_cluster (
  cluster_id       VARCHAR PRIMARY KEY,
  run_id           VARCHAR NOT NULL,
  signature        VARCHAR NOT NULL,
  known_issue_id   VARCHAR,
  mismatch_count   INTEGER NOT NULL,
  confidence       NUMERIC(4,3) NOT NULL,
  rationale        TEXT NOT NULL
);

CREATE TABLE accepted_deviation (
  deviation_id     VARCHAR PRIMARY KEY,
  run_id           VARCHAR NOT NULL,
  cluster_id       VARCHAR,
  description      TEXT NOT NULL,
  approver         VARCHAR NOT NULL,      -- data owner
  approved_at      TIMESTAMP NOT NULL,
  review_by        DATE NOT NULL
);

-- ---------------------------------------------------------------- Cutover
CREATE TABLE cutover_plan (
  plan_id          VARCHAR PRIMARY KEY,
  engagement_id    VARCHAR NOT NULL,
  strategy         VARCHAR NOT NULL,      -- big_bang|phased|parallel_run|consumer_by_consumer
  scope            VARCHAR NOT NULL,
  planned_at       TIMESTAMP
);

CREATE TABLE rehearsal (
  rehearsal_id     VARCHAR PRIMARY KEY,
  plan_id          VARCHAR NOT NULL,
  executed_at      TIMESTAMP NOT NULL,
  result           VARCHAR NOT NULL,
  notes            TEXT
);

CREATE TABLE go_no_go (
  go_no_go_id      VARCHAR PRIMARY KEY,
  plan_id          VARCHAR NOT NULL,
  snapshot_id      VARCHAR NOT NULL,
  evidence_pack    JSONB NOT NULL,
  recommendation   VARCHAR NOT NULL,
  decision         VARCHAR,
  decided_by       VARCHAR,
  decided_at       TIMESTAMP
);

CREATE TABLE rollback_plan (
  rollback_id      VARCHAR PRIMARY KEY,
  plan_id          VARCHAR NOT NULL,
  steps            JSONB NOT NULL,
  rehearsed        BOOLEAN NOT NULL DEFAULT FALSE
);

-- ---------------------------------------------------------------- Run
CREATE TABLE agent (
  agent_id         VARCHAR PRIMARY KEY,
  name             VARCHAR NOT NULL,
  max_autonomy     VARCHAR NOT NULL,      -- L0..L3
  service_identity VARCHAR NOT NULL,
  tool_scope       VARCHAR[] NOT NULL
);

CREATE TABLE agent_version (
  agent_id         VARCHAR NOT NULL,
  version          VARCHAR NOT NULL,
  prompt_template  VARCHAR,
  eval_passed      BOOLEAN NOT NULL,
  released_at      TIMESTAMP NOT NULL,
  PRIMARY KEY (agent_id, version)
);

CREATE TABLE agent_run (
  run_id           VARCHAR PRIMARY KEY,
  agent_id         VARCHAR NOT NULL,
  agent_version    VARCHAR NOT NULL,
  tenant_id        VARCHAR NOT NULL,
  trigger          VARCHAR NOT NULL,
  inputs_ref       VARCHAR,
  started_at       TIMESTAMP NOT NULL,
  completed_at     TIMESTAMP,
  status           VARCHAR NOT NULL
);

CREATE TABLE agent_action (             -- immutable: each status transition is a new row (seq)
  action_id        VARCHAR NOT NULL,
  seq              INTEGER NOT NULL,
  run_id           VARCHAR NOT NULL,
  agent_id         VARCHAR NOT NULL,
  autonomy         VARCHAR NOT NULL,
  action_type      VARCHAR NOT NULL,
  target           VARCHAR,
  payload          JSONB NOT NULL,
  rollback_payload JSONB,
  confidence       NUMERIC(4,3),
  rationale        TEXT,
  status           VARCHAR NOT NULL,      -- proposed|approved|executed|rolled_back|rejected|failed
  actor            VARCHAR NOT NULL,      -- agent identity or approver
  recorded_at      TIMESTAMP NOT NULL,
  PRIMARY KEY (action_id, seq)
);

CREATE TABLE approval (
  approval_id      VARCHAR PRIMARY KEY,
  subject_type     VARCHAR NOT NULL,
  subject_id       VARCHAR NOT NULL,
  approver         VARCHAR NOT NULL,
  decision         VARCHAR NOT NULL,      -- approved|rejected
  comment          TEXT,
  decided_at       TIMESTAMP NOT NULL
);

CREATE TABLE incident (
  incident_id      VARCHAR PRIMARY KEY,
  tenant_id        VARCHAR NOT NULL,
  source           VARCHAR NOT NULL,
  severity         VARCHAR NOT NULL,
  title            VARCHAR NOT NULL,
  status           VARCHAR NOT NULL,
  opened_at        TIMESTAMP NOT NULL,
  resolved_at      TIMESTAMP
);

-- ---------------------------------------------------------------- Knowledge (published copies of YAML)
CREATE TABLE pattern (
  pattern_id       VARCHAR PRIMARY KEY,
  source_dialect   VARCHAR NOT NULL,
  source_construct VARCHAR NOT NULL,
  target_construct VARCHAR NOT NULL,
  note             VARCHAR,
  last_verified    DATE NOT NULL
);

CREATE TABLE known_issue (
  issue_id         VARCHAR PRIMARY KEY,   -- e.g. TD-01
  source_dialect   VARCHAR NOT NULL,
  title            VARCHAR NOT NULL,
  severity         VARCHAR NOT NULL,      -- S1..S4
  detection_rule   VARCHAR NOT NULL,      -- reference to executable detector
  fix_pattern_id   VARCHAR,
  test_case_ids    VARCHAR[],
  frequency_observed INTEGER DEFAULT 0,   -- grows across engagements (anonymised)
  last_verified    DATE NOT NULL,         -- against current Snowflake docs/behaviour
  verified_by      VARCHAR NOT NULL
);

CREATE TABLE fix_pattern (
  fix_pattern_id   VARCHAR PRIMARY KEY,
  issue_id         VARCHAR NOT NULL,
  description      TEXT NOT NULL,
  applies_when     VARCHAR
);

CREATE TABLE test_case (
  test_case_id     VARCHAR PRIMARY KEY,
  issue_id         VARCHAR,
  description      TEXT NOT NULL,
  definition       JSONB NOT NULL
);

CREATE TABLE playbook (
  playbook_id      VARCHAR PRIMARY KEY,
  title            VARCHAR NOT NULL,
  steps            JSONB NOT NULL
);

CREATE TABLE rubric (
  namespace        VARCHAR PRIMARY KEY,
  current_version  VARCHAR NOT NULL
);

CREATE TABLE rubric_version (
  namespace        VARCHAR NOT NULL,
  version          VARCHAR NOT NULL,
  rubric_set_version VARCHAR NOT NULL,
  "values"         JSONB NOT NULL,
  published_at     TIMESTAMP NOT NULL,
  PRIMARY KEY (namespace, version)
);

-- ---------------------------------------------------------------- Audit
CREATE TABLE audit_event (
  event_id         VARCHAR PRIMARY KEY,
  tenant_id        VARCHAR,
  actor            VARCHAR NOT NULL,      -- human id or agent identity
  actor_type       VARCHAR NOT NULL,      -- human|agent|system
  action           VARCHAR NOT NULL,
  subject_type     VARCHAR,
  subject_id       VARCHAR,
  details          JSONB,
  occurred_at      TIMESTAMP NOT NULL
);

CREATE TABLE snapshot (
  snapshot_id      VARCHAR PRIMARY KEY,
  tenant_id        VARCHAR,
  engagement_id    VARCHAR,
  kind             VARCHAR NOT NULL,      -- diagnostic|assessment|conversion|validation|cutover|observability
  content_hash     VARCHAR NOT NULL,
  location         VARCHAR NOT NULL,      -- object-store URI / local path
  manifest         JSONB NOT NULL,
  sealed_at        TIMESTAMP NOT NULL
);
