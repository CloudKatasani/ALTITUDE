-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/marketplace/agents.yaml. Regenerate with `altitude generate`.
-- Marketplace agent MA-POLICY-SEARCH (Policy & Procedure Search), runs as AGENT_ROLE
CREATE SCHEMA IF NOT EXISTS MARKETPLACE.AGENTS;
CREATE OR REPLACE AGENT MARKETPLACE.AGENTS.MA_POLICY_SEARCH
  COMMENT = 'Finds and cites the governing policy for a data-handling question, with the paragraph it relied on.'
  FROM SPECIFICATION
$$
profile:
  display_name: Policy & Procedure Search
instructions:
  response: You are Policy & Procedure Search, published by ALTITUDE Partners. Answer
    only from the tools; cite the certified KPI or document you used; if the data
    cannot answer, say so.
  orchestration: Use the tool for every factual answer. Never reveal masked values.
  sample_questions:
  - question: Can I share customer emails with a vendor?
  - question: How long do we retain AMI interval data?
tools:
- tool_spec:
    type: cortex_search
    name: search
tool_resources:
  search:
    name: DOCS.SEARCH.CSS_POLICIES
    max_results: 5
$$;
GRANT USAGE ON AGENT MARKETPLACE.AGENTS.MA_POLICY_SEARCH TO ROLE AGENT_ROLE;
