-- M2 extraction agent & harvest (connectors). PostgreSQL 16 dialect.

-- One row per harvest executed by an extraction agent.
CREATE TABLE harvest_run (
  harvest_id       VARCHAR PRIMARY KEY,
  engagement_id    VARCHAR NOT NULL,
  source_system_id VARCHAR NOT NULL,
  dialect          VARCHAR NOT NULL,
  manifest_id      VARCHAR NOT NULL,
  manifest_version VARCHAR NOT NULL,
  as_of            TIMESTAMP NOT NULL,
  statements       INTEGER NOT NULL,      -- read statements executed (all logged)
  refused          INTEGER NOT NULL,      -- statements refused by the read-only guard
  object_count     INTEGER NOT NULL,
  snapshot_id      VARCHAR,
  summary          JSONB
);

-- Harvested metadata that has no dedicated canonical column: table statistics
-- (row_count, size_bytes), schedule frequency, SET/MULTISET kind, tags.
CREATE TABLE object_attribute (
  object_id        VARCHAR NOT NULL,
  attr             VARCHAR NOT NULL,
  value            VARCHAR,
  PRIMARY KEY (object_id, attr)
);
