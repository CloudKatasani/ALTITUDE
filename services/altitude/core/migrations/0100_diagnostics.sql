-- Package D (diagnostics): runs, evidence, suggestions and their lifecycle, scores.
-- Every row references the sealed snapshot and the rubric version it was computed from (principle 5).
CREATE TABLE diag_run (
  run_id           VARCHAR PRIMARY KEY,      -- RUN-<hash(snapshot, rubric, catalogue, tier)>: reruns are idempotent
  snapshot_id      VARCHAR NOT NULL,
  rubric_version   VARCHAR NOT NULL,
  catalogue_hash   VARCHAR NOT NULL,
  tier             VARCHAR NOT NULL,         -- D0|D1|D2|D3
  tenant_id        VARCHAR,
  engagement_id    VARCHAR,
  platform_health_index NUMERIC(5,1),
  suggestions      INTEGER NOT NULL,
  summary          JSONB NOT NULL,           -- scorecard + recommendations (aggregates only)
  created_at       TIMESTAMP NOT NULL
);

CREATE TABLE diag_evidence (                 -- append-only
  evidence_id      VARCHAR PRIMARY KEY,      -- EV-<KIND>-<hash>
  snapshot_id      VARCHAR NOT NULL,
  check_id         VARCHAR NOT NULL,
  object_name      VARCHAR NOT NULL,
  kind             VARCHAR NOT NULL,
  cluster_key      VARCHAR,
  metrics          JSONB NOT NULL,           -- detector signals (metadata aggregates; no row data)
  detector_ref     VARCHAR NOT NULL,
  detector_sha     VARCHAR NOT NULL,
  created_at       TIMESTAMP NOT NULL
);

CREATE TABLE diag_suggestion (
  suggestion_id    VARCHAR PRIMARY KEY,      -- SUG-<hash(snapshot, check, cluster)>
  run_id           VARCHAR NOT NULL,
  snapshot_id      VARCHAR NOT NULL,
  rubric_version   VARCHAR NOT NULL,
  check_id         VARCHAR NOT NULL,
  domain           VARCHAR NOT NULL,
  waf_pillar       VARCHAR NOT NULL,
  title            VARCHAR NOT NULL,
  record           JSONB NOT NULL,           -- canonical suggestion record (Section 6.5)
  value_p50_usd    NUMERIC(14,2),
  value_conservative_usd NUMERIC(14,2),
  risk_score       INTEGER,
  confidence       NUMERIC(4,3) NOT NULL,
  needs_review     BOOLEAN NOT NULL,         -- below rubric.ai.review_confidence_min
  quadrant         VARCHAR NOT NULL,         -- quick_win|strategic|hygiene|defer
  priority_rank    INTEGER NOT NULL,
  status           VARCHAR NOT NULL,         -- proposed|accepted|implemented|value_realised|rejected
  reviewer         VARCHAR,                  -- recorded on accept/reject
  narrative        TEXT,
  created_at       TIMESTAMP NOT NULL,
  updated_at       TIMESTAMP NOT NULL
);

CREATE TABLE diag_suggestion_event (         -- append-only lifecycle history
  event_id         VARCHAR PRIMARY KEY,
  suggestion_id    VARCHAR NOT NULL,
  from_status      VARCHAR,
  to_status        VARCHAR NOT NULL,
  actor            VARCHAR NOT NULL,
  reviewer         VARCHAR,
  comment          TEXT,
  occurred_at      TIMESTAMP NOT NULL
);

CREATE TABLE diag_score (
  run_id           VARCHAR NOT NULL,
  scope            VARCHAR NOT NULL,         -- domain|pillar|phi
  scope_key        VARCHAR NOT NULL,
  score            INTEGER,                  -- 1..5 (null when not in scope)
  raw              NUMERIC(6,4),
  label            VARCHAR,
  PRIMARY KEY (run_id, scope, scope_key)
);
