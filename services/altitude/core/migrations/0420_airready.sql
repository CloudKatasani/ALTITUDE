-- M11 AI-Ready: EAIRN readiness scores per sealed snapshot (one row per snapshot + rubric + check-set version;
-- re-scoring must reproduce score_hash exactly).
CREATE TABLE airready_score (
  snapshot_id      VARCHAR NOT NULL,
  rubric_version   VARCHAR NOT NULL,
  checks_version   VARCHAR NOT NULL,
  registry_version VARCHAR NOT NULL,
  overall          NUMERIC(5,1) NOT NULL,
  maturity_level   INTEGER NOT NULL,
  pillars          JSONB NOT NULL,
  score_hash       VARCHAR NOT NULL,
  PRIMARY KEY (snapshot_id, rubric_version, checks_version)
);
