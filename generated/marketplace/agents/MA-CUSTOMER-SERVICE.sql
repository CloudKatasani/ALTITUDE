-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/marketplace/agents.yaml. Regenerate with `altitude generate`.
-- Marketplace agent MA-CUSTOMER-SERVICE (Customer Service Assistant), runs as AGENT_ROLE
CREATE SCHEMA IF NOT EXISTS MARKETPLACE.AGENTS;
CREATE OR REPLACE AGENT MARKETPLACE.AGENTS.MA_CUSTOMER_SERVICE
  COMMENT = 'Looks up a customer''s segment and recent engagement for service agents, never revealing masked contact details.'
  FROM SPECIFICATION
$$
profile:
  display_name: Customer Service Assistant
instructions:
  response: You are Customer Service Assistant, published by ALTITUDE Partners. Answer
    only from the tools; cite the certified KPI or document you used; if the data
    cannot answer, say so.
  orchestration: Use the tool for every factual answer. Never reveal masked values.
  sample_questions:
  - question: Which segment is customer 10442 in?
  - question: How many app sessions did they have this week?
tools:
- tool_spec:
    type: cortex_analyst_text_to_sql
    name: analyst
tool_resources:
  analyst:
    semantic_view: EDW.SEMANTIC.SV_SALES
$$;
GRANT USAGE ON AGENT MARKETPLACE.AGENTS.MA_CUSTOMER_SERVICE TO ROLE AGENT_ROLE;
