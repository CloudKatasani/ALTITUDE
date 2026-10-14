# AUTO-GENERATED — DO NOT EDIT. Source: knowledge/foundation/landing_zone.yaml. Regenerate with `altitude generate`.
resource "snowflake_database" "governance" {
  name    = "GOVERNANCE"
  comment = "Platform governance: tags, policies, network rules"
}

resource "snowflake_schema" "governance_network" {
  database            = snowflake_database.governance.name
  name                = "NETWORK"
  with_managed_access = "true"
}

resource "snowflake_schema" "governance_policies" {
  database            = snowflake_database.governance.name
  name                = "POLICIES"
  with_managed_access = "true"
}

resource "snowflake_schema" "governance_tags" {
  database            = snowflake_database.governance.name
  name                = "TAGS"
  with_managed_access = "true"
}

resource "snowflake_database" "dev_sales_raw" {
  name                        = "DEV_SALES_RAW"
  data_retention_time_in_days = 7
  comment                     = "DEV SALES RAW layer; owner sales-data@example.com"
}

resource "snowflake_schema" "dev_sales_raw_core" {
  database            = snowflake_database.dev_sales_raw.name
  name                = "CORE"
  with_managed_access = "false"
}

resource "snowflake_schema" "dev_sales_raw_staging" {
  database                    = snowflake_database.dev_sales_raw.name
  name                        = "STAGING"
  with_managed_access         = "false"
  is_transient                = "true"
  data_retention_time_in_days = 0
}

resource "snowflake_database" "dev_sales_conformed" {
  name                        = "DEV_SALES_CONFORMED"
  data_retention_time_in_days = 1
  comment                     = "DEV SALES CONFORMED layer; owner sales-data@example.com"
}

resource "snowflake_schema" "dev_sales_conformed_core" {
  database            = snowflake_database.dev_sales_conformed.name
  name                = "CORE"
  with_managed_access = "false"
}

resource "snowflake_schema" "dev_sales_conformed_staging" {
  database                    = snowflake_database.dev_sales_conformed.name
  name                        = "STAGING"
  with_managed_access         = "false"
  is_transient                = "true"
  data_retention_time_in_days = 0
}

resource "snowflake_database" "dev_sales_curated" {
  name                        = "DEV_SALES_CURATED"
  data_retention_time_in_days = 1
  comment                     = "DEV SALES CURATED layer; owner sales-data@example.com"
}

resource "snowflake_schema" "dev_sales_curated_core" {
  database            = snowflake_database.dev_sales_curated.name
  name                = "CORE"
  with_managed_access = "false"
}

resource "snowflake_schema" "dev_sales_curated_staging" {
  database                    = snowflake_database.dev_sales_curated.name
  name                        = "STAGING"
  with_managed_access         = "false"
  is_transient                = "true"
  data_retention_time_in_days = 0
}

resource "snowflake_database" "dev_sales_semantic" {
  name                        = "DEV_SALES_SEMANTIC"
  data_retention_time_in_days = 1
  comment                     = "DEV SALES SEMANTIC layer; owner sales-data@example.com"
}

resource "snowflake_schema" "dev_sales_semantic_core" {
  database            = snowflake_database.dev_sales_semantic.name
  name                = "CORE"
  with_managed_access = "false"
}

resource "snowflake_schema" "dev_sales_semantic_staging" {
  database                    = snowflake_database.dev_sales_semantic.name
  name                        = "STAGING"
  with_managed_access         = "false"
  is_transient                = "true"
  data_retention_time_in_days = 0
}

resource "snowflake_database" "dev_finance_raw" {
  name                        = "DEV_FINANCE_RAW"
  data_retention_time_in_days = 7
  comment                     = "DEV FINANCE RAW layer; owner finance-data@example.com"
}

resource "snowflake_schema" "dev_finance_raw_core" {
  database            = snowflake_database.dev_finance_raw.name
  name                = "CORE"
  with_managed_access = "false"
}

