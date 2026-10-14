# AUTO-GENERATED — DO NOT EDIT. Source: knowledge/foundation/landing_zone.yaml. Regenerate with `altitude generate`.
resource "snowflake_account_role" "ar_dev_sales_raw_ro" {
  name    = "AR_DEV_SALES_RAW_RO"
  comment = "Access role: RO on DEV_SALES_RAW"
}

resource "snowflake_account_role" "ar_dev_sales_raw_rw" {
  name    = "AR_DEV_SALES_RAW_RW"
  comment = "Access role: RW on DEV_SALES_RAW"
}

resource "snowflake_grant_account_role" "ar_dev_sales_raw_rw_inherits_ro" {
  role_name        = snowflake_account_role.ar_dev_sales_raw_ro.name
  parent_role_name = snowflake_account_role.ar_dev_sales_raw_rw.name
}

resource "snowflake_account_role" "ar_dev_sales_conformed_ro" {
  name    = "AR_DEV_SALES_CONFORMED_RO"
  comment = "Access role: RO on DEV_SALES_CONFORMED"
}

resource "snowflake_account_role" "ar_dev_sales_conformed_rw" {
  name    = "AR_DEV_SALES_CONFORMED_RW"
  comment = "Access role: RW on DEV_SALES_CONFORMED"
}

resource "snowflake_grant_account_role" "ar_dev_sales_conformed_rw_inherits_ro" {
  role_name        = snowflake_account_role.ar_dev_sales_conformed_ro.name
  parent_role_name = snowflake_account_role.ar_dev_sales_conformed_rw.name
}

resource "snowflake_account_role" "ar_dev_sales_curated_ro" {
  name    = "AR_DEV_SALES_CURATED_RO"
  comment = "Access role: RO on DEV_SALES_CURATED"
}

resource "snowflake_account_role" "ar_dev_sales_curated_rw" {
  name    = "AR_DEV_SALES_CURATED_RW"
  comment = "Access role: RW on DEV_SALES_CURATED"
}

resource "snowflake_grant_account_role" "ar_dev_sales_curated_rw_inherits_ro" {
  role_name        = snowflake_account_role.ar_dev_sales_curated_ro.name
  parent_role_name = snowflake_account_role.ar_dev_sales_curated_rw.name
}

resource "snowflake_account_role" "ar_dev_sales_semantic_ro" {
  name    = "AR_DEV_SALES_SEMANTIC_RO"
  comment = "Access role: RO on DEV_SALES_SEMANTIC"
}

resource "snowflake_account_role" "ar_dev_sales_semantic_rw" {
  name    = "AR_DEV_SALES_SEMANTIC_RW"
  comment = "Access role: RW on DEV_SALES_SEMANTIC"
}

resource "snowflake_grant_account_role" "ar_dev_sales_semantic_rw_inherits_ro" {
  role_name        = snowflake_account_role.ar_dev_sales_semantic_ro.name
  parent_role_name = snowflake_account_role.ar_dev_sales_semantic_rw.name
}

resource "snowflake_account_role" "ar_dev_finance_raw_ro" {
  name    = "AR_DEV_FINANCE_RAW_RO"
  comment = "Access role: RO on DEV_FINANCE_RAW"
}

resource "snowflake_account_role" "ar_dev_finance_raw_rw" {
  name    = "AR_DEV_FINANCE_RAW_RW"
  comment = "Access role: RW on DEV_FINANCE_RAW"
}

resource "snowflake_grant_account_role" "ar_dev_finance_raw_rw_inherits_ro" {
  role_name        = snowflake_account_role.ar_dev_finance_raw_ro.name
  parent_role_name = snowflake_account_role.ar_dev_finance_raw_rw.name
}

resource "snowflake_account_role" "ar_dev_finance_conformed_ro" {
  name    = "AR_DEV_FINANCE_CONFORMED_RO"
  comment = "Access role: RO on DEV_FINANCE_CONFORMED"
}

resource "snowflake_account_role" "ar_dev_finance_conformed_rw" {
  name    = "AR_DEV_FINANCE_CONFORMED_RW"
  comment = "Access role: RW on DEV_FINANCE_CONFORMED"
}

