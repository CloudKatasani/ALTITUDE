-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/marketplace/products.yaml. Regenerate with `altitude generate`.
-- Data product DP-CUSTOMER-360 (Customer 360): owner crm-data@acme, classification pii
CREATE DATABASE IF NOT EXISTS MARKETPLACE;
CREATE SCHEMA IF NOT EXISTS MARKETPLACE.DP_CUSTOMER_360 WITH MANAGED ACCESS;
CREATE OR REPLACE SECURE VIEW MARKETPLACE.DP_CUSTOMER_360.DIM_CUSTOMER COMMENT = 'Customer 360 — contract view' AS SELECT CUSTOMER_ID, NAME, EMAIL, PHONE, SEGMENT, REGION, IS_CURRENT FROM EDW.SALES.DIM_CUSTOMER;
CREATE SHARE IF NOT EXISTS DP_CUSTOMER_360_SHARE;
GRANT USAGE ON DATABASE MARKETPLACE TO SHARE DP_CUSTOMER_360_SHARE;
GRANT USAGE ON SCHEMA MARKETPLACE.DP_CUSTOMER_360 TO SHARE DP_CUSTOMER_360_SHARE;
GRANT SELECT ON VIEW MARKETPLACE.DP_CUSTOMER_360.DIM_CUSTOMER TO SHARE DP_CUSTOMER_360_SHARE;
CREATE ORGANIZATION LISTING IF NOT EXISTS DP_CUSTOMER_360 SHARE DP_CUSTOMER_360_SHARE AS
$$
title: Customer 360
subtitle: Sales data product · pii
description: 'Current customer attributes and segments with contact details masked
  by policy for non-privileged roles.


  Certified KPIs: Active customers.'
organization_profile: INTERNAL
organization_targets:
  discovery:
  - all_internal_accounts: true
  access:
  - all_internal_accounts: true
support_contact: crm-steward@acme
approver_contact: crm-data@acme
data_dictionary:
  featured:
    database_objects:
    - name: DIM_CUSTOMER
      schema: DP_CUSTOMER_360
      domain: VIEW
$$;
