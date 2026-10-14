# AUTO-GENERATED — DO NOT EDIT. Source: knowledge/foundation/landing_zone.yaml. Regenerate with `altitude generate`.
terraform {
  required_version = ">= 1.6"
  required_providers {
    snowflake = { source = "snowflakedb/snowflake", version = "~> 2.0" }
  }
}

provider "snowflake" {
  organization_name        = var.organization_name
  account_name             = var.account_name
  user                     = var.terraform_user
  role                     = var.terraform_role
  authenticator            = "SNOWFLAKE_JWT"
  private_key              = var.private_key
  preview_features_enabled = ["snowflake_network_rule_resource", "snowflake_execute_resource", "snowflake_tag_association_resource", "snowflake_tag_masking_policy_association_resource"]
}
