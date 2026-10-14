"""Emulated Oracle estate (schemas SALES and FIN) in DuckDB.

Data-dictionary tables are shaped like the real ``DBA_*`` views and
``UNIFIED_AUDIT_TRAIL``. PL/SQL source lives in ``plsql.sql`` and is stored
line by line in ``DBA_SOURCE`` exactly as Oracle does. Includes a package with
global state, an autonomous transaction, BULK COLLECT loops, ``(+)`` joins and
EXECUTE IMMEDIATE; a month-end DBMS_SCHEDULER job; unused objects; and user
tables holding canary rows that must never be harvested.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb

HERE = Path(__file__).parent
AS_OF = datetime(2026, 9, 30, 22, 0, 0)
CANARY = "CANARY-ORA-ROW-4410"

TABLES = {  # name: ([(col, type, length, precision, scale, nullable, char_used)], num_rows, blocks, temporary)
    "SALES.CUSTOMERS": ([("CUSTOMER_ID", "NUMBER", 22, 10, 0, "N", None), ("NAME", "VARCHAR2", 200, None, None, "Y", "C"),
                         ("EMAIL", "VARCHAR2", 320, None, None, "Y", "B"), ("CREATED", "DATE", 7, None, None, "Y", None)],
                        1_200_000, 16_000, "N"),
    "SALES.ORDERS": ([("ORDER_ID", "NUMBER", 22, None, None, "N", None), ("CUSTOMER_ID", "NUMBER", 22, 10, 0, "N", None),
                      ("ORDER_DATE", "DATE", 7, None, None, "N", None), ("STATUS", "VARCHAR2", 20, None, None, "Y", "B")],
                     80_000_000, 900_000, "N"),
    "SALES.ORDER_LINES": ([("ORDER_ID", "NUMBER", 22, None, None, "N", None), ("PRODUCT_ID", "NUMBER", 22, 10, 0, "N", None),
                           ("QUANTITY", "NUMBER", 22, 10, 0, "N", None), ("UNIT_PRICE", "NUMBER", 22, None, None, "N", None)],
                          310_000_000, 2_800_000, "N"),
    "SALES.PRODUCTS": ([("PRODUCT_ID", "NUMBER", 22, 10, 0, "N", None), ("NAME", "VARCHAR2", 200, None, None, "Y", "C")],
                       30_000, 400, "N"),
    "SALES.STG_ORDERS": ([("ORDER_ID", "NUMBER", 22, None, None, "N", None), ("CUSTOMER_ID", "NUMBER", 22, 10, 0, "N", None),
                          ("ORDER_DATE", "DATE", 7, None, None, "N", None), ("STATUS", "VARCHAR2", 20, None, None, "Y", "B")],
                         250_000, 3_000, "N"),
    "SALES.DAILY_SALES_AGG": ([("SALES_DAY", "DATE", 7, None, None, "N", None), ("PRODUCT_ID", "NUMBER", 22, 10, 0, "N", None),
                               ("AMOUNT", "NUMBER", 22, 18, 2, "Y", None)], 9_000_000, 60_000, "N"),
    "SALES.ERR_LOG": ([("LOGGED_AT", "DATE", 7, None, None, "N", None), ("MESSAGE", "VARCHAR2", 4000, None, None, "Y", "B")],
                      1_500, 20, "N"),
    "SALES.ORDERS_AUDIT": ([("ORDER_ID", "NUMBER", 22, None, None, "N", None), ("ACTION", "CHAR", 1, None, None, "N", "B"),
                            ("CHANGED_AT", "DATE", 7, None, None, "N", None)], 4_000_000, 30_000, "N"),
    "SALES.ORDERS_HIST_2015": ([("ORDER_ID", "NUMBER", 22, None, None, "N", None), ("PAYLOAD", "CLOB", 4000, None, None, "Y", None)],
                               120_000_000, 1_500_000, "N"),
    "SALES.TMP_ORDER_FIX": ([("ORDER_ID", "NUMBER", 22, None, None, "N", None)], None, None, "Y"),
    "FIN.GL_ENTRIES": ([("ENTRY_ID", "NUMBER", 22, 18, 0, "N", None), ("ACCOUNT_ID", "NUMBER", 22, 10, 0, "N", None),
                        ("ENTRY_DATE", "DATE", 7, None, None, "N", None), ("AMOUNT", "NUMBER", 22, None, None, "N", None)],
                       45_000_000, 500_000, "N"),
    "FIN.GL_PERIOD_CLOSE": ([("PERIOD_START", "DATE", 7, None, None, "N", None), ("ACCOUNT_ID", "NUMBER", 22, 10, 0, "N", None),
                             ("BALANCE", "NUMBER", 22, 18, 2, "Y", None), ("CLOSED_AT", "DATE", 7, None, None, "N", None)],
                            60_000, 700, "N"),
}

VIEWS = {
    "SALES.V_CUSTOMER_ORDERS": "SELECT c.customer_id, c.name, o.order_id, o.order_date, o.status\n"
                               "FROM SALES.CUSTOMERS c JOIN SALES.ORDERS o ON o.customer_id = c.customer_id\n"
                               "WHERE NVL(o.status, 'X') <> 'CANCELLED'",
    "SALES.V_SALES_BY_MONTH": "SELECT TRUNC(v.order_date, 'MM') AS month_start, COUNT(DISTINCT v.order_id) AS order_count\n"
                              "FROM SALES.V_CUSTOMER_ORDERS v\nGROUP BY TRUNC(v.order_date, 'MM')",
    "FIN.V_GL_SUMMARY": "SELECT p.period_start, SUM(p.balance) AS balance FROM FIN.GL_PERIOD_CLOSE p GROUP BY p.period_start",
    "SALES.V_OLD_REPORT": "SELECT * FROM SALES.ORDERS_HIST_2015",
}

JOBS = [  # owner, name, type, action, repeat_interval, enabled, runs cadence
    ("SALES", "LOAD_DAILY_JOB", "STORED_PROCEDURE", "SALES.SALES_PKG.LOAD_DAILY", "FREQ=DAILY;BYHOUR=2", "TRUE", "daily"),
    ("FIN", "MONTH_END_CLOSE", "PLSQL_BLOCK", "BEGIN fin.gl_close_pkg.close_period(ADD_MONTHS(SYSDATE, -1)); END;",
     "FREQ=MONTHLY;BYMONTHDAY=-1;BYHOUR=23", "TRUE", "month_end"),
]

AUDIT = [  # (schema, object, action, users, cadence, per_event)
    ("SALES", "V_SALES_BY_MONTH", "SELECT", ["ANNA", "RAVI", "BI_SVC"], "weekly", 3),
    ("SALES", "V_CUSTOMER_ORDERS", "SELECT", ["CRM_APP"], "weekly", 5),
    ("FIN", "V_GL_SUMMARY", "SELECT", ["CFO_ANALYST"], "month_end", 2),
    ("SALES", "FN_NET_AMOUNT", "EXECUTE", ["BI_SVC"], "weekly", 4),
    ("SALES", "PRODUCTS", "SELECT", ["BI_SVC"], "weekly", 1),
]

PRIVS = [("BI_READER", "SALES", "V_SALES_BY_MONTH", "SELECT"), ("BI_READER", "FIN", "V_GL_SUMMARY", "SELECT"),
         ("CRM_APP", "SALES", "V_CUSTOMER_ORDERS", "SELECT"), ("ETL_USER", "SALES", "ORDERS", "INSERT")]
ROLES = ["BI_READER", "DBA", "SELECT_CATALOG_ROLE"]


def _cadence(cadence: str) -> list[date]:
    end, out = AS_OF.date(), []
    if cadence == "daily":
        d = date(2025, 10, 1)
        while d <= end:
            out.append(d)
            d += timedelta(days=1)
    elif cadence == "weekly":
        d = date(2025, 10, 6)
        while d <= end:
            out.append(d)
            d += timedelta(days=7)
    elif cadence == "month_end":
        d = date(2025, 10, 1)
        while d <= end:
            nxt = (d.replace(day=28) + timedelta(days=5)).replace(day=1)
            out.append(nxt - timedelta(days=1))
            d = nxt
    return [x for x in out if x <= end]


def _plsql() -> list[tuple[str, str, str, list[str]]]:
    out = []
    for chunk in re.split(r"^/\s*$", (HERE / "plsql.sql").read_text(), flags=re.MULTILINE):
        chunk = chunk.strip()
        m = re.match(r"CREATE OR REPLACE (PACKAGE BODY|PACKAGE|PROCEDURE|FUNCTION|TRIGGER) (\w+)\.(\w+)", chunk)
        if not m:
            continue
        body = chunk[len("CREATE OR REPLACE "):]
        out.append((m.group(2), m.group(3), m.group(1), [l + "\n" for l in body.splitlines()]))
    return out


def bulk_insert(con: duckdb.DuckDBPyConnection, table: str, rows: list[tuple]) -> None:
    """Fast load of fixture rows (columns by position) through an Arrow scan."""
    if not rows:
        return
    import pyarrow as pa

    cols = list(zip(*rows))
    batch = pa.table({f"c{i}": [None if v is None else str(v) if isinstance(v, (int, float)) and not isinstance(v, bool)
                                else v for v in col] for i, col in enumerate(cols)})  # noqa: F841
    names = [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()]
    select = ", ".join(f'CAST(c{i} AS {t}) ' for i, t in enumerate(_types(con, table)))
    con.execute(f"INSERT INTO {table} ({', '.join(names)}) SELECT {select} FROM batch")


def _types(con: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    return [r[1] for r in con.execute(f"DESCRIBE {table}").fetchall()]


def build(*, user_data: bool = True) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    x = con.execute
    x("CREATE TABLE PRODUCT_COMPONENT_VERSION (PRODUCT VARCHAR, VERSION VARCHAR, STATUS VARCHAR)")
    x("CREATE TABLE DBA_OBJECTS (OWNER VARCHAR, OBJECT_NAME VARCHAR, OBJECT_TYPE VARCHAR, STATUS VARCHAR, "
      "CREATED TIMESTAMP, LAST_DDL_TIME TIMESTAMP)")
    x("CREATE TABLE DBA_SOURCE (OWNER VARCHAR, NAME VARCHAR, TYPE VARCHAR, LINE INTEGER, TEXT VARCHAR)")
    x("CREATE TABLE DBA_VIEWS (OWNER VARCHAR, VIEW_NAME VARCHAR, TEXT VARCHAR)")
    x("CREATE TABLE DBA_TABLES (OWNER VARCHAR, TABLE_NAME VARCHAR, NUM_ROWS BIGINT, BLOCKS BIGINT, TEMPORARY VARCHAR)")
    x("CREATE TABLE DBA_TAB_COLUMNS (OWNER VARCHAR, TABLE_NAME VARCHAR, COLUMN_NAME VARCHAR, COLUMN_ID INTEGER, "
      "DATA_TYPE VARCHAR, DATA_LENGTH INTEGER, DATA_PRECISION INTEGER, DATA_SCALE INTEGER, NULLABLE VARCHAR, "
      "CHAR_USED VARCHAR)")
    x("CREATE TABLE DBA_DEPENDENCIES (OWNER VARCHAR, NAME VARCHAR, TYPE VARCHAR, REFERENCED_OWNER VARCHAR, "
      "REFERENCED_NAME VARCHAR, REFERENCED_TYPE VARCHAR, DEPENDENCY_TYPE VARCHAR)")
    x("CREATE TABLE DBA_SCHEDULER_JOBS (OWNER VARCHAR, JOB_NAME VARCHAR, JOB_TYPE VARCHAR, JOB_ACTION VARCHAR, "
      "REPEAT_INTERVAL VARCHAR, ENABLED VARCHAR, RUN_COUNT INTEGER, LAST_START_DATE TIMESTAMP)")
    x("CREATE TABLE DBA_SCHEDULER_JOB_RUN_DETAILS (OWNER VARCHAR, JOB_NAME VARCHAR, LOG_DATE TIMESTAMP, STATUS VARCHAR)")
    x("CREATE TABLE DBA_TAB_PRIVS (GRANTEE VARCHAR, OWNER VARCHAR, TABLE_NAME VARCHAR, PRIVILEGE VARCHAR)")
    x("CREATE TABLE DBA_ROLES (ROLE VARCHAR)")
    x("CREATE TABLE UNIFIED_AUDIT_TRAIL (EVENT_TIMESTAMP TIMESTAMP, DBUSERNAME VARCHAR, ACTION_NAME VARCHAR, "
      "OBJECT_SCHEMA VARCHAR, OBJECT_NAME VARCHAR, SQL_TEXT VARCHAR)")

    def ins(table: str, rows: list[tuple]) -> None:
        bulk_insert(con, table, rows)

    ins("PRODUCT_COMPONENT_VERSION", [("Oracle Database 19c Enterprise Edition", "19.21.0.0.0", "Production")])
    created = datetime(2015, 2, 1)
    objects, tables, columns = [], [], []
    for i, (fq, (cols, nrows, blocks, temp)) in enumerate(TABLES.items()):
        owner, name = fq.split(".")
        objects.append((owner, name, "TABLE", "VALID", created + timedelta(days=i * 40), datetime(2024, 3, 1)))
        tables.append((owner, name, nrows, blocks, temp))
        for ci, (c, t, length, p, s, null, cu) in enumerate(cols, 1):
            columns.append((owner, name, c, ci, t, length, p, s, null, cu))
    for i, (fq, text) in enumerate(VIEWS.items()):
        owner, name = fq.split(".")
        objects.append((owner, name, "VIEW", "VALID", created + timedelta(days=500 + i), datetime(2024, 6, 1)))
    plsql = _plsql()
    source = []
    for owner, name, typ, lines in plsql:
        status = "VALID"
        objects.append((owner, name, typ, status, created + timedelta(days=800), datetime(2025, 1, 10)))
        source.extend((owner, name, typ, n, line) for n, line in enumerate(lines, 1))
    objects.append(("SYS", "DBMS_OUTPUT", "PACKAGE", "VALID", created, created))
    objects.append(("SALES", "ORDERS_SEQ", "SEQUENCE", "VALID", created, created))
    ins("DBA_OBJECTS", objects)
    ins("DBA_SOURCE", source)
    ins("DBA_VIEWS", [(fq.split(".")[0], fq.split(".")[1], t) for fq, t in VIEWS.items()])
    ins("DBA_TABLES", tables)
    ins("DBA_TAB_COLUMNS", columns)

    deps = []
    known = {fq.split(".")[1]: fq.split(".")[0] for fq in list(TABLES) + list(VIEWS)}
    known.update({n: o for o, n, _, _ in plsql})
    kinds = {fq.split(".")[1]: "TABLE" for fq in TABLES}
    kinds.update({fq.split(".")[1]: "VIEW" for fq in VIEWS})
    kinds.update({n: t.replace(" BODY", "") for _, n, t, _ in plsql})
    for owner, name, typ, lines in plsql:
        text = "".join(lines).upper()
        for ref, ref_owner in known.items():
            if ref != name and re.search(rf"\b{ref}\b", text):
                deps.append((owner, name, typ, ref_owner, ref, kinds[ref], "HARD"))
        if "DBMS_" in text or "SQLERRM" in text:
            deps.append((owner, name, typ, "SYS", "STANDARD", "PACKAGE", "HARD"))
    for fq, text in VIEWS.items():
        owner, name = fq.split(".")
        for ref, ref_owner in known.items():
            if ref != name and re.search(rf"\b{ref}\b", text.upper()):
                deps.append((owner, name, "VIEW", ref_owner, ref, kinds[ref], "HARD"))
    ins("DBA_DEPENDENCIES", deps)

    jobs, runs = [], []
    for owner, name, typ, action, interval, enabled, cadence in JOBS:
        days = _cadence(cadence)
        jobs.append((owner, name, typ, action, interval, enabled, len(days), datetime.combine(days[-1], datetime.min.time())))
        runs.extend((owner, name, datetime.combine(d, datetime.min.time()) + timedelta(hours=2), "SUCCEEDED") for d in days)
    ins("DBA_SCHEDULER_JOBS", jobs)
    ins("DBA_SCHEDULER_JOB_RUN_DETAILS", runs)

    audit = []
    for schema, obj, action, users, cadence, per in AUDIT:
        for d in _cadence(cadence):
            for u in users:
                for k in range(per):
                    audit.append((datetime.combine(d, datetime.min.time()) + timedelta(hours=9, minutes=k), u, action,
                                  schema, obj, f"SELECT * FROM {schema}.{obj} WHERE name = '{CANARY}'"))
    audit.append((datetime(2026, 9, 1, 8), "SYS", "LOGON", None, None, None))
    ins("UNIFIED_AUDIT_TRAIL", audit)
    ins("DBA_TAB_PRIVS", PRIVS)
    ins("DBA_ROLES", [(r,) for r in ROLES])

    if user_data:
        x("CREATE SCHEMA SALES")
        x("CREATE TABLE SALES.CUSTOMERS (CUSTOMER_ID INTEGER, NAME VARCHAR, EMAIL VARCHAR)")
        x(f"INSERT INTO SALES.CUSTOMERS VALUES (1, '{CANARY} Ada', 'ada@example.com')")
    return con
