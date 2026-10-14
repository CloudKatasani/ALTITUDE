-- M4 planning & estimation. PostgreSQL 16 dialect.

-- A wave plan computed from an assessment snapshot under a rubric + wave-rule version.
CREATE TABLE wave_plan (
  plan_id                VARCHAR PRIMARY KEY,
  engagement_id          VARCHAR,
  assessment_snapshot_id VARCHAR NOT NULL,
  harvest_snapshot_id    VARCHAR NOT NULL,
  rubric_version         VARCHAR NOT NULL,
  rules_version          VARCHAR NOT NULL,
  status                 VARCHAR NOT NULL,   -- draft|baseline
  start_date             DATE,
  waves                  INTEGER NOT NULL,
  violations             JSONB NOT NULL,
  plan                   JSONB NOT NULL
);

-- Factory state machine (Section 9.2): every transition is an immutable record.
CREATE TABLE factory_transition (
  transition_id    VARCHAR PRIMARY KEY,
  wave_id          VARCHAR NOT NULL,
  object_id        VARCHAR NOT NULL,
  seq              INTEGER NOT NULL,
  from_state       VARCHAR NOT NULL,
  to_state         VARCHAR NOT NULL,
  actor            VARCHAR NOT NULL,      -- human id or agent identity
  actor_type       VARCHAR NOT NULL,      -- human|agent|system
  evidence_ref     VARCHAR NOT NULL,
  confidence       NUMERIC(4,3) NOT NULL,
  note             TEXT,
  recorded_at      TIMESTAMP NOT NULL
);
