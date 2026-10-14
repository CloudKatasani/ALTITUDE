# AUTO-GENERATED — DO NOT EDIT. Source: knowledge/foundation/landing_zone.yaml. Regenerate with `altitude generate`.
resource "snowflake_tag_association" "wh_elt_cost_center" {
  object_identifiers = [snowflake_warehouse.wh_elt.fully_qualified_name]
  object_type        = "WAREHOUSE"
  tag_id             = snowflake_tag.cost_center.fully_qualified_name
  tag_value          = "DATA_PLATFORM"
}

resource "snowflake_tag_association" "wh_bi_cost_center" {
  object_identifiers = [snowflake_warehouse.wh_bi.fully_qualified_name]
  object_type        = "WAREHOUSE"
  tag_id             = snowflake_tag.cost_center.fully_qualified_name
  tag_value          = "FINANCE_BI"
}

resource "snowflake_tag_association" "wh_ds_cost_center" {
  object_identifiers = [snowflake_warehouse.wh_ds.fully_qualified_name]
  object_type        = "WAREHOUSE"
  tag_id             = snowflake_tag.cost_center.fully_qualified_name
  tag_value          = "DATA_SCIENCE"
}

resource "snowflake_tag_association" "wh_adhoc_cost_center" {
  object_identifiers = [snowflake_warehouse.wh_adhoc.fully_qualified_name]
  object_type        = "WAREHOUSE"
  tag_id             = snowflake_tag.cost_center.fully_qualified_name
  tag_value          = "ANALYTICS"
}

resource "snowflake_tag_association" "wh_agents_cost_center" {
  object_identifiers = [snowflake_warehouse.wh_agents.fully_qualified_name]
  object_type        = "WAREHOUSE"
  tag_id             = snowflake_tag.cost_center.fully_qualified_name
  tag_value          = "AI_PLATFORM"
}

resource "snowflake_tag" "pii" {
  name           = "PII"
  database       = snowflake_database.governance.name
  schema         = snowflake_schema.governance_tags.name
  allowed_values = ["email", "phone", "ssn", "name", "address", "dob"]
}

resource "snowflake_tag" "cost_center" {
  name           = "COST_CENTER"
  database       = snowflake_database.governance.name
  schema         = snowflake_schema.governance_tags.name
  allowed_values = ["DATA_PLATFORM", "FINANCE_BI", "DATA_SCIENCE", "ANALYTICS", "AI_PLATFORM", "SALES_ANALYTICS"]
}

resource "snowflake_tag" "data_owner" {
  name     = "DATA_OWNER"
  database = snowflake_database.governance.name
  schema   = snowflake_schema.governance_tags.name
}

resource "snowflake_tag" "tier" {
  name           = "TIER"
  database       = snowflake_database.governance.name
  schema         = snowflake_schema.governance_tags.name
  allowed_values = ["tier1", "tier2", "tier3"]
}

resource "snowflake_tag" "dq_status" {
  name           = "DQ_STATUS"
  database       = snowflake_database.governance.name
  schema         = snowflake_schema.governance_tags.name
  allowed_values = ["QUARANTINED"]
}

resource "snowflake_tag" "idempotent" {
  name           = "IDEMPOTENT"
  database       = snowflake_database.governance.name
  schema         = snowflake_schema.governance_tags.name
  allowed_values = ["true", "false"]
}

resource "snowflake_masking_policy" "mp_pii_string" {
  name             = "MP_PII_STRING"
  database         = snowflake_database.governance.name
  schema           = snowflake_schema.governance_policies.name
  argument {
    name = "VAL"
    type = "VARCHAR"
  }
  return_data_type = "VARCHAR"
  body             = "CASE WHEN IS_ROLE_IN_SESSION('FR_PRIVACY_OFFICER') THEN VAL ELSE '***MASKED***' END"
  comment          = "Tag-based masking: every column tagged PII is masked mechanically"
}

resource "snowflake_tag_masking_policy_association" "pii_mp_pii_string" {
  tag_id            = snowflake_tag.pii.fully_qualified_name
  masking_policy_id = snowflake_masking_policy.mp_pii_string.fully_qualified_name
}

resource "snowflake_tag_association" "dev_sales_raw_owner" {
  object_identifiers = [snowflake_database.dev_sales_raw.fully_qualified_name]
  object_type        = "DATABASE"
  tag_id             = snowflake_tag.data_owner.fully_qualified_name
  tag_value          = "sales-data@example.com"
}

resource "snowflake_tag_association" "dev_sales_conformed_owner" {
  object_identifiers = [snowflake_database.dev_sales_conformed.fully_qualified_name]
  object_type        = "DATABASE"
  tag_id             = snowflake_tag.data_owner.fully_qualified_name
  tag_value          = "sales-data@example.com"
}

