# AUTO-GENERATED — DO NOT EDIT. Source: knowledge/foundation/landing_zone.yaml. Regenerate with `altitude generate`.
resource "snowflake_account_role" "alt_agent_cost_sentinel" {
  name    = "ALT_AGENT_COST_SENTINEL"
  comment = "Agent role (AG-COST-SENTINEL): distinct machine identity"
}

resource "snowflake_service_user" "svc_alt_cost_sentinel" {
  name              = "SVC_ALT_COST_SENTINEL"
  default_role      = snowflake_account_role.alt_agent_cost_sentinel.name
  default_warehouse = snowflake_warehouse.wh_agents.name
  network_policy    = snowflake_network_policy.np_services.name
  rsa_public_key    = lookup(var.service_user_public_keys, "SVC_ALT_COST_SENTINEL", null)
  comment           = "ALTITUDE agent identity: Cost Sentinel"
}

resource "snowflake_grant_account_role" "alt_agent_cost_sentinel_to_svc_alt_cost_sentinel" {
  role_name = snowflake_account_role.alt_agent_cost_sentinel.name
  user_name = snowflake_service_user.svc_alt_cost_sentinel.name
}

resource "snowflake_grant_privileges_to_account_role" "alt_agent_cost_sentinel_wh_agents_usage" {
  account_role_name = snowflake_account_role.alt_agent_cost_sentinel.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.wh_agents.name
  }
}

resource "snowflake_account_role" "alt_agent_rightsizer" {
  name    = "ALT_AGENT_RIGHTSIZER"
  comment = "Agent role (AG-WAREHOUSE-RIGHTSIZER): distinct machine identity"
}

resource "snowflake_service_user" "svc_alt_rightsizer" {
  name              = "SVC_ALT_RIGHTSIZER"
  default_role      = snowflake_account_role.alt_agent_rightsizer.name
  default_warehouse = snowflake_warehouse.wh_agents.name
  network_policy    = snowflake_network_policy.np_services.name
  rsa_public_key    = lookup(var.service_user_public_keys, "SVC_ALT_RIGHTSIZER", null)
  comment           = "ALTITUDE agent identity: Warehouse Rightsizer"
}

resource "snowflake_grant_account_role" "alt_agent_rightsizer_to_svc_alt_rightsizer" {
  role_name = snowflake_account_role.alt_agent_rightsizer.name
  user_name = snowflake_service_user.svc_alt_rightsizer.name
}

resource "snowflake_grant_privileges_to_account_role" "alt_agent_rightsizer_wh_agents_usage" {
  account_role_name = snowflake_account_role.alt_agent_rightsizer.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.wh_agents.name
  }
}

resource "snowflake_account_role" "alt_agent_pipeline_triage" {
  name    = "ALT_AGENT_PIPELINE_TRIAGE"
  comment = "Agent role (AG-PIPELINE-TRIAGE): distinct machine identity"
}

resource "snowflake_service_user" "svc_alt_pipeline_triage" {
  name              = "SVC_ALT_PIPELINE_TRIAGE"
  default_role      = snowflake_account_role.alt_agent_pipeline_triage.name
  default_warehouse = snowflake_warehouse.wh_agents.name
  network_policy    = snowflake_network_policy.np_services.name
  rsa_public_key    = lookup(var.service_user_public_keys, "SVC_ALT_PIPELINE_TRIAGE", null)
  comment           = "ALTITUDE agent identity: Pipeline Triage"
}

resource "snowflake_grant_account_role" "alt_agent_pipeline_triage_to_svc_alt_pipeline_triage" {
  role_name = snowflake_account_role.alt_agent_pipeline_triage.name
  user_name = snowflake_service_user.svc_alt_pipeline_triage.name
}

resource "snowflake_grant_privileges_to_account_role" "alt_agent_pipeline_triage_wh_agents_usage" {
  account_role_name = snowflake_account_role.alt_agent_pipeline_triage.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.wh_agents.name
  }
}

resource "snowflake_account_role" "alt_agent_dq_incident" {
  name    = "ALT_AGENT_DQ_INCIDENT"
  comment = "Agent role (AG-DQ-INCIDENT): distinct machine identity"
}

resource "snowflake_service_user" "svc_alt_dq_incident" {
  name              = "SVC_ALT_DQ_INCIDENT"
  default_role      = snowflake_account_role.alt_agent_dq_incident.name
  default_warehouse = snowflake_warehouse.wh_agents.name
  network_policy    = snowflake_network_policy.np_services.name
  rsa_public_key    = lookup(var.service_user_public_keys, "SVC_ALT_DQ_INCIDENT", null)
  comment           = "ALTITUDE agent identity: DQ Incident Agent"
}

resource "snowflake_grant_account_role" "alt_agent_dq_incident_to_svc_alt_dq_incident" {
  role_name = snowflake_account_role.alt_agent_dq_incident.name
  user_name = snowflake_service_user.svc_alt_dq_incident.name
}

resource "snowflake_grant_privileges_to_account_role" "alt_agent_dq_incident_wh_agents_usage" {
  account_role_name = snowflake_account_role.alt_agent_dq_incident.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.wh_agents.name
  }
}

resource "snowflake_account_role" "alt_agent_access_hygiene" {
  name    = "ALT_AGENT_ACCESS_HYGIENE"
  comment = "Agent role (AG-ACCESS-HYGIENE): distinct machine identity"
}

resource "snowflake_service_user" "svc_alt_access_hygiene" {
  name              = "SVC_ALT_ACCESS_HYGIENE"
  default_role      = snowflake_account_role.alt_agent_access_hygiene.name
  default_warehouse = snowflake_warehouse.wh_agents.name
  network_policy    = snowflake_network_policy.np_services.name
  rsa_public_key    = lookup(var.service_user_public_keys, "SVC_ALT_ACCESS_HYGIENE", null)
  comment           = "ALTITUDE agent identity: Access Hygiene Agent"
}

resource "snowflake_grant_account_role" "alt_agent_access_hygiene_to_svc_alt_access_hygiene" {
  role_name = snowflake_account_role.alt_agent_access_hygiene.name
  user_name = snowflake_service_user.svc_alt_access_hygiene.name
}

resource "snowflake_grant_privileges_to_account_role" "alt_agent_access_hygiene_wh_agents_usage" {
  account_role_name = snowflake_account_role.alt_agent_access_hygiene.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.wh_agents.name
  }
}

resource "snowflake_account_role" "alt_agent_release_watcher" {
  name    = "ALT_AGENT_RELEASE_WATCHER"
  comment = "Agent role (AG-RELEASE-CHANGE-WATCHER): distinct machine identity"
}

resource "snowflake_service_user" "svc_alt_release_watcher" {
  name              = "SVC_ALT_RELEASE_WATCHER"
  default_role      = snowflake_account_role.alt_agent_release_watcher.name
  default_warehouse = snowflake_warehouse.wh_agents.name
  network_policy    = snowflake_network_policy.np_services.name
  rsa_public_key    = lookup(var.service_user_public_keys, "SVC_ALT_RELEASE_WATCHER", null)
  comment           = "ALTITUDE agent identity: Release Change Watcher"
}

resource "snowflake_grant_account_role" "alt_agent_release_watcher_to_svc_alt_release_watcher" {
  role_name = snowflake_account_role.alt_agent_release_watcher.name
  user_name = snowflake_service_user.svc_alt_release_watcher.name
}

resource "snowflake_grant_privileges_to_account_role" "alt_agent_release_watcher_wh_agents_usage" {
  account_role_name = snowflake_account_role.alt_agent_release_watcher.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.wh_agents.name
  }
}
