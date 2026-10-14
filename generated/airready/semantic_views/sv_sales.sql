-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/semantic/kpi_registry.yaml. Regenerate with `altitude generate`.
CREATE OR REPLACE SEMANTIC VIEW EDW.SEMANTIC.SV_SALES
  TABLES (
    orders AS EDW.SALES.FCT_ORDERS PRIMARY KEY (ORDER_ID) WITH SYNONYMS = ('order lines', 'sales orders') COMMENT = 'Order facts',
    customers AS EDW.SALES.DIM_CUSTOMER PRIMARY KEY (CUSTOMER_ID) WITH SYNONYMS = ('clients') COMMENT = 'Current and historical customer attributes'
  )
  RELATIONSHIPS (
    orders_to_customers AS orders (CUSTOMER_ID) REFERENCES customers (CUSTOMER_ID)
  )
  FACTS (
    orders.net_amount AS NET_AMOUNT COMMENT = 'Order line amount net of discounts',
    orders.order_id AS ORDER_ID COMMENT = 'Order identifier',
    customers.customer_id AS CUSTOMER_ID COMMENT = 'Customer identifier'
  )
  DIMENSIONS (
    orders.order_date AS ORDER_DATE WITH SYNONYMS = ('date', 'day') COMMENT = 'Date the order was placed',
    orders.region AS REGION WITH SYNONYMS = ('sales region', 'territory') COMMENT = 'Sales region',
    customers.segment AS SEGMENT WITH SYNONYMS = ('customer segment') COMMENT = 'Customer segment'
  )
  METRICS (
    orders.order_count AS COUNT(DISTINCT orders.order_id) WITH SYNONYMS = ('orders', 'number of orders') COMMENT = '[KPI-ORDERS] Distinct orders placed. Owner: sales-ops@example.com',
    orders.bookings AS SUM(orders.net_amount) WITH SYNONYMS = ('booked sales', 'order value') COMMENT = '[KPI-BOOKINGS] Net value of orders booked (not yet recognised revenue). Owner: sales-ops@example.com',
    orders.average_order_value AS SUM(orders.net_amount) / NULLIF(COUNT(DISTINCT orders.order_id), 0) WITH SYNONYMS = ('aov', 'basket size') COMMENT = '[KPI-AOV] Bookings divided by orders. Owner: sales-ops@example.com',
    customers.active_customers AS COUNT(DISTINCT customers.customer_id) WITH SYNONYMS = ('customer count', 'customers') COMMENT = '[KPI-ACTIVE-CUSTOMERS] Distinct customers with at least one order in the period (filter by order_date). Owner: crm-data@example.com'
  )
  COMMENT = 'Orders and customers — booked sales. Owner: sales-data@example.com';
