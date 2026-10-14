-- M3 assessment engine. PostgreSQL 16 dialect.

-- One row per sealed assessment snapshot.
CREATE TABLE assessment_run (
  assessment_id       VARCHAR PRIMARY KEY,   -- = assessment snapshot id
  engagement_id       VARCHAR,
  harvest_snapshot_id VARCHAR NOT NULL,
  rubric_version      VARCHAR NOT NULL,
  drift_scan_status   VARCHAR NOT NULL,      -- completed|partial|skipped
  objects             INTEGER NOT NULL,
  review_items        INTEGER NOT NULL,
  summary             JSONB NOT NULL
);

CREATE TABLE anti_pattern_hit (
  hit_id           VARCHAR NOT NULL,
  snapshot_id      VARCHAR NOT NULL,
  object_id        VARCHAR NOT NULL,
  pattern_id       VARCHAR NOT NULL,         -- knowledge/anti_patterns id (AP-nn)
  severity         VARCHAR NOT NULL,
  line             INTEGER,
  snippet          TEXT,
  credits_month    NUMERIC(14,4) NOT NULL,   -- estimated; method in impact
  impact           JSONB NOT NULL,
  PRIMARY KEY (hit_id, snapshot_id)
);

CREATE TABLE drift_hit (
  hit_id           VARCHAR NOT NULL,
  snapshot_id      VARCHAR NOT NULL,
  object_id        VARCHAR NOT NULL,
  issue_id         VARCHAR NOT NULL,         -- known issue (e.g. MS-01)
  severity         VARCHAR NOT NULL,
  line             INTEGER,
  snippet          TEXT,
  message          TEXT,
  confidence       NUMERIC(4,3),
  rationale        TEXT,
  PRIMARY KEY (hit_id, snapshot_id)
);