resource "snowflake_tag_association" "dev_sales_curated_owner" {
  object_identifiers = [snowflake_database.dev_sales_curated.fully_qualified_name]
  object_type        = "DATABASE"
  tag_id             = snowflake_tag.data_owner.fully_qualified_name
  tag_value          = "sales-data@example.com"
}

resource "snowflake_tag_association" "dev_sales_semantic_owner" {
  object_identifiers = [snowflake_database.dev_sales_semantic.fully_qualified_name]
  object_type        = "DATABASE"
  tag_id             = snowflake_tag.data_owner.fully_qualified_name
  tag_value          = "sales-data@example.com"
}

resource "snowflake_tag_association" "dev_finance_raw_owner" {
  object_identifiers = [snowflake_database.dev_finance_raw.fully_qualified_name]
  object_type        = "DATABASE"
  tag_id             = snowflake_tag.data_owner.fully_qualified_name
  tag_value          = "finance-data@example.com"
}

resource "snowflake_tag_association" "dev_finance_conformed_owner" {
  object_identifiers = [snowflake_database.dev_finance_conformed.fully_qualified_name]
  object_type        = "DATABASE"
  tag_id             = snowflake_tag.data_owner.fully_qualified_name
  tag_value          = "finance-data@example.com"
}

resource "snowflake_tag_association" "dev_finance_curated_owner" {
  object_identifiers = [snowflake_database.dev_finance_curated.fully_qualified_name]
  object_type        = "DATABASE"
  tag_id             = snowflake_tag.data_owner.fully_qualified_name
  tag_value          = "finance-data@example.com"
}

resource "snowflake_tag_association" "dev_finance_semantic_owner" {
  object_identifiers = [snowflake_database.dev_finance_semantic.fully_qualified_name]
  object_type        = "DATABASE"
  tag_id             = snowflake_tag.data_owner.fully_qualified_name
  tag_value          = "finance-data@example.com"
}

resource "snowflake_tag_association" "prod_sales_raw_owner" {
  object_identifiers = [snowflake_database.prod_sales_raw.fully_qualified_name]
  object_type        = "DATABASE"
  tag_id             = snowflake_tag.data_owner.fully_qualified_name
  tag_value          = "sales-data@example.com"
}

resource "snowflake_tag_association" "prod_sales_conformed_owner" {
  object_identifiers = [snowflake_database.prod_sales_conformed.fully_qualified_name]
  object_type        = "DATABASE"
  tag_id             = snowflake_tag.data_owner.fully_qualified_name
  tag_value          = "sales-data@example.com"
}

resource "snowflake_tag_association" "prod_sales_curated_owner" {
  object_identifiers = [snowflake_database.prod_sales_curated.fully_qualified_name]
  object_type        = "DATABASE"
  tag_id             = snowflake_tag.data_owner.fully_qualified_name
  tag_value          = "sales-data@example.com"
}

resource "snowflake_tag_association" "prod_sales_semantic_owner" {
  object_identifiers = [snowflake_database.prod_sales_semantic.fully_qualified_name]
  object_type        = "DATABASE"
  tag_id             = snowflake_tag.data_owner.fully_qualified_name
  tag_value          = "sales-data@example.com"
}

resource "snowflake_tag_association" "prod_finance_raw_owner" {
  object_identifiers = [snowflake_database.prod_finance_raw.fully_qualified_name]
  object_type        = "DATABASE"
  tag_id             = snowflake_tag.data_owner.fully_qualified_name
  tag_value          = "finance-data@example.com"
}

resource "snowflake_tag_association" "prod_finance_conformed_owner" {
  object_identifiers = [snowflake_database.prod_finance_conformed.fully_qualified_name]
  object_type        = "DATABASE"
  tag_id             = snowflake_tag.data_owner.fully_qualified_name
  tag_value          = "finance-data@example.com"
}

resource "snowflake_tag_association" "prod_finance_curated_owner" {
  object_identifiers = [snowflake_database.prod_finance_curated.fully_qualified_name]
  object_type        = "DATABASE"
  tag_id             = snowflake_tag.data_owner.fully_qualified_name
  tag_value          = "finance-data@example.com"
}

resource "snowflake_tag_association" "prod_finance_semantic_owner" {
  object_identifiers = [snowflake_database.prod_finance_semantic.fully_qualified_name]
  object_type        = "DATABASE"
  tag_id             = snowflake_tag.data_owner.fully_qualified_name
  tag_value          = "finance-data@example.com"
}