resource "snowflake_grant_account_role" "ar_dev_finance_conformed_rw_inherits_ro" {
  role_name        = snowflake_account_role.ar_dev_finance_conformed_ro.name
  parent_role_name = snowflake_account_role.ar_dev_finance_conformed_rw.name
}

resource "snowflake_account_role" "ar_dev_finance_curated_ro" {
  name    = "AR_DEV_FINANCE_CURATED_RO"
  comment = "Access role: RO on DEV_FINANCE_CURATED"
}

resource "snowflake_account_role" "ar_dev_finance_curated_rw" {
  name    = "AR_DEV_FINANCE_CURATED_RW"
  comment = "Access role: RW on DEV_FINANCE_CURATED"
}

resource "snowflake_grant_account_role" "ar_dev_finance_curated_rw_inherits_ro" {
  role_name        = snowflake_account_role.ar_dev_finance_curated_ro.name
  parent_role_name = snowflake_account_role.ar_dev_finance_curated_rw.name
}

resource "snowflake_account_role" "ar_dev_finance_semantic_ro" {
  name    = "AR_DEV_FINANCE_SEMANTIC_RO"
  comment = "Access role: RO on DEV_FINANCE_SEMANTIC"
}

resource "snowflake_account_role" "ar_dev_finance_semantic_rw" {
  name    = "AR_DEV_FINANCE_SEMANTIC_RW"
  comment = "Access role: RW on DEV_FINANCE_SEMANTIC"
}

resource "snowflake_grant_account_role" "ar_dev_finance_semantic_rw_inherits_ro" {
  role_name        = snowflake_account_role.ar_dev_finance_semantic_ro.name
  parent_role_name = snowflake_account_role.ar_dev_finance_semantic_rw.name
}

resource "snowflake_account_role" "ar_prod_sales_raw_ro" {
  name    = "AR_PROD_SALES_RAW_RO"
  comment = "Access role: RO on PROD_SALES_RAW"
}

resource "snowflake_account_role" "ar_prod_sales_raw_rw" {
  name    = "AR_PROD_SALES_RAW_RW"
  comment = "Access role: RW on PROD_SALES_RAW"
}

resource "snowflake_grant_account_role" "ar_prod_sales_raw_rw_inherits_ro" {
  role_name        = snowflake_account_role.ar_prod_sales_raw_ro.name
  parent_role_name = snowflake_account_role.ar_prod_sales_raw_rw.name
}

resource "snowflake_account_role" "ar_prod_sales_conformed_ro" {
  name    = "AR_PROD_SALES_CONFORMED_RO"
  comment = "Access role: RO on PROD_SALES_CONFORMED"
}

resource "snowflake_account_role" "ar_prod_sales_conformed_rw" {
  name    = "AR_PROD_SALES_CONFORMED_RW"
  comment = "Access role: RW on PROD_SALES_CONFORMED"
}

resource "snowflake_grant_account_role" "ar_prod_sales_conformed_rw_inherits_ro" {
  role_name        = snowflake_account_role.ar_prod_sales_conformed_ro.name
  parent_role_name = snowflake_account_role.ar_prod_sales_conformed_rw.name
}

resource "snowflake_account_role" "ar_prod_sales_curated_ro" {
  name    = "AR_PROD_SALES_CURATED_RO"
  comment = "Access role: RO on PROD_SALES_CURATED"
}

resource "snowflake_account_role" "ar_prod_sales_curated_rw" {
  name    = "AR_PROD_SALES_CURATED_RW"
  comment = "Access role: RW on PROD_SALES_CURATED"
}

resource "snowflake_grant_account_role" "ar_prod_sales_curated_rw_inherits_ro" {
  role_name        = snowflake_account_role.ar_prod_sales_curated_ro.name
  parent_role_name = snowflake_account_role.ar_prod_sales_curated_rw.name
}

resource "snowflake_account_role" "ar_prod_sales_semantic_ro" {
  name    = "AR_PROD_SALES_SEMANTIC_RO"
  comment = "Access role: RO on PROD_SALES_SEMANTIC"
}

resource "snowflake_account_role" "ar_prod_sales_semantic_rw" {
  name    = "AR_PROD_SALES_SEMANTIC_RW"
  comment = "Access role: RW on PROD_SALES_SEMANTIC"
}

