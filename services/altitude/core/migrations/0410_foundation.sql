-- M7 Foundation: Well-Architected findings per sealed snapshot (reproducible per snapshot + rubric + checks version).
CREATE TABLE wa_finding (
  snapshot_id      VARCHAR NOT NULL,
  rubric_version   VARCHAR NOT NULL,
  checks_version   VARCHAR NOT NULL,
  check_id         VARCHAR NOT NULL,
  severity         VARCHAR NOT NULL,
  pillar           VARCHAR NOT NULL,
  objects          VARCHAR[] NOT NULL,
  playbook_id      VARCHAR NOT NULL,
  autonomy         VARCHAR NOT NULL,
  evidence         JSONB NOT NULL,
  PRIMARY KEY (snapshot_id, rubric_version, checks_version, check_id)
);
