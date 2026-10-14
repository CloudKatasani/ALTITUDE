-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/observability/kpis. Regenerate with `altitude generate`.
USE DATABASE OBS;
CREATE OR REPLACE AGENT OBS.SEMANTIC.ASK_THE_PLATFORM
  COMMENT = 'Package O ask-the-platform agent: answers only from certified KPIs in OBS.SEMANTIC, with citations'
  FROM SPECIFICATION
$$
{
  "models": {
    "orchestration": "auto"
  },
  "instructions": {
    "response": "Answer only from the certified KPIs exposed by the semantic views. Always cite the KPI id(s), the KPI table and the time window used, and state the unit. If no certified KPI answers the question, or the KPI has no data for the window, say so and refuse; never estimate.",
    "orchestration": "Map the question to a KPI via its name and synonyms, apply account / dimension / time filters, aggregate with the KPI's aggregation, and return the rows used.",
    "sample_questions": [
      {
        "question": "How many credits did WH_DS use in the last 7 days?"
      },
      {
        "question": "What was our total spend yesterday?"
      },
      {
        "question": "What is the idle credit share for WH_BI_PROD this month?"
      },
      {
        "question": "What is our MFA coverage?"
      },
      {
        "question": "How many failed tasks were there in the last 30 days?"
      },
      {
        "question": "Which cost centre spent the most last month?"
      },
      {
        "question": "What is the p95 query time on WH_BI_PROD last week?"
      },
      {
        "question": "How many Cortex credits did we use last week?"
      },
      {
        "question": "What is the task success rate over the last 30 days?"
      },
      {
        "question": "How many users have ACCOUNTADMIN?"
      },
      {
        "question": "What is the platform health index?"
      },
      {
        "question": "How much queued time did WH_BI_PROD have yesterday?"
      },
      {
        "question": "Which warehouses spill the most to storage in the last 14 days?"
      },
      {
        "question": "What is the masking coverage on classified columns?"
      },
      {
        "question": "How many dormant users do we have?"
      },
      {
        "question": "What is the serverless credit breakdown for the last 7 days?"
      }
    ]
  },
  "tools": [
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "kpi_ai",
        "description": "Certified ai KPIs (OBS.SEMANTIC.SV_AI)"
      }
    },
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "kpi_cost",
        "description": "Certified cost KPIs (OBS.SEMANTIC.SV_COST)"
      }
    },
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "kpi_governance",
        "description": "Certified governance KPIs (OBS.SEMANTIC.SV_GOVERNANCE)"
      }
    },
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "kpi_health",
        "description": "Certified health KPIs (OBS.SEMANTIC.SV_HEALTH)"
      }
    },
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "kpi_performance",
        "description": "Certified performance KPIs (OBS.SEMANTIC.SV_PERFORMANCE)"
      }
    },
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "kpi_reliability",
        "description": "Certified reliability KPIs (OBS.SEMANTIC.SV_RELIABILITY)"
      }
    },
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "kpi_security",
        "description": "Certified security KPIs (OBS.SEMANTIC.SV_SECURITY)"
      }
    },
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "kpi_usage",
        "description": "Certified usage KPIs (OBS.SEMANTIC.SV_USAGE)"
      }
    }
  ],
  "tool_resources": {
    "kpi_ai": {
      "semantic_view": "OBS.SEMANTIC.SV_AI",
      "execution_environment": {
        "type": "warehouse",
        "warehouse": "OBS_WH"
      }
    },
    "kpi_cost": {
      "semantic_view": "OBS.SEMANTIC.SV_COST",
      "execution_environment": {
        "type": "warehouse",
        "warehouse": "OBS_WH"
      }
    },
    "kpi_governance": {
      "semantic_view": "OBS.SEMANTIC.SV_GOVERNANCE",
      "execution_environment": {
        "type": "warehouse",
        "warehouse": "OBS_WH"
      }
    },
    "kpi_health": {
      "semantic_view": "OBS.SEMANTIC.SV_HEALTH",
      "execution_environment": {
        "type": "warehouse",
        "warehouse": "OBS_WH"
      }
    },
    "kpi_performance": {
      "semantic_view": "OBS.SEMANTIC.SV_PERFORMANCE",
      "execution_environment": {
        "type": "warehouse",
        "warehouse": "OBS_WH"
      }
    },
    "kpi_reliability": {
      "semantic_view": "OBS.SEMANTIC.SV_RELIABILITY",
      "execution_environment": {
        "type": "warehouse",
        "warehouse": "OBS_WH"
      }
    },
    "kpi_security": {
      "semantic_view": "OBS.SEMANTIC.SV_SECURITY",
      "execution_environment": {
        "type": "warehouse",
        "warehouse": "OBS_WH"
      }
    },
    "kpi_usage": {
      "semantic_view": "OBS.SEMANTIC.SV_USAGE",
      "execution_environment": {
        "type": "warehouse",
        "warehouse": "OBS_WH"
      }
    }
  }
}
$$;
GRANT USAGE ON AGENT OBS.SEMANTIC.ASK_THE_PLATFORM TO ROLE OBS_READER;
