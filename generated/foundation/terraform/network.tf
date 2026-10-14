# AUTO-GENERATED — DO NOT EDIT. Source: knowledge/foundation/landing_zone.yaml. Regenerate with `altitude generate`.
resource "snowflake_network_rule" "nr_corporate" {
  name       = "NR_CORPORATE"
  database   = snowflake_database.governance.name
  schema     = snowflake_schema.governance_network.name
  type       = "IPV4"
  mode       = "INGRESS"
  value_list = ["10.0.0.0/8"]
}

resource "snowflake_network_rule" "nr_services" {
  name       = "NR_SERVICES"
  database   = snowflake_database.governance.name
  schema     = snowflake_schema.governance_network.name
  type       = "IPV4"
  mode       = "INGRESS"
  value_list = ["10.20.0.0/16"]
}

resource "snowflake_network_policy" "np_account" {
  name                      = "NP_ACCOUNT"
  allowed_network_rule_list = [snowflake_network_rule.nr_corporate.fully_qualified_name]
}

resource "snowflake_account_parameter" "network_policy" {
  key   = "NETWORK_POLICY"
  value = snowflake_network_policy.np_account.name
}

resource "snowflake_network_policy" "np_services" {
  name                      = "NP_SERVICES"
  allowed_network_rule_list = [snowflake_network_rule.nr_services.fully_qualified_name]
}