resource "snowflake_schema" "dev_finance_raw_staging" {
  database                    = snowflake_database.dev_finance_raw.name
  name                        = "STAGING"
  with_managed_access         = "false"
  is_transient                = "true"
  data_retention_time_in_days = 0
}

resource "snowflake_database" "dev_finance_conformed" {
  name                        = "DEV_FINANCE_CONFORMED"
  data_retention_time_in_days = 1
  comment                     = "DEV FINANCE CONFORMED layer; owner finance-data@example.com"
}

resource "snowflake_schema" "dev_finance_conformed_core" {
  database            = snowflake_database.dev_finance_conformed.name
  name                = "CORE"
  with_managed_access = "false"
}

resource "snowflake_schema" "dev_finance_conformed_staging" {
  database                    = snowflake_database.dev_finance_conformed.name
  name                        = "STAGING"
  with_managed_access         = "false"
  is_transient                = "true"
  data_retention_time_in_days = 0
}

resource "snowflake_database" "dev_finance_curated" {
  name                        = "DEV_FINANCE_CURATED"
  data_retention_time_in_days = 1
  comment                     = "DEV FINANCE CURATED layer; owner finance-data@example.com"
}

resource "snowflake_schema" "dev_finance_curated_core" {
  database            = snowflake_database.dev_finance_curated.name
  name                = "CORE"
  with_managed_access = "false"
}

resource "snowflake_schema" "dev_finance_curated_staging" {
  database                    = snowflake_database.dev_finance_curated.name
  name                        = "STAGING"
  with_managed_access         = "false"
  is_transient                = "true"
  data_retention_time_in_days = 0
}

resource "snowflake_database" "dev_finance_semantic" {
  name                        = "DEV_FINANCE_SEMANTIC"
  data_retention_time_in_days = 1
  comment                     = "DEV FINANCE SEMANTIC layer; owner finance-data@example.com"
}

resource "snowflake_schema" "dev_finance_semantic_core" {
  database            = snowflake_database.dev_finance_semantic.name
  name                = "CORE"
  with_managed_access = "false"
}

resource "snowflake_schema" "dev_finance_semantic_staging" {
  database                    = snowflake_database.dev_finance_semantic.name
  name                        = "STAGING"
  with_managed_access         = "false"
  is_transient                = "true"
  data_retention_time_in_days = 0
}

resource "snowflake_database" "prod_sales_raw" {
  name                        = "PROD_SALES_RAW"
  data_retention_time_in_days = 7
  comment                     = "PROD SALES RAW layer; owner sales-data@example.com"
}

resource "snowflake_schema" "prod_sales_raw_core" {
  database            = snowflake_database.prod_sales_raw.name
  name                = "CORE"
  with_managed_access = "true"
}

resource "snowflake_schema" "prod_sales_raw_staging" {
  database                    = snowflake_database.prod_sales_raw.name
  name                        = "STAGING"
  with_managed_access         = "true"
  is_transient                = "true"
  data_retention_time_in_days = 0
}

resource "snowflake_database" "prod_sales_conformed" {
  name                        = "PROD_SALES_CONFORMED"
  data_retention_time_in_days = 1
  comment                     = "PROD SALES CONFORMED layer; owner sales-data@example.com"
}

resource "snowflake_schema" "prod_sales_conformed_core" {
  database            = snowflake_database.prod_sales_conformed.name
  name                = "CORE"
  with_managed_access = "true"
}

resource "snowflake_schema" "prod_sales_conformed_staging" {
  database                    = snowflake_database.prod_sales_conformed.name
  name                        = "STAGING"
  with_managed_access         = "true"
  is_transient                = "true"
  data_retention_time_in_days = 0
}

resource "snowflake_database" "prod_sales_curated" {
  name                        = "PROD_SALES_CURATED"
  data_retention_time_in_days = 1
  comment                     = "PROD SALES CURATED layer; owner sales-data@example.com"
}

