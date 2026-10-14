<!-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/marketplace. Regenerate with `altitude generate`. -->
# Marketplace catalogue

## Data products

| ID | Name | Domain | Owner | Classification | Endpoints |
|---|---|---|---|---|---|
| DP-ORDERS | Orders | sales | sales-data@acme | internal | sql, semantic_view, mcp |
| DP-REVENUE | Recognised Revenue | finance | finance-data@acme | confidential | sql, semantic_view |
| DP-CUSTOMER-360 | Customer 360 | sales | crm-data@acme | pii | sql, mcp |
| DP-DIGITAL-EVENTS | Digital Engagement Events | digital | digital@acme | internal | sql |

## Agents

| ID | Name | Kind | Data products | Role | Golden questions |
|---|---|---|---|---|---|
| MA-REVENUE-ANALYST | Revenue Analyst | cortex_analyst | DP-ORDERS, DP-REVENUE | AGENT_ROLE | 24 |
| MA-CUSTOMER-SERVICE | Customer Service Assistant | cortex_analyst | DP-CUSTOMER-360, DP-DIGITAL-EVENTS | AGENT_ROLE | 18 |
| MA-POLICY-SEARCH | Policy & Procedure Search | cortex_search | — | AGENT_ROLE | 30 |
| MA-FINOPS-ADVISOR | FinOps Advisor | cortex_analyst | — | AGENT_ROLE | 16 |
