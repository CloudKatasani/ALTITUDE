-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/semantic/kpi_registry.yaml. Regenerate with `altitude generate`.
CREATE OR REPLACE SEMANTIC VIEW EDW.SEMANTIC.SV_FINANCE
  TABLES (
    revenue_lines AS EDW.FINANCE.FCT_REVENUE PRIMARY KEY (REVENUE_DATE, PRODUCT_ID, REGION) WITH SYNONYMS = ('ledger revenue') COMMENT = 'Recognised revenue by day and product',
    products AS EDW.SALES.DIM_PRODUCT PRIMARY KEY (PRODUCT_ID) WITH SYNONYMS = ('catalogue') COMMENT = 'Product catalogue'
  )
  RELATIONSHIPS (
    revenue_to_products AS revenue_lines (PRODUCT_ID) REFERENCES products (PRODUCT_ID)
  )
  FACTS (
    revenue_lines.net_amount AS NET_AMOUNT COMMENT = 'Recognised revenue net of tax',
    revenue_lines.gross_amount AS GROSS_AMOUNT COMMENT = 'Recognised revenue before deductions',
    revenue_lines.tax_amount AS TAX_AMOUNT COMMENT = 'Tax on recognised revenue'
  )
  DIMENSIONS (
    revenue_lines.revenue_date AS REVENUE_DATE WITH SYNONYMS = ('date', 'day') COMMENT = 'Recognition date',
    revenue_lines.region AS REGION WITH SYNONYMS = ('region', 'territory') COMMENT = 'Region',
    products.category AS CATEGORY WITH SYNONYMS = ('product category') COMMENT = 'Product category'
  )
  METRICS (
    revenue_lines.revenue AS SUM(revenue_lines.net_amount) WITH SYNONYMS = ('net revenue', 'recognised revenue', 'recognized revenue') COMMENT = '[KPI-REVENUE] Recognised revenue net of discounts and tax (the certified definition; gross is a separate KPI). Owner: cfo-office@example.com',
    revenue_lines.gross_revenue AS SUM(revenue_lines.gross_amount) WITH SYNONYMS = ('gross sales') COMMENT = '[KPI-GROSS-REVENUE] Recognised revenue before deductions. Owner: cfo-office@example.com',
    revenue_lines.tax AS SUM(revenue_lines.tax_amount) WITH SYNONYMS = ('tax collected') COMMENT = '[KPI-TAX] Tax on recognised revenue. Owner: cfo-office@example.com'
  )
  COMMENT = 'Recognised revenue by day, product and region. Owner: finance-data@example.com';