resource "snowflake_schema" "prod_sales_curated_core" {
  database            = snowflake_database.prod_sales_curated.name
  name                = "CORE"
  with_managed_access = "true"
}

resource "snowflake_schema" "prod_sales_curated_staging" {
  database                    = snowflake_database.prod_sales_curated.name
  name                        = "STAGING"
  with_managed_access         = "true"
  is_transient                = "true"
  data_retention_time_in_days = 0
}

resource "snowflake_database" "prod_sales_semantic" {
  name                        = "PROD_SALES_SEMANTIC"
  data_retention_time_in_days = 1
  comment                     = "PROD SALES SEMANTIC layer; owner sales-data@example.com"
}

resource "snowflake_schema" "prod_sales_semantic_core" {
  database            = snowflake_database.prod_sales_semantic.name
  name                = "CORE"
  with_managed_access = "true"
}

resource "snowflake_schema" "prod_sales_semantic_staging" {
  database                    = snowflake_database.prod_sales_semantic.name
  name                        = "STAGING"
  with_managed_access         = "true"
  is_transient                = "true"
  data_retention_time_in_days = 0
}

resource "snowflake_database" "prod_finance_raw" {
  name                        = "PROD_FINANCE_RAW"
  data_retention_time_in_days = 7
  comment                     = "PROD FINANCE RAW layer; owner finance-data@example.com"
}

resource "snowflake_schema" "prod_finance_raw_core" {
  database            = snowflake_database.prod_finance_raw.name
  name                = "CORE"
  with_managed_access = "true"
}

resource "snowflake_schema" "prod_finance_raw_staging" {
  database                    = snowflake_database.prod_finance_raw.name
  name                        = "STAGING"
  with_managed_access         = "true"
  is_transient                = "true"
  data_retention_time_in_days = 0
}

resource "snowflake_database" "prod_finance_conformed" {
  name                        = "PROD_FINANCE_CONFORMED"
  data_retention_time_in_days = 1
  comment                     = "PROD FINANCE CONFORMED layer; owner finance-data@example.com"
}

resource "snowflake_schema" "prod_finance_conformed_core" {
  database            = snowflake_database.prod_finance_conformed.name
  name                = "CORE"
  with_managed_access = "true"
}

resource "snowflake_schema" "prod_finance_conformed_staging" {
  database                    = snowflake_database.prod_finance_conformed.name
  name                        = "STAGING"
  with_managed_access         = "true"
  is_transient                = "true"
  data_retention_time_in_days = 0
}

resource "snowflake_database" "prod_finance_curated" {
  name                        = "PROD_FINANCE_CURATED"
  data_retention_time_in_days = 1
  comment                     = "PROD FINANCE CURATED layer; owner finance-data@example.com"
}

resource "snowflake_schema" "prod_finance_curated_core" {
  database            = snowflake_database.prod_finance_curated.name
  name                = "CORE"
  with_managed_access = "true"
}

resource "snowflake_schema" "prod_finance_curated_staging" {
  database                    = snowflake_database.prod_finance_curated.name
  name                        = "STAGING"
  with_managed_access         = "true"
  is_transient                = "true"
  data_retention_time_in_days = 0
}

resource "snowflake_database" "prod_finance_semantic" {
  name                        = "PROD_FINANCE_SEMANTIC"
  data_retention_time_in_days = 1
  comment                     = "PROD FINANCE SEMANTIC layer; owner finance-data@example.com"
}

resource "snowflake_schema" "prod_finance_semantic_core" {
  database            = snowflake_database.prod_finance_semantic.name
  name                = "CORE"
  with_managed_access = "true"
}

resource "snowflake_schema" "prod_finance_semantic_staging" {
  database                    = snowflake_database.prod_finance_semantic.name
  name                        = "STAGING"
  with_managed_access         = "true"
  is_transient                = "true"
  data_retention_time_in_days = 0
}
