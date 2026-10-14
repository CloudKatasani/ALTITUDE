# AUTO-GENERATED — DO NOT EDIT. Source: knowledge/foundation/landing_zone.yaml. Regenerate with `altitude generate`.
resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_raw_ro_db" {
  account_role_name = snowflake_account_role.ar_dev_sales_raw_ro.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.dev_sales_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_raw_ro_schemas" {
  account_role_name = snowflake_account_role.ar_dev_sales_raw_ro.name
  privileges        = ["USAGE"]
  on_schema {
    all_schemas_in_database = snowflake_database.dev_sales_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_raw_ro_future_schemas" {
  account_role_name = snowflake_account_role.ar_dev_sales_raw_ro.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = snowflake_database.dev_sales_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_raw_ro_future_semantic_views" {
  account_role_name = snowflake_account_role.ar_dev_sales_raw_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "SEMANTIC VIEWS"
      in_database        = snowflake_database.dev_sales_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_raw_ro_future_tables" {
  account_role_name = snowflake_account_role.ar_dev_sales_raw_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.dev_sales_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_raw_ro_future_views" {
  account_role_name = snowflake_account_role.ar_dev_sales_raw_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.dev_sales_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_raw_rw_db" {
  account_role_name = snowflake_account_role.ar_dev_sales_raw_rw.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.dev_sales_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_raw_rw_schemas" {
  account_role_name = snowflake_account_role.ar_dev_sales_raw_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    all_schemas_in_database = snowflake_database.dev_sales_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_raw_rw_future_schemas" {
  account_role_name = snowflake_account_role.ar_dev_sales_raw_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    future_schemas_in_database = snowflake_database.dev_sales_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_raw_rw_future_tables" {
  account_role_name = snowflake_account_role.ar_dev_sales_raw_rw.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.dev_sales_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_raw_rw_future_views" {
  account_role_name = snowflake_account_role.ar_dev_sales_raw_rw.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.dev_sales_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_conformed_ro_db" {
  account_role_name = snowflake_account_role.ar_dev_sales_conformed_ro.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.dev_sales_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_conformed_ro_schemas" {
  account_role_name = snowflake_account_role.ar_dev_sales_conformed_ro.name
  privileges        = ["USAGE"]
  on_schema {
    all_schemas_in_database = snowflake_database.dev_sales_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_conformed_ro_future_schemas" {
  account_role_name = snowflake_account_role.ar_dev_sales_conformed_ro.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = snowflake_database.dev_sales_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_conformed_ro_future_semantic_views" {
  account_role_name = snowflake_account_role.ar_dev_sales_conformed_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "SEMANTIC VIEWS"
      in_database        = snowflake_database.dev_sales_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_conformed_ro_future_tables" {
  account_role_name = snowflake_account_role.ar_dev_sales_conformed_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.dev_sales_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_conformed_ro_future_views" {
  account_role_name = snowflake_account_role.ar_dev_sales_conformed_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.dev_sales_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_conformed_rw_db" {
  account_role_name = snowflake_account_role.ar_dev_sales_conformed_rw.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.dev_sales_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_conformed_rw_schemas" {
  account_role_name = snowflake_account_role.ar_dev_sales_conformed_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    all_schemas_in_database = snowflake_database.dev_sales_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_conformed_rw_future_schemas" {
  account_role_name = snowflake_account_role.ar_dev_sales_conformed_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    future_schemas_in_database = snowflake_database.dev_sales_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_conformed_rw_future_tables" {
  account_role_name = snowflake_account_role.ar_dev_sales_conformed_rw.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.dev_sales_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_conformed_rw_future_views" {
  account_role_name = snowflake_account_role.ar_dev_sales_conformed_rw.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.dev_sales_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_curated_ro_db" {
  account_role_name = snowflake_account_role.ar_dev_sales_curated_ro.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.dev_sales_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_curated_ro_schemas" {
  account_role_name = snowflake_account_role.ar_dev_sales_curated_ro.name
  privileges        = ["USAGE"]
  on_schema {
    all_schemas_in_database = snowflake_database.dev_sales_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_curated_ro_future_schemas" {
  account_role_name = snowflake_account_role.ar_dev_sales_curated_ro.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = snowflake_database.dev_sales_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_curated_ro_future_semantic_views" {
  account_role_name = snowflake_account_role.ar_dev_sales_curated_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "SEMANTIC VIEWS"
      in_database        = snowflake_database.dev_sales_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_curated_ro_future_tables" {
  account_role_name = snowflake_account_role.ar_dev_sales_curated_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.dev_sales_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_curated_ro_future_views" {
  account_role_name = snowflake_account_role.ar_dev_sales_curated_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.dev_sales_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_curated_rw_db" {
  account_role_name = snowflake_account_role.ar_dev_sales_curated_rw.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.dev_sales_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_curated_rw_schemas" {
  account_role_name = snowflake_account_role.ar_dev_sales_curated_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    all_schemas_in_database = snowflake_database.dev_sales_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_curated_rw_future_schemas" {
  account_role_name = snowflake_account_role.ar_dev_sales_curated_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    future_schemas_in_database = snowflake_database.dev_sales_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_curated_rw_future_tables" {
  account_role_name = snowflake_account_role.ar_dev_sales_curated_rw.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.dev_sales_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_curated_rw_future_views" {
  account_role_name = snowflake_account_role.ar_dev_sales_curated_rw.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.dev_sales_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_semantic_ro_db" {
  account_role_name = snowflake_account_role.ar_dev_sales_semantic_ro.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.dev_sales_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_semantic_ro_schemas" {
  account_role_name = snowflake_account_role.ar_dev_sales_semantic_ro.name
  privileges        = ["USAGE"]
  on_schema {
    all_schemas_in_database = snowflake_database.dev_sales_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_semantic_ro_future_schemas" {
  account_role_name = snowflake_account_role.ar_dev_sales_semantic_ro.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = snowflake_database.dev_sales_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_semantic_ro_future_semantic_views" {
  account_role_name = snowflake_account_role.ar_dev_sales_semantic_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "SEMANTIC VIEWS"
      in_database        = snowflake_database.dev_sales_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_semantic_ro_future_tables" {
  account_role_name = snowflake_account_role.ar_dev_sales_semantic_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.dev_sales_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_semantic_ro_future_views" {
  account_role_name = snowflake_account_role.ar_dev_sales_semantic_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.dev_sales_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_semantic_rw_db" {
  account_role_name = snowflake_account_role.ar_dev_sales_semantic_rw.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.dev_sales_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_semantic_rw_schemas" {
  account_role_name = snowflake_account_role.ar_dev_sales_semantic_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    all_schemas_in_database = snowflake_database.dev_sales_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_semantic_rw_future_schemas" {
  account_role_name = snowflake_account_role.ar_dev_sales_semantic_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    future_schemas_in_database = snowflake_database.dev_sales_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_semantic_rw_future_tables" {
  account_role_name = snowflake_account_role.ar_dev_sales_semantic_rw.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.dev_sales_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_sales_semantic_rw_future_views" {
  account_role_name = snowflake_account_role.ar_dev_sales_semantic_rw.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.dev_sales_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_raw_ro_db" {
  account_role_name = snowflake_account_role.ar_dev_finance_raw_ro.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.dev_finance_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_raw_ro_schemas" {
  account_role_name = snowflake_account_role.ar_dev_finance_raw_ro.name
  privileges        = ["USAGE"]
  on_schema {
    all_schemas_in_database = snowflake_database.dev_finance_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_raw_ro_future_schemas" {
  account_role_name = snowflake_account_role.ar_dev_finance_raw_ro.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = snowflake_database.dev_finance_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_raw_ro_future_semantic_views" {
  account_role_name = snowflake_account_role.ar_dev_finance_raw_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "SEMANTIC VIEWS"
      in_database        = snowflake_database.dev_finance_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_raw_ro_future_tables" {
  account_role_name = snowflake_account_role.ar_dev_finance_raw_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.dev_finance_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_raw_ro_future_views" {
  account_role_name = snowflake_account_role.ar_dev_finance_raw_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.dev_finance_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_raw_rw_db" {
  account_role_name = snowflake_account_role.ar_dev_finance_raw_rw.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.dev_finance_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_raw_rw_schemas" {
  account_role_name = snowflake_account_role.ar_dev_finance_raw_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    all_schemas_in_database = snowflake_database.dev_finance_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_raw_rw_future_schemas" {
  account_role_name = snowflake_account_role.ar_dev_finance_raw_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    future_schemas_in_database = snowflake_database.dev_finance_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_raw_rw_future_tables" {
  account_role_name = snowflake_account_role.ar_dev_finance_raw_rw.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.dev_finance_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_raw_rw_future_views" {
  account_role_name = snowflake_account_role.ar_dev_finance_raw_rw.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.dev_finance_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_conformed_ro_db" {
  account_role_name = snowflake_account_role.ar_dev_finance_conformed_ro.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.dev_finance_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_conformed_ro_schemas" {
  account_role_name = snowflake_account_role.ar_dev_finance_conformed_ro.name
  privileges        = ["USAGE"]
  on_schema {
    all_schemas_in_database = snowflake_database.dev_finance_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_conformed_ro_future_schemas" {
  account_role_name = snowflake_account_role.ar_dev_finance_conformed_ro.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = snowflake_database.dev_finance_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_conformed_ro_future_semantic_views" {
  account_role_name = snowflake_account_role.ar_dev_finance_conformed_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "SEMANTIC VIEWS"
      in_database        = snowflake_database.dev_finance_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_conformed_ro_future_tables" {
  account_role_name = snowflake_account_role.ar_dev_finance_conformed_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.dev_finance_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_conformed_ro_future_views" {
  account_role_name = snowflake_account_role.ar_dev_finance_conformed_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.dev_finance_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_conformed_rw_db" {
  account_role_name = snowflake_account_role.ar_dev_finance_conformed_rw.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.dev_finance_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_conformed_rw_schemas" {
  account_role_name = snowflake_account_role.ar_dev_finance_conformed_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    all_schemas_in_database = snowflake_database.dev_finance_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_conformed_rw_future_schemas" {
  account_role_name = snowflake_account_role.ar_dev_finance_conformed_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    future_schemas_in_database = snowflake_database.dev_finance_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_conformed_rw_future_tables" {
  account_role_name = snowflake_account_role.ar_dev_finance_conformed_rw.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.dev_finance_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_conformed_rw_future_views" {
  account_role_name = snowflake_account_role.ar_dev_finance_conformed_rw.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.dev_finance_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_curated_ro_db" {
  account_role_name = snowflake_account_role.ar_dev_finance_curated_ro.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.dev_finance_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_curated_ro_schemas" {
  account_role_name = snowflake_account_role.ar_dev_finance_curated_ro.name
  privileges        = ["USAGE"]
  on_schema {
    all_schemas_in_database = snowflake_database.dev_finance_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_curated_ro_future_schemas" {
  account_role_name = snowflake_account_role.ar_dev_finance_curated_ro.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = snowflake_database.dev_finance_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_curated_ro_future_semantic_views" {
  account_role_name = snowflake_account_role.ar_dev_finance_curated_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "SEMANTIC VIEWS"
      in_database        = snowflake_database.dev_finance_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_curated_ro_future_tables" {
  account_role_name = snowflake_account_role.ar_dev_finance_curated_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.dev_finance_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_curated_ro_future_views" {
  account_role_name = snowflake_account_role.ar_dev_finance_curated_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.dev_finance_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_curated_rw_db" {
  account_role_name = snowflake_account_role.ar_dev_finance_curated_rw.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.dev_finance_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_curated_rw_schemas" {
  account_role_name = snowflake_account_role.ar_dev_finance_curated_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    all_schemas_in_database = snowflake_database.dev_finance_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_curated_rw_future_schemas" {
  account_role_name = snowflake_account_role.ar_dev_finance_curated_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    future_schemas_in_database = snowflake_database.dev_finance_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_curated_rw_future_tables" {
  account_role_name = snowflake_account_role.ar_dev_finance_curated_rw.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.dev_finance_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_curated_rw_future_views" {
  account_role_name = snowflake_account_role.ar_dev_finance_curated_rw.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.dev_finance_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_semantic_ro_db" {
  account_role_name = snowflake_account_role.ar_dev_finance_semantic_ro.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.dev_finance_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_semantic_ro_schemas" {
  account_role_name = snowflake_account_role.ar_dev_finance_semantic_ro.name
  privileges        = ["USAGE"]
  on_schema {
    all_schemas_in_database = snowflake_database.dev_finance_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_semantic_ro_future_schemas" {
  account_role_name = snowflake_account_role.ar_dev_finance_semantic_ro.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = snowflake_database.dev_finance_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_semantic_ro_future_semantic_views" {
  account_role_name = snowflake_account_role.ar_dev_finance_semantic_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "SEMANTIC VIEWS"
      in_database        = snowflake_database.dev_finance_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_semantic_ro_future_tables" {
  account_role_name = snowflake_account_role.ar_dev_finance_semantic_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.dev_finance_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_semantic_ro_future_views" {
  account_role_name = snowflake_account_role.ar_dev_finance_semantic_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.dev_finance_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_semantic_rw_db" {
  account_role_name = snowflake_account_role.ar_dev_finance_semantic_rw.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.dev_finance_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_semantic_rw_schemas" {
  account_role_name = snowflake_account_role.ar_dev_finance_semantic_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    all_schemas_in_database = snowflake_database.dev_finance_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_semantic_rw_future_schemas" {
  account_role_name = snowflake_account_role.ar_dev_finance_semantic_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    future_schemas_in_database = snowflake_database.dev_finance_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_semantic_rw_future_tables" {
  account_role_name = snowflake_account_role.ar_dev_finance_semantic_rw.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.dev_finance_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_dev_finance_semantic_rw_future_views" {
  account_role_name = snowflake_account_role.ar_dev_finance_semantic_rw.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.dev_finance_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_raw_ro_db" {
  account_role_name = snowflake_account_role.ar_prod_sales_raw_ro.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.prod_sales_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_raw_ro_schemas" {
  account_role_name = snowflake_account_role.ar_prod_sales_raw_ro.name
  privileges        = ["USAGE"]
  on_schema {
    all_schemas_in_database = snowflake_database.prod_sales_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_raw_ro_future_schemas" {
  account_role_name = snowflake_account_role.ar_prod_sales_raw_ro.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = snowflake_database.prod_sales_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_raw_ro_future_semantic_views" {
  account_role_name = snowflake_account_role.ar_prod_sales_raw_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "SEMANTIC VIEWS"
      in_database        = snowflake_database.prod_sales_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_raw_ro_future_tables" {
  account_role_name = snowflake_account_role.ar_prod_sales_raw_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.prod_sales_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_raw_ro_future_views" {
  account_role_name = snowflake_account_role.ar_prod_sales_raw_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.prod_sales_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_raw_rw_db" {
  account_role_name = snowflake_account_role.ar_prod_sales_raw_rw.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.prod_sales_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_raw_rw_schemas" {
  account_role_name = snowflake_account_role.ar_prod_sales_raw_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    all_schemas_in_database = snowflake_database.prod_sales_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_raw_rw_future_schemas" {
  account_role_name = snowflake_account_role.ar_prod_sales_raw_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    future_schemas_in_database = snowflake_database.prod_sales_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_raw_rw_future_tables" {
  account_role_name = snowflake_account_role.ar_prod_sales_raw_rw.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.prod_sales_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_raw_rw_future_views" {
  account_role_name = snowflake_account_role.ar_prod_sales_raw_rw.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.prod_sales_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_conformed_ro_db" {
  account_role_name = snowflake_account_role.ar_prod_sales_conformed_ro.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.prod_sales_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_conformed_ro_schemas" {
  account_role_name = snowflake_account_role.ar_prod_sales_conformed_ro.name
  privileges        = ["USAGE"]
  on_schema {
    all_schemas_in_database = snowflake_database.prod_sales_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_conformed_ro_future_schemas" {
  account_role_name = snowflake_account_role.ar_prod_sales_conformed_ro.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = snowflake_database.prod_sales_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_conformed_ro_future_semantic_views" {
  account_role_name = snowflake_account_role.ar_prod_sales_conformed_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "SEMANTIC VIEWS"
      in_database        = snowflake_database.prod_sales_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_conformed_ro_future_tables" {
  account_role_name = snowflake_account_role.ar_prod_sales_conformed_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.prod_sales_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_conformed_ro_future_views" {
  account_role_name = snowflake_account_role.ar_prod_sales_conformed_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.prod_sales_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_conformed_rw_db" {
  account_role_name = snowflake_account_role.ar_prod_sales_conformed_rw.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.prod_sales_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_conformed_rw_schemas" {
  account_role_name = snowflake_account_role.ar_prod_sales_conformed_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    all_schemas_in_database = snowflake_database.prod_sales_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_conformed_rw_future_schemas" {
  account_role_name = snowflake_account_role.ar_prod_sales_conformed_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    future_schemas_in_database = snowflake_database.prod_sales_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_conformed_rw_future_tables" {
  account_role_name = snowflake_account_role.ar_prod_sales_conformed_rw.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.prod_sales_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_conformed_rw_future_views" {
  account_role_name = snowflake_account_role.ar_prod_sales_conformed_rw.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.prod_sales_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_curated_ro_db" {
  account_role_name = snowflake_account_role.ar_prod_sales_curated_ro.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.prod_sales_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_curated_ro_schemas" {
  account_role_name = snowflake_account_role.ar_prod_sales_curated_ro.name
  privileges        = ["USAGE"]
  on_schema {
    all_schemas_in_database = snowflake_database.prod_sales_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_curated_ro_future_schemas" {
  account_role_name = snowflake_account_role.ar_prod_sales_curated_ro.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = snowflake_database.prod_sales_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_curated_ro_future_semantic_views" {
  account_role_name = snowflake_account_role.ar_prod_sales_curated_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "SEMANTIC VIEWS"
      in_database        = snowflake_database.prod_sales_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_curated_ro_future_tables" {
  account_role_name = snowflake_account_role.ar_prod_sales_curated_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.prod_sales_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_curated_ro_future_views" {
  account_role_name = snowflake_account_role.ar_prod_sales_curated_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.prod_sales_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_curated_rw_db" {
  account_role_name = snowflake_account_role.ar_prod_sales_curated_rw.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.prod_sales_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_curated_rw_schemas" {
  account_role_name = snowflake_account_role.ar_prod_sales_curated_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    all_schemas_in_database = snowflake_database.prod_sales_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_curated_rw_future_schemas" {
  account_role_name = snowflake_account_role.ar_prod_sales_curated_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    future_schemas_in_database = snowflake_database.prod_sales_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_curated_rw_future_tables" {
  account_role_name = snowflake_account_role.ar_prod_sales_curated_rw.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.prod_sales_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_curated_rw_future_views" {
  account_role_name = snowflake_account_role.ar_prod_sales_curated_rw.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.prod_sales_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_semantic_ro_db" {
  account_role_name = snowflake_account_role.ar_prod_sales_semantic_ro.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.prod_sales_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_semantic_ro_schemas" {
  account_role_name = snowflake_account_role.ar_prod_sales_semantic_ro.name
  privileges        = ["USAGE"]
  on_schema {
    all_schemas_in_database = snowflake_database.prod_sales_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_semantic_ro_future_schemas" {
  account_role_name = snowflake_account_role.ar_prod_sales_semantic_ro.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = snowflake_database.prod_sales_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_semantic_ro_future_semantic_views" {
  account_role_name = snowflake_account_role.ar_prod_sales_semantic_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "SEMANTIC VIEWS"
      in_database        = snowflake_database.prod_sales_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_semantic_ro_future_tables" {
  account_role_name = snowflake_account_role.ar_prod_sales_semantic_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.prod_sales_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_semantic_ro_future_views" {
  account_role_name = snowflake_account_role.ar_prod_sales_semantic_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.prod_sales_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_semantic_rw_db" {
  account_role_name = snowflake_account_role.ar_prod_sales_semantic_rw.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.prod_sales_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_semantic_rw_schemas" {
  account_role_name = snowflake_account_role.ar_prod_sales_semantic_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    all_schemas_in_database = snowflake_database.prod_sales_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_semantic_rw_future_schemas" {
  account_role_name = snowflake_account_role.ar_prod_sales_semantic_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    future_schemas_in_database = snowflake_database.prod_sales_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_semantic_rw_future_tables" {
  account_role_name = snowflake_account_role.ar_prod_sales_semantic_rw.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.prod_sales_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_sales_semantic_rw_future_views" {
  account_role_name = snowflake_account_role.ar_prod_sales_semantic_rw.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.prod_sales_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_raw_ro_db" {
  account_role_name = snowflake_account_role.ar_prod_finance_raw_ro.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.prod_finance_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_raw_ro_schemas" {
  account_role_name = snowflake_account_role.ar_prod_finance_raw_ro.name
  privileges        = ["USAGE"]
  on_schema {
    all_schemas_in_database = snowflake_database.prod_finance_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_raw_ro_future_schemas" {
  account_role_name = snowflake_account_role.ar_prod_finance_raw_ro.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = snowflake_database.prod_finance_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_raw_ro_future_semantic_views" {
  account_role_name = snowflake_account_role.ar_prod_finance_raw_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "SEMANTIC VIEWS"
      in_database        = snowflake_database.prod_finance_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_raw_ro_future_tables" {
  account_role_name = snowflake_account_role.ar_prod_finance_raw_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.prod_finance_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_raw_ro_future_views" {
  account_role_name = snowflake_account_role.ar_prod_finance_raw_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.prod_finance_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_raw_rw_db" {
  account_role_name = snowflake_account_role.ar_prod_finance_raw_rw.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.prod_finance_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_raw_rw_schemas" {
  account_role_name = snowflake_account_role.ar_prod_finance_raw_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    all_schemas_in_database = snowflake_database.prod_finance_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_raw_rw_future_schemas" {
  account_role_name = snowflake_account_role.ar_prod_finance_raw_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    future_schemas_in_database = snowflake_database.prod_finance_raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_raw_rw_future_tables" {
  account_role_name = snowflake_account_role.ar_prod_finance_raw_rw.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.prod_finance_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_raw_rw_future_views" {
  account_role_name = snowflake_account_role.ar_prod_finance_raw_rw.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.prod_finance_raw.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_conformed_ro_db" {
  account_role_name = snowflake_account_role.ar_prod_finance_conformed_ro.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.prod_finance_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_conformed_ro_schemas" {
  account_role_name = snowflake_account_role.ar_prod_finance_conformed_ro.name
  privileges        = ["USAGE"]
  on_schema {
    all_schemas_in_database = snowflake_database.prod_finance_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_conformed_ro_future_schemas" {
  account_role_name = snowflake_account_role.ar_prod_finance_conformed_ro.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = snowflake_database.prod_finance_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_conformed_ro_future_semantic_views" {
  account_role_name = snowflake_account_role.ar_prod_finance_conformed_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "SEMANTIC VIEWS"
      in_database        = snowflake_database.prod_finance_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_conformed_ro_future_tables" {
  account_role_name = snowflake_account_role.ar_prod_finance_conformed_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.prod_finance_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_conformed_ro_future_views" {
  account_role_name = snowflake_account_role.ar_prod_finance_conformed_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.prod_finance_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_conformed_rw_db" {
  account_role_name = snowflake_account_role.ar_prod_finance_conformed_rw.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.prod_finance_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_conformed_rw_schemas" {
  account_role_name = snowflake_account_role.ar_prod_finance_conformed_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    all_schemas_in_database = snowflake_database.prod_finance_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_conformed_rw_future_schemas" {
  account_role_name = snowflake_account_role.ar_prod_finance_conformed_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    future_schemas_in_database = snowflake_database.prod_finance_conformed.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_conformed_rw_future_tables" {
  account_role_name = snowflake_account_role.ar_prod_finance_conformed_rw.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.prod_finance_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_conformed_rw_future_views" {
  account_role_name = snowflake_account_role.ar_prod_finance_conformed_rw.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.prod_finance_conformed.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_curated_ro_db" {
  account_role_name = snowflake_account_role.ar_prod_finance_curated_ro.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.prod_finance_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_curated_ro_schemas" {
  account_role_name = snowflake_account_role.ar_prod_finance_curated_ro.name
  privileges        = ["USAGE"]
  on_schema {
    all_schemas_in_database = snowflake_database.prod_finance_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_curated_ro_future_schemas" {
  account_role_name = snowflake_account_role.ar_prod_finance_curated_ro.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = snowflake_database.prod_finance_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_curated_ro_future_semantic_views" {
  account_role_name = snowflake_account_role.ar_prod_finance_curated_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "SEMANTIC VIEWS"
      in_database        = snowflake_database.prod_finance_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_curated_ro_future_tables" {
  account_role_name = snowflake_account_role.ar_prod_finance_curated_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.prod_finance_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_curated_ro_future_views" {
  account_role_name = snowflake_account_role.ar_prod_finance_curated_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.prod_finance_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_curated_rw_db" {
  account_role_name = snowflake_account_role.ar_prod_finance_curated_rw.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.prod_finance_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_curated_rw_schemas" {
  account_role_name = snowflake_account_role.ar_prod_finance_curated_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    all_schemas_in_database = snowflake_database.prod_finance_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_curated_rw_future_schemas" {
  account_role_name = snowflake_account_role.ar_prod_finance_curated_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    future_schemas_in_database = snowflake_database.prod_finance_curated.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_curated_rw_future_tables" {
  account_role_name = snowflake_account_role.ar_prod_finance_curated_rw.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.prod_finance_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_curated_rw_future_views" {
  account_role_name = snowflake_account_role.ar_prod_finance_curated_rw.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.prod_finance_curated.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_semantic_ro_db" {
  account_role_name = snowflake_account_role.ar_prod_finance_semantic_ro.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.prod_finance_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_semantic_ro_schemas" {
  account_role_name = snowflake_account_role.ar_prod_finance_semantic_ro.name
  privileges        = ["USAGE"]
  on_schema {
    all_schemas_in_database = snowflake_database.prod_finance_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_semantic_ro_future_schemas" {
  account_role_name = snowflake_account_role.ar_prod_finance_semantic_ro.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = snowflake_database.prod_finance_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_semantic_ro_future_semantic_views" {
  account_role_name = snowflake_account_role.ar_prod_finance_semantic_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "SEMANTIC VIEWS"
      in_database        = snowflake_database.prod_finance_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_semantic_ro_future_tables" {
  account_role_name = snowflake_account_role.ar_prod_finance_semantic_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.prod_finance_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_semantic_ro_future_views" {
  account_role_name = snowflake_account_role.ar_prod_finance_semantic_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.prod_finance_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_semantic_rw_db" {
  account_role_name = snowflake_account_role.ar_prod_finance_semantic_rw.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.prod_finance_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_semantic_rw_schemas" {
  account_role_name = snowflake_account_role.ar_prod_finance_semantic_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    all_schemas_in_database = snowflake_database.prod_finance_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_semantic_rw_future_schemas" {
  account_role_name = snowflake_account_role.ar_prod_finance_semantic_rw.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    future_schemas_in_database = snowflake_database.prod_finance_semantic.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_semantic_rw_future_tables" {
  account_role_name = snowflake_account_role.ar_prod_finance_semantic_rw.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.prod_finance_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ar_prod_finance_semantic_rw_future_views" {
  account_role_name = snowflake_account_role.ar_prod_finance_semantic_rw.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.prod_finance_semantic.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "fr_engineer_wh_elt_usage" {
  account_role_name = snowflake_account_role.fr_engineer.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.wh_elt.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "fr_engineer_wh_adhoc_usage" {
  account_role_name = snowflake_account_role.fr_engineer.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.wh_adhoc.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "fr_analyst_wh_adhoc_usage" {
  account_role_name = snowflake_account_role.fr_analyst.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.wh_adhoc.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "fr_bi_wh_bi_usage" {
  account_role_name = snowflake_account_role.fr_bi.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.wh_bi.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "fr_data_scientist_wh_ds_usage" {
  account_role_name = snowflake_account_role.fr_data_scientist.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.wh_ds.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "fr_privacy_officer_wh_adhoc_usage" {
  account_role_name = snowflake_account_role.fr_privacy_officer.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.wh_adhoc.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "fr_governance_admin_governance_tags_admin" {
  account_role_name = snowflake_account_role.fr_governance_admin.name
  privileges        = ["USAGE", "CREATE TAG", "CREATE MASKING POLICY", "CREATE ROW ACCESS POLICY"]
  on_schema {
    schema_name = snowflake_schema.governance_tags.fully_qualified_name
  }
}

resource "snowflake_grant_privileges_to_account_role" "fr_governance_admin_governance_policies_admin" {
  account_role_name = snowflake_account_role.fr_governance_admin.name
  privileges        = ["USAGE", "CREATE TAG", "CREATE MASKING POLICY", "CREATE ROW ACCESS POLICY"]
  on_schema {
    schema_name = snowflake_schema.governance_policies.fully_qualified_name
  }
}
