-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/marketplace/agents.yaml. Regenerate with `altitude generate`.
-- Marketplace agent MA-FINOPS-ADVISOR (FinOps Advisor), runs as AGENT_ROLE
CREATE SCHEMA IF NOT EXISTS MARKETPLACE.AGENTS;
CREATE OR REPLACE AGENT MARKETPLACE.AGENTS.MA_FINOPS_ADVISOR
  COMMENT = 'Explains Snowflake spend by warehouse and cost centre and forecasts month-end, citing the KPI behind each number.'
  FROM SPECIFICATION
$$
profile:
  display_name: FinOps Advisor
instructions:
  response: You are FinOps Advisor, published by ALTITUDE Partners. Answer only from
    the tools; cite the certified KPI or document you used; if the data cannot answer,
    say so.
  orchestration: Use the tool for every factual answer. Never reveal masked values.
  sample_questions:
  - question: Which warehouses drove last week's spend?
  - question: Will we stay within budget this month?
tools:
- tool_spec:
    type: cortex_analyst_text_to_sql
    name: analyst
tool_resources:
  analyst:
    semantic_view: OBS.SEMANTIC.SV_COST
$$;
GRANT USAGE ON AGENT MARKETPLACE.AGENTS.MA_FINOPS_ADVISOR TO ROLE AGENT_ROLE;
