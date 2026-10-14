"""Snowflake Native App bundle: the D0 Snapshot runs entirely inside the client account.

The bundle (``manifest.yml``, ``setup.sql``, ``README.md``) is rendered from the
same sources the SaaS edition uses — the harvest contract queries and the
diagnostic check catalogue — so the two editions cannot drift:

- ``CORE.HARVEST(edition, window_days)`` materialises every harvest-contract
  table into the app's ``HARVEST`` schema with the same read-only statements the
  live harvester uses (SHOW + RESULT_SCAN where needed);
- each detector is transpiled from the catalogue's DuckDB SQL to Snowflake SQL
  (sqlglot, unsupported constructs raise at generation time) as a view in
  ``DETECTORS``; rubric thresholds are rendered as literals *in the generated
  bundle only*;
- ``CORE.RUN_D0()`` records flagged objects per check into ``CORE.FINDINGS``.

The app requests ``IMPORTED PRIVILEGES ON SNOWFLAKE DB`` (account-usage views) and
no external access integration: nothing leaves the account.
"""

from __future__ import annotations

import re

import sqlglot
from sqlglot.errors import ErrorLevel

from altitude.core.rubric import RubricSet, default_rubrics
from altitude.core.theme import token
from altitude.synthetic.schema import HARVEST_SCHEMA

APP_SCHEMAS = ("CORE", "HARVEST", "DETECTORS")
CLIENT_SUPPLIED = ("CLIENT_INPUTS", "BI_REPORTS", "BI_MEASURES")


def _sf(sql: str) -> str:
    return sqlglot.transpile(sql, read="duckdb", write="snowflake", unsupported_level=ErrorLevel.RAISE)[0]


def _literal(v) -> str:
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_literal(x) for x in v) + "]"  # DuckDB list literal; transpiled with the detector
    return "'" + str(v).replace("'", "''") + "'"


def _runtime_params(rubrics: RubricSet) -> dict[str, str]:
    from altitude.diagnostics.engine import UNIT_REFS

    out = {name: _literal(rubrics.get(ref)) for name, ref in UNIT_REFS.items()}
    out.update({
        "window_days": "(SELECT WINDOW_DAYS FROM CORE.RUN_CONTEXT)",
        "as_of": "(SELECT AS_OF FROM CORE.RUN_CONTEXT)",
        "window_start": "(SELECT WINDOW_START FROM CORE.RUN_CONTEXT)",
        "window_end": "(SELECT WINDOW_END FROM CORE.RUN_CONTEXT)",
        "price_per_credit": "(SELECT TRY_TO_DOUBLE(VALUE::STRING) FROM HARVEST.CLIENT_INPUTS "
                            "WHERE KEY = 'contract_price_per_credit')",
        "storage_price_per_tb_month": "(SELECT TRY_TO_DOUBLE(VALUE::STRING) FROM HARVEST.CLIENT_INPUTS "
                                      "WHERE KEY = 'storage_price_per_tb_month')",
    })
    return out


def _bind(sql: str, params: dict[str, str]) -> str:
    def sub(m: re.Match) -> str:
        name = m.group(1)
        if name not in params:
            raise KeyError(f"unbound detector parameter ${name}")
        return params[name]

    return re.sub(r"\$(\w+)", sub, sql)


def _qualify(sql: str, names: set[str], schema: str) -> str:
    """Point bare harvest/helper table names at their app schema."""
    tree = sqlglot.parse_one(sql, read="snowflake")
    for t in tree.find_all(sqlglot.exp.Table):
        if not t.args.get("db") and t.name.upper() in names:
            t.set("db", sqlglot.exp.to_identifier(schema if t.name.upper() in HARVEST_SCHEMA else "DETECTORS"))
    return tree.sql(dialect="snowflake")


