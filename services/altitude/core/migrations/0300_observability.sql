-- Package O — suggestion-to-value loop (Section 7.12).
-- Package D suggestions carry kpis_to_watch; once implemented, Package O measures the watched KPIs before and
-- after in the client's own account and records the realised value on the suggestion.

-- Append-only: every status transition of a suggestion is a new row (proposed → accepted → implemented →
-- value_realised | rejected). The current status is the latest row per suggestion.
CREATE TABLE obs_suggestion_status (
  transition_id    VARCHAR PRIMARY KEY,
  tenant_id        VARCHAR,
  suggestion_id    VARCHAR NOT NULL,
  check_id         VARCHAR,
  from_status      VARCHAR,
  to_status        VARCHAR NOT NULL,
  measurement_id   VARCHAR,
  actor            VARCHAR NOT NULL,
  actor_type       VARCHAR NOT NULL,      -- human|agent|system
  reason           TEXT,
  transitioned_at  TIMESTAMP NOT NULL
);

-- Append-only: one row per before/after measurement of an implemented suggestion.
CREATE TABLE obs_value_measurement (
  measurement_id   VARCHAR PRIMARY KEY,
  tenant_id        VARCHAR,
  suggestion_id    VARCHAR NOT NULL,
  check_id         VARCHAR,
  account_name     VARCHAR,
  affected_objects JSONB,
  implemented_at   DATE NOT NULL,
  before_start     DATE NOT NULL,
  before_end       DATE NOT NULL,
  after_start      DATE NOT NULL,
  after_end        DATE NOT NULL,
  kpi_results      JSONB NOT NULL,        -- per watched KPI: before, after, delta, delta_pct, improved, coverage
  identified_usd   NUMERIC(14, 2),        -- value.annualised_usd.p50 from Package D
  realised_usd     NUMERIC(14, 2),        -- measured, annualised
  realised_method  TEXT NOT NULL,
  outcome          VARCHAR NOT NULL,      -- value_realised|no_improvement|insufficient_data
  rubric_version   VARCHAR NOT NULL,
  evidence_hash    VARCHAR NOT NULL,      -- hash of the KPI rows used (reproducibility)
  measured_at      TIMESTAMP NOT NULL
);

CREATE INDEX obs_value_measurement_suggestion ON obs_value_measurement (suggestion_id);
CREATE INDEX obs_suggestion_status_suggestion ON obs_suggestion_status (suggestion_id);

-- Quarterly business review: identified vs realised value and Health Index delta.
CREATE TABLE obs_qbr_summary (
  qbr_id           VARCHAR PRIMARY KEY,
  tenant_id        VARCHAR,
  period_start     DATE,
  period_end       DATE,
  identified_usd   NUMERIC(14, 2),
  realised_usd     NUMERIC(14, 2),
  health_index_before NUMERIC(6, 2),
  health_index_after  NUMERIC(6, 2),
  summary          JSONB NOT NULL,
  created_at       TIMESTAMP NOT NULL
);
