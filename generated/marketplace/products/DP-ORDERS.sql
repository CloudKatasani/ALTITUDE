-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/marketplace/products.yaml. Regenerate with `altitude generate`.
-- Data product DP-ORDERS (Orders): owner sales-data@acme, classification internal
CREATE DATABASE IF NOT EXISTS MARKETPLACE;
CREATE SCHEMA IF NOT EXISTS MARKETPLACE.DP_ORDERS WITH MANAGED ACCESS;
CREATE OR REPLACE SECURE VIEW MARKETPLACE.DP_ORDERS.FCT_ORDERS COMMENT = 'Orders — contract view' AS SELECT ORDER_ID, ORDER_DATE, CUSTOMER_ID, REGION, NET_AMOUNT, GROSS_AMOUNT, STATUS FROM EDW.SALES.FCT_ORDERS;
CREATE OR REPLACE SECURE VIEW MARKETPLACE.DP_ORDERS.DIM_PRODUCT COMMENT = 'Orders — contract view' AS SELECT PRODUCT_ID, NAME, CATEGORY FROM EDW.SALES.DIM_PRODUCT;
CREATE SHARE IF NOT EXISTS DP_ORDERS_SHARE;
GRANT USAGE ON DATABASE MARKETPLACE TO SHARE DP_ORDERS_SHARE;
GRANT USAGE ON SCHEMA MARKETPLACE.DP_ORDERS TO SHARE DP_ORDERS_SHARE;
GRANT SELECT ON VIEW MARKETPLACE.DP_ORDERS.FCT_ORDERS TO SHARE DP_ORDERS_SHARE;
GRANT SELECT ON VIEW MARKETPLACE.DP_ORDERS.DIM_PRODUCT TO SHARE DP_ORDERS_SHARE;
CREATE ORGANIZATION LISTING IF NOT EXISTS DP_ORDERS SHARE DP_ORDERS_SHARE AS
$$
title: Orders
subtitle: Sales data product · internal
description: 'One row per order line with customer, region and net/gross amounts;
  the certified basis for bookings and AOV.


  Certified KPIs: Bookings, Orders, Average order value.'
organization_profile: INTERNAL
organization_targets:
  discovery:
  - all_internal_accounts: true
  access:
  - all_internal_accounts: true
support_contact: sales-steward@acme
approver_contact: sales-data@acme
data_dictionary:
  featured:
    database_objects:
    - name: FCT_ORDERS
      schema: DP_ORDERS
      domain: VIEW
    - name: DIM_PRODUCT
      schema: DP_ORDERS
      domain: VIEW
data_attributes:
  refresh_rate: Daily by 06:00 UTC
$$;