def setup_sql(rubrics: RubricSet | None = None) -> str:
    from altitude.diagnostics.catalogue import default_catalogue
    from altitude.diagnostics.harvest import HARVEST_QUERIES

    rubrics = rubrics or default_rubrics()
    cat = default_catalogue()
    params = _runtime_params(rubrics)
    out = [
        f"-- {token('PRODUCT_NAME')} D0 Snapshot — Snowflake Native App setup script.",
        "-- Metadata-only: reads SNOWFLAKE.ACCOUNT_USAGE through imported privileges; no external access.",
        "CREATE APPLICATION ROLE IF NOT EXISTS APP_ADMIN;",
        "CREATE APPLICATION ROLE IF NOT EXISTS APP_VIEWER;",
        "GRANT APPLICATION ROLE APP_VIEWER TO APPLICATION ROLE APP_ADMIN;",
        "CREATE OR ALTER VERSIONED SCHEMA CORE;",
        "CREATE SCHEMA IF NOT EXISTS HARVEST;",
        "CREATE OR ALTER VERSIONED SCHEMA DETECTORS;",
        "CREATE TABLE IF NOT EXISTS CORE.RUN_CONTEXT (AS_OF TIMESTAMP_NTZ, WINDOW_START TIMESTAMP_NTZ, "
        "WINDOW_END TIMESTAMP_NTZ, WINDOW_DAYS INTEGER, EDITION VARCHAR);",
        "CREATE TABLE IF NOT EXISTS CORE.FINDINGS (RUN_AT TIMESTAMP_NTZ, CHECK_ID VARCHAR, OBJECT_NAME VARCHAR, "
        "CLUSTER_KEY VARCHAR, SIGNALS VARIANT);",
        "CREATE TABLE IF NOT EXISTS CORE.HARVEST_LOG (RUN_AT TIMESTAMP_NTZ, TABLE_NAME VARCHAR, STATUS VARCHAR, "
        "ERROR VARCHAR);",
    ]
    for name in CLIENT_SUPPLIED:
        cols = ", ".join(f'{c} {"VARIANT" if t == "JSON" else t.replace("DOUBLE", "FLOAT")}'
                         for c, t in HARVEST_SCHEMA[name]["columns"].items())
        out.append(f"CREATE TABLE IF NOT EXISTS HARVEST.{name} ({cols});")
    # harvest procedure: each source in its own block so an unreadable view is logged, not fatal
    body = ["DECLARE run_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP();", "BEGIN",
            "  DELETE FROM CORE.RUN_CONTEXT;",
            "  INSERT INTO CORE.RUN_CONTEXT SELECT CURRENT_TIMESTAMP(), DATEADD(day, -:window_days, CURRENT_DATE()), "
            "CURRENT_DATE() + 1, :window_days, :edition;"]
    for table in HARVEST_SCHEMA:
        if table in CLIENT_SUPPLIED or table not in HARVEST_QUERIES:
            continue
        q = HARVEST_QUERIES[table]
        select = (q.sql.replace("%(edition)s", ":edition")
                  .replace("%(window_start)s", "DATEADD(day, -:window_days, CURRENT_DATE())")
                  .replace("%(window_end)s", "CURRENT_DATE() + 1"))
        stmts = []
        if q.pre:
            stmts.append(f"    {q.pre};")
        stmts.append(f"    CREATE OR REPLACE TABLE HARVEST.{table} AS {select};")
        body += ["  BEGIN", *stmts,
                 f"    INSERT INTO CORE.HARVEST_LOG SELECT :run_at, '{table}', 'ok', NULL;",
                 "  EXCEPTION WHEN OTHER THEN",
                 f"    INSERT INTO CORE.HARVEST_LOG SELECT :run_at, '{table}', 'unavailable', :SQLERRM;",
                 "  END;"]
    body += ["  RETURN 'harvested';", "END;"]
    out.append("CREATE OR REPLACE PROCEDURE CORE.HARVEST(EDITION VARCHAR, WINDOW_DAYS INTEGER)\n"
               "RETURNS VARCHAR LANGUAGE SQL EXECUTE AS OWNER AS\n$$\n" + "\n".join(body) + "\n$$;")
    # helpers and detectors as views
    names = {t.upper() for t in HARVEST_SCHEMA} | {h["name"].upper() for h in cat.helpers}
    for h in cat.helpers:
        if h["kind"] == "rubric_map":
            mapping = rubrics.get(h["ref"])
            rows = " UNION ALL ".join(f"SELECT {_literal(k)} AS {h['key_column']}, {float(v)!r} AS {h['value_column']}"
                                      for k, v in sorted(mapping.items()))
            out.append(f"CREATE OR REPLACE VIEW DETECTORS.{h['name']} AS {rows};")
        else:
            sql = _qualify(_sf(_bind(h["sql"], params)), names, "HARVEST")
            out.append(f"CREATE OR REPLACE VIEW DETECTORS.{h['name']} AS {sql};")
    d0 = [c for c in cat.checks if c.domain in ("D1", "D2", "D3", "D4", "D5")]
    for c in cat.checks:
        bound = _bind(c.detector_sql(), {**params, **{k: _literal(v) for k, v in c.resolve_params(rubrics).items()}})
        sql = _qualify(_sf(bound), names, "HARVEST")
        out.append(f"-- {c.id}: {c.title}\nCREATE OR REPLACE VIEW DETECTORS.{c.id.replace('-', '_')} AS {sql};")
    inserts = "\n".join(
        f"  INSERT INTO CORE.FINDINGS SELECT :run_at, '{c.id}', OBJECT_NAME, CLUSTER_KEY, OBJECT_CONSTRUCT(*) "
        f"FROM DETECTORS.{c.id.replace('-', '_')} WHERE FLAGGED;" for c in d0)
    out.append("CREATE OR REPLACE PROCEDURE CORE.RUN_D0()\nRETURNS VARCHAR LANGUAGE SQL EXECUTE AS OWNER AS\n$$\n"
               "DECLARE run_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP();\nBEGIN\n" + inserts +
               "\n  RETURN 'D0 snapshot complete';\nEND;\n$$;")
    out.append("CREATE OR REPLACE VIEW CORE.TOP_FINDINGS AS SELECT CHECK_ID, COUNT(*) AS OBJECTS, "
               "ARRAY_AGG(OBJECT_NAME) AS AFFECTED FROM CORE.FINDINGS "
               "WHERE RUN_AT = (SELECT MAX(RUN_AT) FROM CORE.FINDINGS) GROUP BY CHECK_ID;")
    out += [
        "GRANT USAGE ON SCHEMA CORE TO APPLICATION ROLE APP_VIEWER;",
        "GRANT USAGE ON SCHEMA DETECTORS TO APPLICATION ROLE APP_VIEWER;",
        "GRANT SELECT ON ALL VIEWS IN SCHEMA DETECTORS TO APPLICATION ROLE APP_VIEWER;",
        "GRANT SELECT ON VIEW CORE.TOP_FINDINGS TO APPLICATION ROLE APP_VIEWER;",
        "GRANT SELECT ON TABLE CORE.FINDINGS TO APPLICATION ROLE APP_VIEWER;",
        "GRANT USAGE ON SCHEMA HARVEST TO APPLICATION ROLE APP_ADMIN;",
        "GRANT INSERT, SELECT ON TABLE HARVEST.CLIENT_INPUTS TO APPLICATION ROLE APP_ADMIN;",
        "GRANT INSERT, SELECT ON TABLE HARVEST.BI_REPORTS TO APPLICATION ROLE APP_ADMIN;",
        "GRANT INSERT, SELECT ON TABLE HARVEST.BI_MEASURES TO APPLICATION ROLE APP_ADMIN;",
        "GRANT USAGE ON PROCEDURE CORE.HARVEST(VARCHAR, INTEGER) TO APPLICATION ROLE APP_ADMIN;",
        "GRANT USAGE ON PROCEDURE CORE.RUN_D0() TO APPLICATION ROLE APP_ADMIN;",
    ]
    return "\n\n".join(out) + "\n"


