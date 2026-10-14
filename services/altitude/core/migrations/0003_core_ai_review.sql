-- Principle 3: every AI inference carries confidence + rationale; low-confidence
-- inferences wait in the human review queue before they affect code, scores or estimates.
CREATE TABLE ai_inference (
  inference_id     VARCHAR PRIMARY KEY,
  tenant_id        VARCHAR,
  kind             VARCHAR NOT NULL,      -- narrative|classification|disposition|remediation|answer|...
  subject_type     VARCHAR NOT NULL,
  subject_id       VARCHAR NOT NULL,
  provider         VARCHAR NOT NULL,      -- template|cortex|anthropic|...
  model_id         VARCHAR NOT NULL,
  prompt_template  VARCHAR NOT NULL,      -- id@version
  inputs_ref       VARCHAR,
  output           TEXT NOT NULL,
  confidence       NUMERIC(4,3) NOT NULL,
  rationale        TEXT NOT NULL,
  needs_review     BOOLEAN NOT NULL,
  created_at       TIMESTAMP NOT NULL
);

CREATE TABLE review_item (
  item_id          VARCHAR PRIMARY KEY,
  tenant_id        VARCHAR,
  subject_type     VARCHAR NOT NULL,
  subject_id       VARCHAR NOT NULL,
  reason           VARCHAR NOT NULL,      -- low_confidence|sampled|policy
  confidence       NUMERIC(4,3),
  status           VARCHAR NOT NULL,      -- open|approved|rejected|modified
  reviewer         VARCHAR,
  decided_at       TIMESTAMP,
  created_at       TIMESTAMP NOT NULL
);