resource "snowflake_grant_account_role" "ar_prod_sales_semantic_rw_inherits_ro" {
  role_name        = snowflake_account_role.ar_prod_sales_semantic_ro.name
  parent_role_name = snowflake_account_role.ar_prod_sales_semantic_rw.name
}

resource "snowflake_account_role" "ar_prod_finance_raw_ro" {
  name    = "AR_PROD_FINANCE_RAW_RO"
  comment = "Access role: RO on PROD_FINANCE_RAW"
}

resource "snowflake_account_role" "ar_prod_finance_raw_rw" {
  name    = "AR_PROD_FINANCE_RAW_RW"
  comment = "Access role: RW on PROD_FINANCE_RAW"
}

resource "snowflake_grant_account_role" "ar_prod_finance_raw_rw_inherits_ro" {
  role_name        = snowflake_account_role.ar_prod_finance_raw_ro.name
  parent_role_name = snowflake_account_role.ar_prod_finance_raw_rw.name
}

resource "snowflake_account_role" "ar_prod_finance_conformed_ro" {
  name    = "AR_PROD_FINANCE_CONFORMED_RO"
  comment = "Access role: RO on PROD_FINANCE_CONFORMED"
}

resource "snowflake_account_role" "ar_prod_finance_conformed_rw" {
  name    = "AR_PROD_FINANCE_CONFORMED_RW"
  comment = "Access role: RW on PROD_FINANCE_CONFORMED"
}

resource "snowflake_grant_account_role" "ar_prod_finance_conformed_rw_inherits_ro" {
  role_name        = snowflake_account_role.ar_prod_finance_conformed_ro.name
  parent_role_name = snowflake_account_role.ar_prod_finance_conformed_rw.name
}

resource "snowflake_account_role" "ar_prod_finance_curated_ro" {
  name    = "AR_PROD_FINANCE_CURATED_RO"
  comment = "Access role: RO on PROD_FINANCE_CURATED"
}

resource "snowflake_account_role" "ar_prod_finance_curated_rw" {
  name    = "AR_PROD_FINANCE_CURATED_RW"
  comment = "Access role: RW on PROD_FINANCE_CURATED"
}

resource "snowflake_grant_account_role" "ar_prod_finance_curated_rw_inherits_ro" {
  role_name        = snowflake_account_role.ar_prod_finance_curated_ro.name
  parent_role_name = snowflake_account_role.ar_prod_finance_curated_rw.name
}

resource "snowflake_account_role" "ar_prod_finance_semantic_ro" {
  name    = "AR_PROD_FINANCE_SEMANTIC_RO"
  comment = "Access role: RO on PROD_FINANCE_SEMANTIC"
}

resource "snowflake_account_role" "ar_prod_finance_semantic_rw" {
  name    = "AR_PROD_FINANCE_SEMANTIC_RW"
  comment = "Access role: RW on PROD_FINANCE_SEMANTIC"
}

resource "snowflake_grant_account_role" "ar_prod_finance_semantic_rw_inherits_ro" {
  role_name        = snowflake_account_role.ar_prod_finance_semantic_ro.name
  parent_role_name = snowflake_account_role.ar_prod_finance_semantic_rw.name
}

resource "snowflake_account_role" "fr_engineer" {
  name    = "FR_ENGINEER"
  comment = "Functional role: Data engineers and pipeline service users"
}

resource "snowflake_grant_account_role" "fr_engineer_to_sysadmin" {
  role_name        = snowflake_account_role.fr_engineer.name
  parent_role_name = "SYSADMIN"
}

resource "snowflake_grant_account_role" "ar_dev_sales_raw_rw_to_fr_engineer" {
  role_name        = snowflake_account_role.ar_dev_sales_raw_rw.name
  parent_role_name = snowflake_account_role.fr_engineer.name
}

resource "snowflake_grant_account_role" "ar_dev_sales_conformed_rw_to_fr_engineer" {
  role_name        = snowflake_account_role.ar_dev_sales_conformed_rw.name
  parent_role_name = snowflake_account_role.fr_engineer.name
}

resource "snowflake_grant_account_role" "ar_dev_sales_curated_rw_to_fr_engineer" {
  role_name        = snowflake_account_role.ar_dev_sales_curated_rw.name
  parent_role_name = snowflake_account_role.fr_engineer.name
}