def manifest_yml() -> str:
    name = token("PRODUCT_NAME")
    return f"""manifest_version: 1
version:
  name: V1
  label: "{name} D0 Snapshot"
  comment: "Metadata-only Snowflake estate diagnostics running inside your account"
artifacts:
  setup_script: setup.sql
  readme: README.md
privileges:
  - IMPORTED PRIVILEGES ON SNOWFLAKE DB:
      description: "Read ACCOUNT_USAGE metadata (usage, metering, grants, tags). No row data is read."
  - MONITOR USAGE:
      description: "SHOW WAREHOUSES / resource monitors for configuration checks."
configuration:
  log_level: INFO
  trace_level: OFF
"""


def readme_md() -> str:
    return f"""# {token('PRODUCT_NAME')} D0 Snapshot (Native App)

Runs the D1–D5 diagnostic checks inside your Snowflake account. Nothing leaves the account: the app has
no external access integration and reads metadata only (no table rows).

1. Install from the listing and grant `IMPORTED PRIVILEGES ON SNOWFLAKE DB`.
2. Optionally insert intake values (contract price per credit, Tier-1 tables) into `HARVEST.CLIENT_INPUTS`.
3. `CALL CORE.HARVEST('ENTERPRISE', 90);` then `CALL CORE.RUN_D0();`
4. `SELECT * FROM CORE.TOP_FINDINGS;` — then ask {token('COMPANY_NAME')} for the evidence-backed Package D readout.
"""


def bundle(rubrics: RubricSet | None = None) -> dict[str, str]:
    return {"manifest.yml": manifest_yml(), "setup.sql": setup_sql(rubrics), "README.md": readme_md()}
