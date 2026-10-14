-- Engagement facts that Sherpa, next actions and the review board reason over
-- (e.g. chosen pattern, procedural script count, whether a test harness exists).
-- Latest row per (engagement, key) wins; history is kept.
CREATE TABLE engagement_fact (
  engagement_id    VARCHAR NOT NULL,
  fact_key         VARCHAR NOT NULL,
  value            JSONB NOT NULL,
  set_by           VARCHAR NOT NULL,
  set_at           TIMESTAMP NOT NULL
);