resource "snowflake_grant_account_role" "ar_dev_sales_semantic_rw_to_fr_engineer" {
  role_name        = snowflake_account_role.ar_dev_sales_semantic_rw.name
  parent_role_name = snowflake_account_role.fr_engineer.name
}

resource "snowflake_grant_account_role" "ar_dev_finance_raw_rw_to_fr_engineer" {
  role_name        = snowflake_account_role.ar_dev_finance_raw_rw.name
  parent_role_name = snowflake_account_role.fr_engineer.name
}

resource "snowflake_grant_account_role" "ar_dev_finance_conformed_rw_to_fr_engineer" {
  role_name        = snowflake_account_role.ar_dev_finance_conformed_rw.name
  parent_role_name = snowflake_account_role.fr_engineer.name
}

resource "snowflake_grant_account_role" "ar_dev_finance_curated_rw_to_fr_engineer" {
  role_name        = snowflake_account_role.ar_dev_finance_curated_rw.name
  parent_role_name = snowflake_account_role.fr_engineer.name
}

resource "snowflake_grant_account_role" "ar_dev_finance_semantic_rw_to_fr_engineer" {
  role_name        = snowflake_account_role.ar_dev_finance_semantic_rw.name
  parent_role_name = snowflake_account_role.fr_engineer.name
}

resource "snowflake_grant_account_role" "ar_prod_sales_raw_rw_to_fr_engineer" {
  role_name        = snowflake_account_role.ar_prod_sales_raw_rw.name
  parent_role_name = snowflake_account_role.fr_engineer.name
}

resource "snowflake_grant_account_role" "ar_prod_sales_conformed_rw_to_fr_engineer" {
  role_name        = snowflake_account_role.ar_prod_sales_conformed_rw.name
  parent_role_name = snowflake_account_role.fr_engineer.name
}

resource "snowflake_grant_account_role" "ar_prod_sales_curated_rw_to_fr_engineer" {
  role_name        = snowflake_account_role.ar_prod_sales_curated_rw.name
  parent_role_name = snowflake_account_role.fr_engineer.name
}

resource "snowflake_grant_account_role" "ar_prod_sales_semantic_rw_to_fr_engineer" {
  role_name        = snowflake_account_role.ar_prod_sales_semantic_rw.name
  parent_role_name = snowflake_account_role.fr_engineer.name
}

resource "snowflake_grant_account_role" "ar_prod_finance_raw_rw_to_fr_engineer" {
  role_name        = snowflake_account_role.ar_prod_finance_raw_rw.name
  parent_role_name = snowflake_account_role.fr_engineer.name
}

resource "snowflake_grant_account_role" "ar_prod_finance_conformed_rw_to_fr_engineer" {
  role_name        = snowflake_account_role.ar_prod_finance_conformed_rw.name
  parent_role_name = snowflake_account_role.fr_engineer.name
}

resource "snowflake_grant_account_role" "ar_prod_finance_curated_rw_to_fr_engineer" {
  role_name        = snowflake_account_role.ar_prod_finance_curated_rw.name
  parent_role_name = snowflake_account_role.fr_engineer.name
}

resource "snowflake_grant_account_role" "ar_prod_finance_semantic_rw_to_fr_engineer" {
  role_name        = snowflake_account_role.ar_prod_finance_semantic_rw.name
  parent_role_name = snowflake_account_role.fr_engineer.name
}

resource "snowflake_account_role" "fr_analyst" {
  name    = "FR_ANALYST"
  comment = "Functional role: Analysts \u2014 curated and semantic layers, read-only, production"
}

resource "snowflake_grant_account_role" "fr_analyst_to_sysadmin" {
  role_name        = snowflake_account_role.fr_analyst.name
  parent_role_name = "SYSADMIN"
}

resource "snowflake_grant_account_role" "ar_prod_sales_curated_ro_to_fr_analyst" {
  role_name        = snowflake_account_role.ar_prod_sales_curated_ro.name
  parent_role_name = snowflake_account_role.fr_analyst.name
}

resource "snowflake_grant_account_role" "ar_prod_finance_curated_ro_to_fr_analyst" {
  role_name        = snowflake_account_role.ar_prod_finance_curated_ro.name
  parent_role_name = snowflake_account_role.fr_analyst.name
}

