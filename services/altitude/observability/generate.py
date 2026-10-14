"""Generated Package O deployment artifacts (``generated/observability/``), rendered from knowledge YAML.

- ``snowflake/00_database.sql``       OBS database, schemas (RAW managed access), roles, warehouse
- ``snowflake/01_raw_tables.sql``     RAW archive tables (harvest contract + ACCOUNT_NAME + load metadata)
- ``snowflake/02_grants.sql``         least-privilege grants — RAW gets INSERT/SELECT only (no UPDATE/DELETE)
- ``snowflake/03_curated.sql``        CURATED views (DuckDB SQL transpiled with sqlglot, or Snowflake overrides)
- ``snowflake/04_kpi_dynamic_tables.sql``  one dynamic table per implemented KPI (target lag = freshness SLA)
- ``snowflake/05_semantic.sql``       certified KPI definitions, KPI_VALUES view and semantic views per domain
- ``snowflake/06_alerts.sql``         Snowflake ALERT objects for the alert catalogue
- ``cortex/ask_the_platform_agent.json`` / ``cortex/create_agent.sql``  Cortex Agent over the semantic views
- ``streamlit/streamlit_app.py`` (+ ``environment.yml``)  Streamlit-in-Snowflake app for dashboards 1, 2, 4, 8
- ``alerts/alert_catalogue.json``     resolved alert catalogue (severity, route, runbook, suppression, owner)
- ``kpi_catalogue.md``                human-readable KPI catalogue
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

from altitude.core.generated import stamp
from altitude.core.rubric import default_rubrics
from altitude.synthetic.schema import HARVEST_SCHEMA

from .config import kpi_table, load_alerts, load_golden, load_kpis, load_runbooks, load_sources
from .curate import curated_objects, substitute_rubric, to_snowflake
from .db import HARVEST_LOG_COLUMNS, MEMBERSHIP_COLUMNS, ALERT_EVENT_COLUMNS, ROUTING_TEST_COLUMNS, raw_columns
from .kpi import implemented, kpi_select

PREFIX = "observability"
DB = "OBS"
WAREHOUSE = "OBS_WH"
ROLES = {"admin": "OBS_ADMIN", "loader": "OBS_LOADER", "transformer": "OBS_TRANSFORMER", "reader": "OBS_READER",
         "agent": "OBS_AGENT"}
SF_TYPES = {"VARCHAR": "VARCHAR", "TIMESTAMP": "TIMESTAMP_NTZ", "DOUBLE": "FLOAT", "BIGINT": "NUMBER(38,0)",
            "INTEGER": "NUMBER(38,0)", "BOOLEAN": "BOOLEAN", "DATE": "DATE", "JSON": "VARIANT"}


def _ddl(schema: str, table: str, cols: dict[str, str], comment: str) -> str:
    body = ",\n".join(f"  {c} {SF_TYPES.get(t, t)}" for c, t in cols.items())
    return f"CREATE TABLE IF NOT EXISTS {DB}.{schema}.{table} (\n{body}\n)\n  COMMENT = '{comment}';\n"


def database_sql() -> str:
    r = ROLES
    return f"""-- Package O OBS database (Section 7.3). Run as a role with CREATE DATABASE / CREATE ROLE.
CREATE ROLE IF NOT EXISTS {r['admin']};
CREATE ROLE IF NOT EXISTS {r['loader']};
CREATE ROLE IF NOT EXISTS {r['transformer']};
CREATE ROLE IF NOT EXISTS {r['reader']};
CREATE ROLE IF NOT EXISTS {r['agent']};
GRANT ROLE {r['loader']} TO ROLE {r['admin']};
GRANT ROLE {r['transformer']} TO ROLE {r['admin']};
GRANT ROLE {r['reader']} TO ROLE {r['admin']};
GRANT ROLE {r['agent']} TO ROLE {r['admin']};

CREATE WAREHOUSE IF NOT EXISTS {WAREHOUSE} WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE COMMENT = 'Package O harvest, KPI refresh and alerts';
CREATE DATABASE IF NOT EXISTS {DB} COMMENT = 'Package O observability data product (client-owned)';
GRANT OWNERSHIP ON DATABASE {DB} TO ROLE {r['admin']} COPY CURRENT GRANTS;
USE DATABASE {DB};

