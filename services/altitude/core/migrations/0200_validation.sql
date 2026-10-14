-- M6 validation engine: data ownership and accepted-deviation scope.
-- (validation_suite / validation_check / validation_run / mismatch_cluster / accepted_deviation live in 0001.)

-- Data owner per validated object: only this person may accept a deviation for it.
CREATE TABLE validation_object_owner (
  object_id        VARCHAR PRIMARY KEY,
  data_owner       VARCHAR NOT NULL,
  assigned_by      VARCHAR NOT NULL,
  assigned_at      TIMESTAMP NOT NULL
);

-- What an accepted deviation covers: a root-cause signature ("<signature>:<column>") on one object.
-- Later runs with the same signature on the same object are classified accepted_deviation until review_by.
CREATE TABLE accepted_deviation_scope (
  deviation_id     VARCHAR PRIMARY KEY,
  object_id        VARCHAR NOT NULL,
  level            VARCHAR NOT NULL,
  signature        VARCHAR NOT NULL,
  known_issue_id   VARCHAR
);
