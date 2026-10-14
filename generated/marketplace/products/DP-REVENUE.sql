-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/marketplace/products.yaml. Regenerate with `altitude generate`.
-- Data product DP-REVENUE (Recognised Revenue): owner finance-data@acme, classification confidential
CREATE DATABASE IF NOT EXISTS MARKETPLACE;
CREATE SCHEMA IF NOT EXISTS MARKETPLACE.DP_REVENUE WITH MANAGED ACCESS;
CREATE OR REPLACE SECURE VIEW MARKETPLACE.DP_REVENUE.FCT_REVENUE COMMENT = 'Recognised Revenue — contract view' AS SELECT REVENUE_DATE, PRODUCT_ID, REGION, NET_AMOUNT, GROSS_AMOUNT, TAX_AMOUNT, CURRENCY FROM EDW.FINANCE.FCT_REVENUE;
CREATE SHARE IF NOT EXISTS DP_REVENUE_SHARE;
GRANT USAGE ON DATABASE MARKETPLACE TO SHARE DP_REVENUE_SHARE;
GRANT USAGE ON SCHEMA MARKETPLACE.DP_REVENUE TO SHARE DP_REVENUE_SHARE;
GRANT SELECT ON VIEW MARKETPLACE.DP_REVENUE.FCT_REVENUE TO SHARE DP_REVENUE_SHARE;
CREATE ORGANIZATION LISTING IF NOT EXISTS DP_REVENUE SHARE DP_REVENUE_SHARE AS
$$
title: Recognised Revenue
subtitle: Finance data product · confidential
description: 'Recognised revenue by day, product and region, net of tax; feeds month-end
  close and the board pack.


  Certified KPIs: Revenue, Gross revenue, Tax.'
organization_profile: INTERNAL
organization_targets:
  discovery:
  - all_internal_accounts: true
  access:
  - all_internal_accounts: true
support_contact: controller@acme
approver_contact: finance-data@acme
data_dictionary:
  featured:
    database_objects:
    - name: FCT_REVENUE
      schema: DP_REVENUE
      domain: VIEW
data_attributes:
  refresh_rate: Daily by 06:00 UTC
$$;
