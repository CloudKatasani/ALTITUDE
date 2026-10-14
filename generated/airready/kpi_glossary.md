<!-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/semantic/kpi_registry.yaml. Regenerate with `altitude generate`. -->
# Certified KPI glossary

One definition per KPI; generated from the KPI registry.

| KPI | Name | Domain | Definition | Synonyms | Owner |
|---|---|---|---|---|---|
| KPI-GROSS-REVENUE | Gross Revenue | finance | `SUM(revenue_lines.gross_amount)` | gross sales | cfo-office@example.com |
| KPI-REVENUE | Revenue | finance | `SUM(revenue_lines.net_amount)` | net revenue, recognised revenue, recognized revenue | cfo-office@example.com |
| KPI-TAX | Tax | finance | `SUM(revenue_lines.tax_amount)` | tax collected | cfo-office@example.com |
| KPI-ACTIVE-CUSTOMERS | Active Customers | sales | `COUNT(DISTINCT customers.customer_id)` | customer count, customers | crm-data@example.com |
| KPI-AOV | Average Order Value | sales | `SUM(orders.net_amount) / NULLIF(COUNT(DISTINCT orders.order_id), 0)` | aov, basket size | sales-ops@example.com |
| KPI-BOOKINGS | Bookings | sales | `SUM(orders.net_amount)` | booked sales, order value | sales-ops@example.com |
| KPI-ORDERS | Order Count | sales | `COUNT(DISTINCT orders.order_id)` | orders, number of orders | sales-ops@example.com |
