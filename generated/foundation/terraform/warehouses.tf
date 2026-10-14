# AUTO-GENERATED — DO NOT EDIT. Source: knowledge/foundation/landing_zone.yaml. Regenerate with `altitude generate`.
resource "snowflake_resource_monitor" "rm_wh_elt" {
  name            = "RM_WH_ELT"
  credit_quota    = 1500
  frequency       = "MONTHLY"
  start_timestamp = "IMMEDIATELY"
  notify_triggers = [75, 90]
  suspend_trigger = 100
}

resource "snowflake_warehouse" "wh_elt" {
  name                         = "WH_ELT"
  warehouse_size               = "MEDIUM"
  auto_suspend                 = 60
  auto_resume                  = "true"
  initially_suspended          = true
  min_cluster_count            = 1
  max_cluster_count            = 1
  scaling_policy               = "STANDARD"
  statement_timeout_in_seconds = 7200
  resource_monitor             = snowflake_resource_monitor.rm_wh_elt.name
  comment                      = "workload_class=elt"
}

resource "snowflake_resource_monitor" "rm_wh_bi" {
  name            = "RM_WH_BI"
  credit_quota    = 800
  frequency       = "MONTHLY"
  start_timestamp = "IMMEDIATELY"
  notify_triggers = [75, 90]
  suspend_trigger = 100
}

resource "snowflake_warehouse" "wh_bi" {
  name                         = "WH_BI"
  warehouse_size               = "SMALL"
  auto_suspend                 = 60
  auto_resume                  = "true"
  initially_suspended          = true
  min_cluster_count            = 1
  max_cluster_count            = 3
  scaling_policy               = "STANDARD"
  statement_timeout_in_seconds = 900
  resource_monitor             = snowflake_resource_monitor.rm_wh_bi.name
  comment                      = "workload_class=bi"
}

resource "snowflake_resource_monitor" "rm_wh_ds" {
  name            = "RM_WH_DS"
  credit_quota    = 1200
  frequency       = "MONTHLY"
  start_timestamp = "IMMEDIATELY"
  notify_triggers = [75, 90]
  suspend_trigger = 100
}

resource "snowflake_warehouse" "wh_ds" {
  name                         = "WH_DS"
  warehouse_size               = "LARGE"
  auto_suspend                 = 60
  auto_resume                  = "true"
  initially_suspended          = true
  min_cluster_count            = 1
  max_cluster_count            = 1
  scaling_policy               = "STANDARD"
  statement_timeout_in_seconds = 14400
  resource_monitor             = snowflake_resource_monitor.rm_wh_ds.name
  comment                      = "workload_class=data_science"
}

resource "snowflake_resource_monitor" "rm_wh_adhoc" {
  name            = "RM_WH_ADHOC"
  credit_quota    = 300
  frequency       = "MONTHLY"
  start_timestamp = "IMMEDIATELY"
  notify_triggers = [75, 90]
  suspend_trigger = 100
}

resource "snowflake_warehouse" "wh_adhoc" {
  name                         = "WH_ADHOC"
  warehouse_size               = "XSMALL"
  auto_suspend                 = 60
  auto_resume                  = "true"
  initially_suspended          = true
  min_cluster_count            = 1
  max_cluster_count            = 2
  scaling_policy               = "ECONOMY"
  statement_timeout_in_seconds = 1800
  resource_monitor             = snowflake_resource_monitor.rm_wh_adhoc.name
  comment                      = "workload_class=adhoc"
}

resource "snowflake_resource_monitor" "rm_wh_agents" {
  name            = "RM_WH_AGENTS"
  credit_quota    = 200
  frequency       = "MONTHLY"
  start_timestamp = "IMMEDIATELY"
  notify_triggers = [50, 75, 90]
  suspend_trigger = 100
}

resource "snowflake_warehouse" "wh_agents" {
  name                         = "WH_AGENTS"
  warehouse_size               = "XSMALL"
  auto_suspend                 = 60
  auto_resume                  = "true"
  initially_suspended          = true
  min_cluster_count            = 1
  max_cluster_count            = 1
  scaling_policy               = "STANDARD"
  statement_timeout_in_seconds = 600
  resource_monitor             = snowflake_resource_monitor.rm_wh_agents.name
  comment                      = "workload_class=agents"
}

resource "snowflake_resource_monitor" "rm_account" {
  name            = "RM_ACCOUNT"
  credit_quota    = 6000
  frequency       = "MONTHLY"
  start_timestamp = "IMMEDIATELY"
  notify_triggers = [80, 95]
  suspend_trigger = 100
}

resource "snowflake_execute" "rm_account_account_level" {
  execute    = "ALTER ACCOUNT SET RESOURCE_MONITOR = RM_ACCOUNT"
  revert     = "ALTER ACCOUNT UNSET RESOURCE_MONITOR"
  depends_on = [snowflake_resource_monitor.rm_account]
}