resource "snowflake_grant_account_role" "ar_prod_sales_semantic_ro_to_fr_analyst" {
  role_name        = snowflake_account_role.ar_prod_sales_semantic_ro.name
  parent_role_name = snowflake_account_role.fr_analyst.name
}

resource "snowflake_grant_account_role" "ar_prod_finance_semantic_ro_to_fr_analyst" {
  role_name        = snowflake_account_role.ar_prod_finance_semantic_ro.name
  parent_role_name = snowflake_account_role.fr_analyst.name
}

resource "snowflake_account_role" "fr_bi" {
  name    = "FR_BI"
  comment = "Functional role: BI service accounts \u2014 semantic layer only"
}

resource "snowflake_grant_account_role" "fr_bi_to_sysadmin" {
  role_name        = snowflake_account_role.fr_bi.name
  parent_role_name = "SYSADMIN"
}

resource "snowflake_grant_account_role" "ar_prod_sales_semantic_ro_to_fr_bi" {
  role_name        = snowflake_account_role.ar_prod_sales_semantic_ro.name
  parent_role_name = snowflake_account_role.fr_bi.name
}

resource "snowflake_grant_account_role" "ar_prod_finance_semantic_ro_to_fr_bi" {
  role_name        = snowflake_account_role.ar_prod_finance_semantic_ro.name
  parent_role_name = snowflake_account_role.fr_bi.name
}

resource "snowflake_account_role" "fr_data_scientist" {
  name    = "FR_DATA_SCIENTIST"
  comment = "Functional role: Data science \u2014 conformed and curated, read-only"
}

resource "snowflake_grant_account_role" "fr_data_scientist_to_sysadmin" {
  role_name        = snowflake_account_role.fr_data_scientist.name
  parent_role_name = "SYSADMIN"
}

resource "snowflake_grant_account_role" "ar_prod_sales_conformed_ro_to_fr_data_scientist" {
  role_name        = snowflake_account_role.ar_prod_sales_conformed_ro.name
  parent_role_name = snowflake_account_role.fr_data_scientist.name
}

resource "snowflake_grant_account_role" "ar_prod_finance_conformed_ro_to_fr_data_scientist" {
  role_name        = snowflake_account_role.ar_prod_finance_conformed_ro.name
  parent_role_name = snowflake_account_role.fr_data_scientist.name
}

resource "snowflake_grant_account_role" "ar_prod_sales_curated_ro_to_fr_data_scientist" {
  role_name        = snowflake_account_role.ar_prod_sales_curated_ro.name
  parent_role_name = snowflake_account_role.fr_data_scientist.name
}

resource "snowflake_grant_account_role" "ar_prod_finance_curated_ro_to_fr_data_scientist" {
  role_name        = snowflake_account_role.ar_prod_finance_curated_ro.name
  parent_role_name = snowflake_account_role.fr_data_scientist.name
}

resource "snowflake_account_role" "fr_privacy_officer" {
  name    = "FR_PRIVACY_OFFICER"
  comment = "Functional role: Sees unmasked PII (tag-based masking exemption)"
}

resource "snowflake_grant_account_role" "fr_privacy_officer_to_sysadmin" {
  role_name        = snowflake_account_role.fr_privacy_officer.name
  parent_role_name = "SYSADMIN"
}

resource "snowflake_grant_account_role" "ar_prod_sales_curated_ro_to_fr_privacy_officer" {
  role_name        = snowflake_account_role.ar_prod_sales_curated_ro.name
  parent_role_name = snowflake_account_role.fr_privacy_officer.name
}

resource "snowflake_grant_account_role" "ar_prod_finance_curated_ro_to_fr_privacy_officer" {
  role_name        = snowflake_account_role.ar_prod_finance_curated_ro.name
  parent_role_name = snowflake_account_role.fr_privacy_officer.name
}

resource "snowflake_account_role" "fr_governance_admin" {
  name    = "FR_GOVERNANCE_ADMIN"
  comment = "Functional role: Owns tags, masking and network policies"
}

resource "snowflake_grant_account_role" "fr_governance_admin_to_sysadmin" {
  role_name        = snowflake_account_role.fr_governance_admin.name
  parent_role_name = "SYSADMIN"
}
