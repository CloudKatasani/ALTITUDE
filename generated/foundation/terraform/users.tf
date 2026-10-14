# AUTO-GENERATED — DO NOT EDIT. Source: knowledge/foundation/landing_zone.yaml. Regenerate with `altitude generate`.
resource "snowflake_service_user" "svc_dbt" {
  name              = "SVC_DBT"
  default_role      = snowflake_account_role.fr_engineer.name
  default_warehouse = snowflake_warehouse.wh_elt.name
  network_policy    = snowflake_network_policy.np_services.name
  rsa_public_key    = lookup(var.service_user_public_keys, "SVC_DBT", null)
  comment           = "Managed by the ALTITUDE landing zone"
}

resource "snowflake_grant_account_role" "fr_engineer_to_svc_dbt" {
  role_name = snowflake_account_role.fr_engineer.name
  user_name = snowflake_service_user.svc_dbt.name
}

resource "snowflake_service_user" "svc_ingest" {
  name              = "SVC_INGEST"
  default_role      = snowflake_account_role.fr_engineer.name
  default_warehouse = snowflake_warehouse.wh_elt.name
  network_policy    = snowflake_network_policy.np_services.name
  rsa_public_key    = lookup(var.service_user_public_keys, "SVC_INGEST", null)
  comment           = "Managed by the ALTITUDE landing zone"
}

resource "snowflake_grant_account_role" "fr_engineer_to_svc_ingest" {
  role_name = snowflake_account_role.fr_engineer.name
  user_name = snowflake_service_user.svc_ingest.name
}

resource "snowflake_service_user" "svc_bi" {
  name              = "SVC_BI"
  default_role      = snowflake_account_role.fr_bi.name
  default_warehouse = snowflake_warehouse.wh_bi.name
  network_policy    = snowflake_network_policy.np_services.name
  rsa_public_key    = lookup(var.service_user_public_keys, "SVC_BI", null)
  comment           = "Managed by the ALTITUDE landing zone"
}

resource "snowflake_grant_account_role" "fr_bi_to_svc_bi" {
  role_name = snowflake_account_role.fr_bi.name
  user_name = snowflake_service_user.svc_bi.name
}
