-- Anonymised peer benchmarks (Section 4.6 moat 4, 6.11) and go-to-market buying signals (Section 2).
CREATE TABLE benchmark_observation (
  observation_id   VARCHAR PRIMARY KEY,
  contributor_hash VARCHAR NOT NULL,     -- salted hash of the tenant; never the account name
  industry         VARCHAR NOT NULL,
  spend_band       VARCHAR NOT NULL,
  metric           VARCHAR NOT NULL,     -- e.g. KPI-COST-007
  value            DOUBLE NOT NULL,
  period           VARCHAR NOT NULL,     -- e.g. 2026-Q3
  consent_ref      VARCHAR NOT NULL,     -- contract clause / consent record
  contributed_at   TIMESTAMP NOT NULL
);

CREATE TABLE gtm_signal (
  signal_id        VARCHAR PRIMARY KEY,
  account          VARCHAR NOT NULL,
  kind             VARCHAR NOT NULL,     -- renewal_window|job_posting|ae_referral|snowflake_customer|...
  detail           VARCHAR,
  observed_on      DATE NOT NULL,
  source           VARCHAR NOT NULL
);
