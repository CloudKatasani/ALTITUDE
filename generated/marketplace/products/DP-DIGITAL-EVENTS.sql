-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/marketplace/products.yaml. Regenerate with `altitude generate`.
-- Data product DP-DIGITAL-EVENTS (Digital Engagement Events): owner digital@acme, classification internal
CREATE DATABASE IF NOT EXISTS MARKETPLACE;
CREATE SCHEMA IF NOT EXISTS MARKETPLACE.DP_DIGITAL_EVENTS WITH MANAGED ACCESS;
CREATE OR REPLACE SECURE VIEW MARKETPLACE.DP_DIGITAL_EVENTS.FCT_EVENTS COMMENT = 'Digital Engagement Events — contract view' AS SELECT EVENT_ID, EVENT_DATE, CUSTOMER_ID, EVENT_TYPE FROM EDW.SALES.FCT_EVENTS;
CREATE SHARE IF NOT EXISTS DP_DIGITAL_EVENTS_SHARE;
GRANT USAGE ON DATABASE MARKETPLACE TO SHARE DP_DIGITAL_EVENTS_SHARE;
GRANT USAGE ON SCHEMA MARKETPLACE.DP_DIGITAL_EVENTS TO SHARE DP_DIGITAL_EVENTS_SHARE;
GRANT SELECT ON VIEW MARKETPLACE.DP_DIGITAL_EVENTS.FCT_EVENTS TO SHARE DP_DIGITAL_EVENTS_SHARE;
CREATE ORGANIZATION LISTING IF NOT EXISTS DP_DIGITAL_EVENTS SHARE DP_DIGITAL_EVENTS_SHARE AS
$$
title: Digital Engagement Events
subtitle: Digital data product · internal
description: 'Web and app events by customer and type for engagement and funnel analytics.


  Certified KPIs: Daily active users, Events per customer.'
organization_profile: INTERNAL
organization_targets:
  discovery:
  - all_internal_accounts: true
  access:
  - all_internal_accounts: true
support_contact: digital-steward@acme
approver_contact: digital@acme
data_dictionary:
  featured:
    database_objects:
    - name: FCT_EVENTS
      schema: DP_DIGITAL_EVENTS
      domain: VIEW
data_attributes:
  refresh_rate: Daily by 06:00 UTC
$$;
