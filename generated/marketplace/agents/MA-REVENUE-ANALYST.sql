-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/marketplace/agents.yaml. Regenerate with `altitude generate`.
-- Marketplace agent MA-REVENUE-ANALYST (Revenue Analyst), runs as AGENT_ROLE
CREATE SCHEMA IF NOT EXISTS MARKETPLACE.AGENTS;
CREATE OR REPLACE AGENT MARKETPLACE.AGENTS.MA_REVENUE_ANALYST
  COMMENT = 'Answers revenue, bookings and order questions in plain English with the SQL and the certified KPI it used.'
  FROM SPECIFICATION
$$
profile:
  display_name: Revenue Analyst
instructions:
  response: You are Revenue Analyst, published by ALTITUDE Partners. Answer only from
    the tools; cite the certified KPI or document you used; if the data cannot answer,
    say so.
  orchestration: Use the tool for every factual answer. Never reveal masked values.
  sample_questions:
  - question: What was net revenue by region last month?
  - question: How did average order value trend this quarter?
tools:
- tool_spec:
    type: cortex_analyst_text_to_sql
    name: analyst
tool_resources:
  analyst:
    semantic_view: EDW.SEMANTIC.SV_FINANCE
$$;
GRANT USAGE ON AGENT MARKETPLACE.AGENTS.MA_REVENUE_ANALYST TO ROLE AGENT_ROLE;