-- RAW is a managed-access schema owned by {r['admin']}: only the owner can grant, and no pipeline role
-- receives UPDATE, DELETE or TRUNCATE (see 02_grants.sql and the CI kill-test).
CREATE SCHEMA IF NOT EXISTS {DB}.RAW WITH MANAGED ACCESS DATA_RETENTION_TIME_IN_DAYS = 90
  COMMENT = 'Immutable, append-only archive of ACCOUNT_USAGE et al.; retention beyond the native window';
CREATE SCHEMA IF NOT EXISTS {DB}.CURATED COMMENT = 'Conformed facts and dimensions';
CREATE SCHEMA IF NOT EXISTS {DB}.KPI COMMENT = 'Dynamic tables implementing the KPI catalogue';
CREATE SCHEMA IF NOT EXISTS {DB}.SEMANTIC COMMENT = 'Semantic views holding certified KPI definitions';
CREATE SCHEMA IF NOT EXISTS {DB}.OPS WITH MANAGED ACCESS COMMENT = 'Alert events and routing tests (append-only)';
"""


def raw_tables_sql() -> str:
    parts = [f"USE DATABASE {DB};\n"]
    for table in HARVEST_SCHEMA:
        parts.append(_ddl("RAW", table, raw_columns(table),
                          f"Archive of {HARVEST_SCHEMA[table]['source'][:120]}".replace("'", "")))
    parts.append(_ddl("RAW", "HARVEST_LOG", HARVEST_LOG_COLUMNS, "Every harvest step (append-only)"))
    parts.append(_ddl("RAW", "SNAPSHOT_MEMBERSHIP", MEMBERSHIP_COLUMNS, "Row hashes seen by each full-snapshot harvest"))
    parts.append(_ddl("OPS", "ALERT_EVENT", ALERT_EVENT_COLUMNS, "Fired and suppressed alert events (append-only)"))
    parts.append(_ddl("OPS", "ROUTING_TEST", ROUTING_TEST_COLUMNS, "Monthly alert routing tests (append-only)"))
    return "\n".join(parts)


def grants_sql() -> str:
    r = ROLES
    lines = [
        "-- Least-privilege grants. RAW immutability: no role is granted UPDATE, DELETE or TRUNCATE on RAW;",
        "-- the loader may only INSERT and SELECT (append-only). Verified by tests/observability (kill-test).",
        f"GRANT USAGE ON WAREHOUSE {WAREHOUSE} TO ROLE {r['loader']};",
        f"GRANT USAGE ON WAREHOUSE {WAREHOUSE} TO ROLE {r['transformer']};",
        f"GRANT USAGE ON WAREHOUSE {WAREHOUSE} TO ROLE {r['reader']};",
        f"GRANT USAGE ON WAREHOUSE {WAREHOUSE} TO ROLE {r['agent']};",
        f"GRANT USAGE ON DATABASE {DB} TO ROLE {r['loader']};",
        f"GRANT USAGE ON DATABASE {DB} TO ROLE {r['transformer']};",
        f"GRANT USAGE ON DATABASE {DB} TO ROLE {r['reader']};",
        f"GRANT USAGE ON DATABASE {DB} TO ROLE {r['agent']};",
        "",
        "-- harvest: read the source views (in each client account, via SNOWFLAKE database roles)",
        f"GRANT DATABASE ROLE SNOWFLAKE.USAGE_VIEWER TO ROLE {r['loader']};",
        f"GRANT DATABASE ROLE SNOWFLAKE.GOVERNANCE_VIEWER TO ROLE {r['loader']};",
        f"GRANT DATABASE ROLE SNOWFLAKE.SECURITY_VIEWER TO ROLE {r['loader']};",
        "",
        "-- RAW: append-only",
        f"GRANT USAGE ON SCHEMA {DB}.RAW TO ROLE {r['loader']};",
        f"GRANT INSERT, SELECT ON ALL TABLES IN SCHEMA {DB}.RAW TO ROLE {r['loader']};",
        f"GRANT INSERT, SELECT ON FUTURE TABLES IN SCHEMA {DB}.RAW TO ROLE {r['loader']};",
        f"GRANT USAGE ON SCHEMA {DB}.RAW TO ROLE {r['transformer']};",
        f"GRANT SELECT ON ALL TABLES IN SCHEMA {DB}.RAW TO ROLE {r['transformer']};",
        f"GRANT SELECT ON FUTURE TABLES IN SCHEMA {DB}.RAW TO ROLE {r['transformer']};",
        "",
        "-- CURATED / KPI: rebuilt by the transformer (views and dynamic tables)",
    ]
    for s in ("CURATED", "KPI", "SEMANTIC"):
        lines += [
            f"GRANT USAGE, CREATE VIEW, CREATE TABLE, CREATE DYNAMIC TABLE ON SCHEMA {DB}.{s} TO ROLE {r['transformer']};",
            f"GRANT USAGE ON SCHEMA {DB}.{s} TO ROLE {r['reader']};",
            f"GRANT SELECT ON ALL TABLES IN SCHEMA {DB}.{s} TO ROLE {r['reader']};",
            f"GRANT SELECT ON FUTURE TABLES IN SCHEMA {DB}.{s} TO ROLE {r['reader']};",
            f"GRANT SELECT ON ALL VIEWS IN SCHEMA {DB}.{s} TO ROLE {r['reader']};",
            f"GRANT SELECT ON FUTURE VIEWS IN SCHEMA {DB}.{s} TO ROLE {r['reader']};",
            f"GRANT SELECT ON ALL DYNAMIC TABLES IN SCHEMA {DB}.{s} TO ROLE {r['reader']};",
            f"GRANT SELECT ON FUTURE DYNAMIC TABLES IN SCHEMA {DB}.{s} TO ROLE {r['reader']};",
        ]
    lines += [
        f"GRANT CREATE SEMANTIC VIEW ON SCHEMA {DB}.SEMANTIC TO ROLE {r['transformer']};",
        "",
        "-- ask-the-platform agent: semantic layer only",
        f"GRANT USAGE ON SCHEMA {DB}.SEMANTIC TO ROLE {r['agent']};",
        f"GRANT SELECT ON ALL VIEWS IN SCHEMA {DB}.SEMANTIC TO ROLE {r['agent']};",
        f"GRANT SELECT ON ALL TABLES IN SCHEMA {DB}.SEMANTIC TO ROLE {r['agent']};",
        f"GRANT SELECT ON ALL SEMANTIC VIEWS IN SCHEMA {DB}.SEMANTIC TO ROLE {r['agent']};",
        f"GRANT USAGE ON SCHEMA {DB}.KPI TO ROLE {r['agent']};",
        f"GRANT SELECT ON ALL DYNAMIC TABLES IN SCHEMA {DB}.KPI TO ROLE {r['agent']};",
        f"GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE {r['agent']};",
        "",
        "-- OPS: alert events are append-only too",
        f"GRANT USAGE ON SCHEMA {DB}.OPS TO ROLE {r['transformer']};",
        f"GRANT INSERT, SELECT ON ALL TABLES IN SCHEMA {DB}.OPS TO ROLE {r['transformer']};",
        f"GRANT USAGE ON SCHEMA {DB}.OPS TO ROLE {r['reader']};",
        f"GRANT SELECT ON ALL TABLES IN SCHEMA {DB}.OPS TO ROLE {r['reader']};",
        f"GRANT EXECUTE ALERT ON ACCOUNT TO ROLE {r['transformer']};",
    ]
    return "\n".join(lines) + "\n"


def _sf(sql: str) -> str:
    return to_snowflake(substitute_rubric(sql))


def curated_sql() -> str:
    parts = [f"USE DATABASE {DB};\n"]
    for name, sql, sf, obj in curated_objects():
        desc = " ".join(str(obj.get("description", "")).split()).replace("'", "")
        body = sf.strip() if sf else _sf(sql)
        parts.append(f"-- {obj.get('kind', 'view')}: {desc}\nCREATE OR REPLACE VIEW {DB}.CURATED.{name}\n"
                     f"  COMMENT = '{desc[:250]}'\nAS\n{body};\n")
    return "\n".join(parts)


def _lag_hours(k: dict) -> str:
    return f"{float(default_rubrics().get(k['freshness_sla_ref'])):g} hours"


def kpi_dynamic_tables_sql() -> str:
    parts = [f"USE DATABASE {DB};\n"]
    for k in implemented(load_kpis()):
        name = kpi_table(k["id"])
        comment = f"{k['id']} {k['name']}: {' '.join(str(k['definition']).split())}".replace("'", "")[:400]
        if k.get("engine", "sql") != "sql":
            measures = {"KPI-PHI-001": "PILLARS", "KPI-PHI-002": "KPIS"}
            extra = f",\n  {measures[k['id']]} NUMBER(38,0)" if k["id"] in measures else ""
            parts.append(f"-- {k['id']} is computed by altitude.observability.kpi (engine: python) or fed by the\n"
                         f"-- Package D scorecard re-run; the table is loaded, not a dynamic table.\n"
                         f"CREATE TABLE IF NOT EXISTS {DB}.KPI.{name} (\n  ACCOUNT_NAME VARCHAR,\n  PERIOD DATE,\n"
                         f"  DIMENSION VARCHAR,\n  VALUE FLOAT{extra}\n) COMMENT = '{comment}';\n")
            continue
        parts.append(f"CREATE OR REPLACE DYNAMIC TABLE {DB}.KPI.{name}\n  TARGET_LAG = '{_lag_hours(k)}'\n"
                     f"  WAREHOUSE = {WAREHOUSE}\n  COMMENT = '{comment}'\nAS\n{_sf(kpi_select(k))};\n")
    return "\n".join(parts)


def _ident(s: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", s.lower())


def semantic_sql() -> str:
    kpis = load_kpis()
    impl = implemented(kpis)
    rs = default_rubrics()
    parts = [f"USE DATABASE {DB};\n",
             f"CREATE OR REPLACE TABLE {DB}.SEMANTIC.KPI_DEFINITIONS (\n  KPI_ID VARCHAR, NAME VARCHAR, DOMAIN VARCHAR, "
             "TIER VARCHAR, STATUS VARCHAR, CERTIFIED BOOLEAN,\n  DEFINITION VARCHAR, UNIT VARCHAR, GRAIN VARCHAR, "
             "AGGREGATION VARCHAR, DIRECTION VARCHAR, WAF_PILLAR VARCHAR,\n  OWNER_ROLE VARCHAR, KPI_TABLE VARCHAR, "
             "SYNONYMS VARCHAR\n) COMMENT = 'Certified KPI definitions (knowledge/observability/kpis)';\n"]
    values = []
    for k in kpis:
        def q(v: object) -> str:
            return "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"
        values.append("  (" + ", ".join([
            q(k["id"]), q(k["name"]), q(k["domain"]), q(k["tier"]), q(k["status"]),
            "TRUE" if k["status"] == "implemented" else "FALSE", q(" ".join(str(k["definition"]).split())),
            q(k.get("unit")), q(json.dumps(k.get("grain", []))), q(k.get("aggregation")), q(k.get("direction")),
            q(k.get("waf_pillar")), q(k.get("owner_role")), q(f"{DB}.KPI.{kpi_table(k['id'])}"),
            q(json.dumps(k.get("synonyms", []))),
        ]) + ")")
    parts.append(f"INSERT INTO {DB}.SEMANTIC.KPI_DEFINITIONS VALUES\n" + ",\n".join(values) + ";\n")
    union = "\nUNION ALL\n".join(
        f"SELECT '{k['id']}' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM {DB}.KPI.{kpi_table(k['id'])}"
        for k in impl)
    parts.append(f"CREATE OR REPLACE VIEW {DB}.SEMANTIC.KPI_VALUES AS\n{union};\n")
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for k in impl:
        by_domain[k["domain"]].append(k)
    for dom, ks in sorted(by_domain.items()):
        tables, dims, metrics = [], [], []
        for k in ks:
            alias = _ident(k["id"])
            syn = ", ".join("'" + s.replace("'", "") + "'" for s in (k.get("synonyms") or [])[:6])
            desc = " ".join(str(k["definition"]).split()).replace("'", "")[:300]
            tables.append(f"    {alias} AS {DB}.KPI.{kpi_table(k['id'])}\n      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)"
                          + (f"\n      WITH SYNONYMS ({syn})" if syn else "") + f"\n      COMMENT = '{k['name'].replace(chr(39), '')}'")
            dims.append(f"    {alias}.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account'")
            dims.append(f"    {alias}.period AS PERIOD COMMENT = 'Day (or month) of the KPI value'")
            dims.append(f"    {alias}.{_ident(k.get('dimension') or 'dimension')}_{alias} AS DIMENSION "
                        f"COMMENT = '{k.get('dimension', 'none')}'")
            agg = {"sum": "SUM", "avg": "AVG", "max": "MAX", "min": "MIN", "latest": "MAX"}.get(k.get("aggregation"), "AVG")
            target = f" Target: {float(rs.get(k['target_ref'])):g} ({k['direction']})." if k.get("target_ref") else ""
            metrics.append(f"    {alias}.{_ident(k['name'])[:60]} AS {agg}(VALUE)\n      COMMENT = "
                           f"'{k['id']} [{k.get('unit')}] {desc}{target}'")
        parts.append(
            f"CREATE OR REPLACE SEMANTIC VIEW {DB}.SEMANTIC.SV_{dom.upper()}\n  TABLES (\n" + ",\n".join(tables)
            + "\n  )\n  DIMENSIONS (\n" + ",\n".join(dims) + "\n  )\n  METRICS (\n" + ",\n".join(metrics)
            + f"\n  )\n  COMMENT = 'Certified {dom} KPIs (Package O semantic layer)';\n")
    return "\n".join(parts)


_ACCOUNT_EQ = re.compile(r"([\w.]*ACCOUNT_NAME)\s*=\s*\$account")


def _alert_condition(a: dict) -> str:
    rs = default_rubrics()
    rule = a["rule"]
    t = f"{DB}.KPI.{kpi_table(a['kpi'])}"
    if rule["type"] == "forecast_band":
        dim = "DIMENSION" if rule.get("per", "dimension") == "dimension" else "''"
        g = lambda ref: f"{float(rs.get(rule[ref])):g}"  # noqa: E731
        return (f"WITH s AS (SELECT ACCOUNT_NAME, {dim} AS DIM, PERIOD, SUM(VALUE) AS V FROM {t}\n"
                f"           WHERE PERIOD >= DATEADD(DAY, -{int(rs.get(rule['lookback_ref'])) + 1}, CURRENT_DATE()) GROUP BY 1, 2, 3),\n"
                f"     b AS (SELECT t.ACCOUNT_NAME, t.DIM, t.V, AVG(h.V) AS M, STDDEV_POP(h.V) AS SD, COUNT(h.V) AS N\n"
                f"           FROM s t JOIN s h ON h.ACCOUNT_NAME = t.ACCOUNT_NAME AND h.DIM = t.DIM AND h.PERIOD < t.PERIOD\n"
                f"            AND (DAYOFWEEKISO(h.PERIOD) IN (6, 7)) = (DAYOFWEEKISO(t.PERIOD) IN (6, 7))\n"
                f"           WHERE t.PERIOD = DATEADD(DAY, -1, CURRENT_DATE()) GROUP BY 1, 2, 3)\n"
                f"SELECT * FROM b WHERE N >= {int(rs.get(rule['min_points_ref']))}\n"
                f"  AND V > M + GREATEST({g('band_stdevs_ref')} * SD, {g('min_band_pct_ref')} * ABS(M))\n"
                f"  AND V - M >= {g('min_abs_ref')}")
    if rule["type"] == "threshold":
        ops = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
        period = ("DATE_TRUNC('MONTH', DATEADD(DAY, -1, CURRENT_DATE()))" if rule.get("at") == "month"
                  else "DATEADD(DAY, -1, CURRENT_DATE())")
        return (f"SELECT ACCOUNT_NAME, DIMENSION, VALUE FROM {t}\nWHERE PERIOD = {period} AND VALUE "
                f"{ops[rule.get('op', 'gt')]} {float(rs.get(rule['threshold_ref'])):g}")
    sql = substitute_rubric(rule["sql"])
    sql = _ACCOUNT_EQ.sub(r"\1 IS NOT NULL", sql).replace("$day", "CAST(current_date - INTERVAL 1 DAY AS DATE)")
    sql = sql.replace("CURATED.", f"{DB}.CURATED.")
    return to_snowflake(sql)


def alerts_sql() -> str:
    cat = load_alerts()
    parts = [f"USE DATABASE {DB};\n-- One Snowflake ALERT per catalogue entry. Notification integrations are created per tenant\n"
             f"-- (OBS_ROUTE_<ROUTE>) from the tenant registry's alert_routes; routing is tested monthly.\n"]
    for a in cat["alerts"]:
        route = a["route_ref"].rsplit(".", 1)[-1].upper()
        name = a["id"].replace("-", "_")
        msg = f"[{a['severity'].upper()}] {a['name']} — runbook {a['runbook']}, owner {a['owner_role']}".replace("'", "")
        parts.append(
            f"-- {a['id']} ({a['class']}): severity {a['severity']}, route {a['route_ref']}, runbook {a['runbook']}, "
            f"suppression {a.get('suppression_hours', 0)}h, owner {a['owner_role']}\n"
            f"CREATE OR REPLACE ALERT {DB}.OPS.{name}\n  WAREHOUSE = {WAREHOUSE}\n  SCHEDULE = 'USING CRON 15 6 * * * UTC'\n"
            f"  IF (EXISTS (\n{_alert_condition(a)}\n  ))\n  THEN CALL SYSTEM$SEND_SNOWFLAKE_NOTIFICATION(\n"
            f"    SNOWFLAKE.NOTIFICATION.TEXT_PLAIN('{msg}'),\n"
            f"    SNOWFLAKE.NOTIFICATION.INTEGRATION('OBS_ROUTE_{route}'));\n"
            f"ALTER ALERT {DB}.OPS.{name} RESUME;\n")
    return "\n".join(parts)


def alert_catalogue_json() -> str:
    cat = load_alerts()
    runbooks = load_runbooks()
    out = {"alerts": [], "routing_test": cat.get("routing_test"), "severities": cat.get("severities")}
    for a in cat["alerts"]:
        rb = runbooks.get(a["runbook"], {})
        out["alerts"].append({"id": a["id"], "class": a["class"], "name": a["name"], "severity": a["severity"],
                              "kpi": a["kpi"], "rule": a["rule"]["type"], "route_ref": a["route_ref"],
                              "runbook": a["runbook"], "runbook_title": rb.get("title"),
                              "suppression_hours": a.get("suppression_hours"), "owner_role": a["owner_role"]})
    return json.dumps(out, indent=2)


def agent_spec() -> dict:
    impl = implemented(load_kpis())
    domains = sorted({k["domain"] for k in impl})
    samples = [g["question"] for g in load_golden() if not g["expected"].get("refuse")]
    return {
        "name": "ASK_THE_PLATFORM",
        "comment": "Package O ask-the-platform agent: answers only from certified KPIs in OBS.SEMANTIC, with citations",
        "models": {"orchestration": "auto"},
        "instructions": {
            "response": ("Answer only from the certified KPIs exposed by the semantic views. Always cite the KPI id(s), "
                         "the KPI table and the time window used, and state the unit. If no certified KPI answers the "
                         "question, or the KPI has no data for the window, say so and refuse; never estimate."),
            "orchestration": ("Map the question to a KPI via its name and synonyms, apply account / dimension / time "
                              "filters, aggregate with the KPI's aggregation, and return the rows used."),
            "sample_questions": [{"question": q} for q in samples],
        },
        "tools": [{"tool_spec": {"type": "cortex_analyst_text_to_sql", "name": f"kpi_{d}",
                                 "description": f"Certified {d} KPIs (OBS.SEMANTIC.SV_{d.upper()})"}} for d in domains],
        "tool_resources": {f"kpi_{d}": {"semantic_view": f"{DB}.SEMANTIC.SV_{d.upper()}",
                                        "execution_environment": {"type": "warehouse", "warehouse": WAREHOUSE}}
                           for d in domains},
    }


def create_agent_sql() -> str:
    spec = agent_spec()
    body = json.dumps({k: v for k, v in spec.items() if k not in ("name", "comment")}, indent=2)
    return (f"USE DATABASE {DB};\nCREATE OR REPLACE AGENT {DB}.SEMANTIC.{spec['name']}\n"
            f"  COMMENT = '{spec['comment']}'\n  FROM SPECIFICATION\n$$\n{body}\n$$;\n"
            f"GRANT USAGE ON AGENT {DB}.SEMANTIC.{spec['name']} TO ROLE {ROLES['reader']};\n")


def streamlit_app() -> str:
    return f'''"""Package O dashboards in Streamlit-in-Snowflake (dashboards 1, 2, 4 and 8) over {DB}.KPI."""

import streamlit as st
from snowflake.snowpark.context import get_active_session

session = get_active_session()
st.set_page_config(page_title="Platform Observability", layout="wide")


def q(sql, params=None):
    return session.sql(sql, params=params or []).to_pandas()


accounts = q("SELECT DISTINCT ACCOUNT_NAME FROM {DB}.KPI.KPI_COST_011 ORDER BY 1")["ACCOUNT_NAME"].tolist()
account = st.sidebar.selectbox("Account", accounts)
days = st.sidebar.slider("Window (days)", 7, 90, 28)
page = st.sidebar.radio("Dashboard", ["Executive Cost & Value", "Platform Health", "Pipelines & Freshness",
                                      "Chargeback statements"])
win = "PERIOD >= DATEADD(DAY, -?, (SELECT MAX(PERIOD) FROM {DB}.KPI.KPI_COST_011)) AND ACCOUNT_NAME = ?"

if page == "Executive Cost & Value":
    st.header("Executive Cost & Value")
    c1, c2, c3 = st.columns(3)
    mom = q("SELECT VALUE FROM {DB}.KPI.KPI_COST_004 WHERE ACCOUNT_NAME = ? ORDER BY PERIOD DESC LIMIT 1", [account])
    fvb = q("SELECT VALUE FROM {DB}.KPI.KPI_COST_005 WHERE ACCOUNT_NAME = ? ORDER BY PERIOD DESC LIMIT 1", [account])
    spend = q(f"SELECT PERIOD, VALUE FROM {DB}.KPI.KPI_COST_011 WHERE {{win}} ORDER BY PERIOD", [days, account])
    c1.metric("Spend in window ($)", f"{{spend['VALUE'].sum():,.0f}}")
    c2.metric("Month-on-month (%)", "-" if mom.empty else f"{{mom['VALUE'][0]:+.1f}}")
    c3.metric("Forecast vs budget", "-" if fvb.empty else f"{{fvb['VALUE'][0]:.0%}}")
    st.subheader("Daily spend (KPI-COST-011)")
    st.line_chart(spend, x="PERIOD", y="VALUE")
    st.subheader("Spend by warehouse (KPI-COST-002)")
    st.bar_chart(q(f"SELECT DIMENSION, SUM(VALUE) AS USD FROM {DB}.KPI.KPI_COST_002 WHERE {{win}} GROUP BY 1",
                   [days, account]), x="DIMENSION", y="USD")
    st.subheader("Cost by cost centre (KPI-COST-003)")
    st.bar_chart(q(f"SELECT DIMENSION, SUM(VALUE) AS USD FROM {DB}.KPI.KPI_COST_003 WHERE {{win}} GROUP BY 1",
                   [days, account]), x="DIMENSION", y="USD")
elif page == "Platform Health":
    st.header("Platform Health")
    phi = q("SELECT PERIOD, VALUE FROM {DB}.KPI.KPI_PHI_001 WHERE ACCOUNT_NAME = ? ORDER BY PERIOD", [account])
    st.metric("Health Index", "-" if phi.empty else f"{{phi['VALUE'].iloc[-1]:.1f}}")
    st.bar_chart(q("SELECT DIMENSION AS PILLAR, VALUE FROM {DB}.KPI.KPI_PHI_002 WHERE ACCOUNT_NAME = ? AND PERIOD = "
                   "(SELECT MAX(PERIOD) FROM {DB}.KPI.KPI_PHI_002 WHERE ACCOUNT_NAME = ?)", [account, account]),
                 x="PILLAR", y="VALUE")
    st.dataframe(q("SELECT ALERT_CLASS, SEVERITY, COUNT(*) AS FIRED FROM {DB}.OPS.ALERT_EVENT WHERE STATUS = 'fired' "
                   "AND ACCOUNT_NAME = ? GROUP BY 1, 2 ORDER BY 3 DESC", [account]))
elif page == "Pipelines & Freshness":
    st.header("Pipelines & Freshness")
    st.line_chart(q(f"SELECT PERIOD, VALUE FROM {DB}.KPI.KPI_REL_001 WHERE {{win}} ORDER BY PERIOD", [days, account]),
                  x="PERIOD", y="VALUE")
    st.bar_chart(q(f"SELECT DIMENSION, AVG(VALUE) AS ATTAINMENT FROM {DB}.KPI.KPI_REL_003 WHERE {{win}} GROUP BY 1",
                   [days, account]), x="DIMENSION", y="ATTAINMENT")
    st.dataframe(q("SELECT FQ_NAME, SCHEDULED_TIME, ERROR_MESSAGE FROM {DB}.CURATED.FACT_TASK_RUN WHERE STATE = 'FAILED' "
                   "AND ACCOUNT_NAME = ? ORDER BY SCHEDULED_TIME DESC LIMIT 50", [account]))
else:
    st.header("Chargeback statements")
    month = st.selectbox("Month", q("SELECT DISTINCT DATE_TRUNC('MONTH', PERIOD) AS M FROM {DB}.KPI.KPI_COST_003 "
                                    "ORDER BY 1 DESC")["M"].tolist())
    cb = q("SELECT DIMENSION AS COST_CENTRE, SUM(VALUE) AS USD FROM {DB}.KPI.KPI_COST_003 WHERE ACCOUNT_NAME = ? AND "
           "DATE_TRUNC('MONTH', PERIOD) = ? GROUP BY 1 ORDER BY 2 DESC", [account, month])
    st.dataframe(cb)
    st.download_button("Export CSV", cb.to_csv(index=False), file_name=f"chargeback_{{month}}.csv")
'''


def kpi_catalogue_md() -> str:
    kpis = load_kpis()
    rows = ["# Package O KPI catalogue", "",
            f"{len(kpis)} KPIs; {len([k for k in kpis if k['status'] == 'implemented'])} implemented, "
            f"{len([k for k in kpis if k['tier'] == 'core'])} in the core tier. Source: knowledge/observability/kpis.", "",
            "| ID | Name | Domain | Tier | Status | Unit | Grain | Sources |", "|---|---|---|---|---|---|---|---|"]
    for k in sorted(kpis, key=lambda k: k["id"]):
        rows.append(f"| {k['id']} | {k['name']} | {k['domain']} | {k['tier']} | {k['status']} | {k.get('unit', '')} | "
                    f"{', '.join(k.get('grain', []))} | {', '.join(k.get('sources', []))} |")
    return "\n".join(rows) + "\n"


def generate() -> dict[str, str]:
    files = {
        "snowflake/00_database.sql": (database_sql(), ".sql", "knowledge/observability/sources.yaml"),
        "snowflake/01_raw_tables.sql": (raw_tables_sql(), ".sql", "altitude.synthetic.schema.HARVEST_SCHEMA"),
        "snowflake/02_grants.sql": (grants_sql(), ".sql", "altitude.observability.generate"),
        "snowflake/03_curated.sql": (curated_sql(), ".sql", "knowledge/observability/curated.yaml"),
        "snowflake/04_kpi_dynamic_tables.sql": (kpi_dynamic_tables_sql(), ".sql", "knowledge/observability/kpis"),
        "snowflake/05_semantic.sql": (semantic_sql(), ".sql", "knowledge/observability/kpis"),
        "snowflake/06_alerts.sql": (alerts_sql(), ".sql", "knowledge/observability/alerts.yaml"),
        "alerts/alert_catalogue.json": (alert_catalogue_json(), ".json", "knowledge/observability/alerts.yaml"),
        "cortex/ask_the_platform_agent.json": (json.dumps(agent_spec(), indent=2), ".json",
                                               "knowledge/observability/kpis + golden_questions.yaml"),
        "cortex/create_agent.sql": (create_agent_sql(), ".sql", "knowledge/observability/kpis"),
        "streamlit/streamlit_app.py": (streamlit_app(), ".py", "altitude.observability.generate"),
        "streamlit/environment.yml": ("name: obs_dashboards\nchannels:\n  - snowflake\ndependencies:\n  - streamlit\n",
                                      ".yml", "altitude.observability.generate"),
        "kpi_catalogue.md": (kpi_catalogue_md(), ".md", "knowledge/observability/kpis"),
    }
    return {f"{PREFIX}/{rel}": stamp(content, suffix, source) for rel, (content, suffix, source) in files.items()}
