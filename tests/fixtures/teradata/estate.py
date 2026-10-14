"""Emulated Teradata estate (EDW / EDW_V) in DuckDB plus BTEQ scripts on disk.

``DBC.TablesV`` carries RequestText DDL for tables, views, macros and an SPL
procedure; ``DBC.ColumnsV`` carries NOT CASESPECIFIC and CHAR columns (TD-02,
TD-03); DBQL (``QryLogV``/``QryLogObjectsV``) carries usage with query bands
naming BTEQ scripts. Scripts in ``bteq/`` contain ``.LOGON`` credentials that
must be redacted before shipping.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb

HERE = Path(__file__).parent
BTEQ_DIR = HERE / "bteq"
AS_OF = datetime(2026, 9, 30, 21, 0, 0)
CANARY = "CANARY-TD-ROW-9902"

DDL = {  # (db, name): (kind, request text)
    ("EDW", "CUSTOMER"): ("T", "CREATE SET TABLE EDW.CUSTOMER ,FALLBACK (CUSTOMER_ID INTEGER NOT NULL, "
                               "CUSTOMER_NAME VARCHAR(100) CHARACTER SET LATIN NOT CASESPECIFIC, SEGMENT CHAR(10)) "
                               "UNIQUE PRIMARY INDEX (CUSTOMER_ID);"),
    ("EDW", "SALES_FACT"): ("T", "CREATE MULTISET TABLE EDW.SALES_FACT (SALE_ID BIGINT NOT NULL, SALE_DATE DATE, "
                                 "CUSTOMER_ID INTEGER, PRODUCT_ID INTEGER, QTY INTEGER, AMOUNT DECIMAL(18,2)) "
                                 "PRIMARY INDEX (SALE_ID) PARTITION BY RANGE_N(SALE_DATE BETWEEN DATE '2010-01-01' "
                                 "AND DATE '2030-12-31' EACH INTERVAL '1' MONTH);"),
    ("EDW", "PRODUCT"): ("T", "CREATE MULTISET TABLE EDW.PRODUCT (PRODUCT_ID INTEGER, PRODUCT_NAME VARCHAR(200)) "
                              "PRIMARY INDEX (PRODUCT_ID);"),
    ("EDW", "STG_SALES"): ("T", "CREATE MULTISET TABLE EDW.STG_SALES (SALE_ID BIGINT, SALE_DATE DATE, CUSTOMER_ID "
                                "INTEGER, PRODUCT_ID INTEGER, QTY INTEGER, AMOUNT DECIMAL(18,2)) NO PRIMARY INDEX;"),
    ("EDW", "SALES_DAILY_AGG"): ("T", "CREATE SET TABLE EDW.SALES_DAILY_AGG (SALE_DATE DATE, PRODUCT_ID INTEGER, "
                                      "AMOUNT DECIMAL(18,2)) PRIMARY INDEX (SALE_DATE, PRODUCT_ID);"),
    ("EDW", "OLD_SALES_2016"): ("T", "CREATE MULTISET TABLE EDW.OLD_SALES_2016 (SALE_ID BIGINT, PAYLOAD VARCHAR(4000)) "
                                     "PRIMARY INDEX (SALE_ID);"),
    ("EDW", "CAL_DATE"): ("T", "CREATE SET TABLE EDW.CAL_DATE (CAL_DATE DATE, FISCAL_QTR CHAR(6)) "
                               "UNIQUE PRIMARY INDEX (CAL_DATE);"),
    ("EDW", "ACCOUNT_BAL"): ("T", "CREATE MULTISET TABLE EDW.ACCOUNT_BAL (BAL_MONTH DATE, CUSTOMER_ID INTEGER, "
                                  "BALANCE DECIMAL(18,4)) PRIMARY INDEX (CUSTOMER_ID);"),
    ("EDW_V", "V_SALES"): ("V", "REPLACE VIEW EDW_V.V_SALES AS LOCKING ROW FOR ACCESS\n"
                                "SELECT f.SALE_ID, f.SALE_DATE, f.CUSTOMER_ID, p.PRODUCT_NAME, f.QTY, f.AMOUNT\n"
                                "FROM EDW.SALES_FACT f JOIN EDW.PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID;"),
    ("EDW_V", "V_SALES_MONTHLY"): ("V", "REPLACE VIEW EDW_V.V_SALES_MONTHLY AS LOCKING ROW FOR ACCESS\n"
                                        "SELECT EXTRACT(YEAR FROM v.SALE_DATE) AS SALE_YEAR, EXTRACT(MONTH FROM v.SALE_DATE) "
                                        "AS SALE_MONTH, SUM(v.AMOUNT) / SUM(v.QTY) AS AVG_PRICE\n"
                                        "FROM EDW_V.V_SALES v GROUP BY 1, 2;"),
    ("EDW_V", "V_CUSTOMER"): ("V", "REPLACE VIEW EDW_V.V_CUSTOMER AS LOCKING ROW FOR ACCESS\n"
                                   "SELECT c.CUSTOMER_ID, c.CUSTOMER_NAME, c.SEGMENT FROM EDW.CUSTOMER c\n"
                                   "WHERE c.SEGMENT = 'RETAIL';"),
    ("EDW_V", "V_UNUSED_PRODUCTS"): ("V", "REPLACE VIEW EDW_V.V_UNUSED_PRODUCTS AS\n"
                                          "SELECT DISTINCT p.* FROM EDW.PRODUCT p;"),
    ("EDW", "M_REFRESH_AGG"): ("M", "REPLACE MACRO EDW.M_REFRESH_AGG AS (\n"
                                    "DELETE FROM EDW.SALES_DAILY_AGG ALL;\n"
                                    "INSERT INTO EDW.SALES_DAILY_AGG SELECT SALE_DATE, PRODUCT_ID, SUM(AMOUNT)\n"
                                    "FROM EDW.SALES_FACT GROUP BY 1, 2;\n);"),
    ("EDW", "SP_FIX_CUSTOMERS"): ("P", "REPLACE PROCEDURE EDW.SP_FIX_CUSTOMERS()\nBEGIN\n"
                                       "  DECLARE v_id INTEGER;\n"
                                       "  FOR c AS cur CURSOR FOR SELECT CUSTOMER_ID FROM EDW.CUSTOMER WHERE SEGMENT IS NULL DO\n"
                                       "    UPDATE EDW.CUSTOMER SET SEGMENT = 'UNKNOWN' WHERE CUSTOMER_ID = c.CUSTOMER_ID;\n"
                                       "  END FOR;\nEND;"),
}

COLUMNS = {  # (db, table): [(name, type, length, digits, frac, nullable, uppercaseflag)]
    ("EDW", "CUSTOMER"): [("CUSTOMER_ID", "I", 4, None, None, "N", "N"), ("CUSTOMER_NAME", "CV", 100, None, None, "Y", "N"),
                          ("SEGMENT", "CF", 10, None, None, "Y", "C")],
    ("EDW", "SALES_FACT"): [("SALE_ID", "I8", 8, None, None, "N", "N"), ("SALE_DATE", "DA", 4, None, None, "Y", "N"),
                            ("CUSTOMER_ID", "I", 4, None, None, "Y", "N"), ("PRODUCT_ID", "I", 4, None, None, "Y", "N"),
                            ("QTY", "I", 4, None, None, "Y", "N"), ("AMOUNT", "D", 8, 18, 2, "Y", "N")],
    ("EDW", "PRODUCT"): [("PRODUCT_ID", "I", 4, None, None, "Y", "N"), ("PRODUCT_NAME", "CV", 200, None, None, "Y", "C")],
    ("EDW", "CAL_DATE"): [("CAL_DATE", "DA", 4, None, None, "Y", "N"), ("FISCAL_QTR", "CF", 6, None, None, "Y", "N")],
}

SIZES = {("EDW", "SALES_FACT"): 1_400_000_000_000, ("EDW", "CUSTOMER"): 4_000_000_000, ("EDW", "PRODUCT"): 90_000_000,
         ("EDW", "STG_SALES"): 2_000_000_000, ("EDW", "SALES_DAILY_AGG"): 30_000_000_000,
         ("EDW", "OLD_SALES_2016"): 600_000_000_000, ("EDW", "CAL_DATE"): 2_000_000, ("EDW", "ACCOUNT_BAL"): 8_000_000_000}

USAGE = [  # (objects touched, user, cadence, queries per day, query band)
    ([("EDW_V", "V_SALES_MONTHLY"), ("EDW_V", "V_SALES"), ("EDW", "SALES_FACT"), ("EDW", "PRODUCT")], "BI_SVC", "weekly", 6, None),
    ([("EDW_V", "V_CUSTOMER"), ("EDW", "CUSTOMER")], "CRM_APP", "weekly", 4, None),
    ([("EDW", "STG_SALES"), ("EDW", "SALES_FACT"), ("EDW", "SALES_DAILY_AGG"), ("EDW", "M_REFRESH_AGG")], "ETL_BATCH",
     "daily", 3, "ScriptName=load_sales.bteq;JobName=DAILY_SALES;"),
    ([("EDW", "ACCOUNT_BAL"), ("EDW", "SALES_FACT"), ("EDW", "CUSTOMER")], "ETL_BATCH", "month_end", 2,
     "ScriptName=month_end_balances.bteq;JobName=MONTH_END;"),
    ([("EDW", "CAL_DATE")], "ANALYST1", "weekly", 1, None),
]


def _cadence(c: str) -> list[date]:
    end, out = AS_OF.date(), []
    d = date(2025, 10, 1)
    while d <= end:
        if c == "daily" or (c == "weekly" and d.weekday() == 0):
            out.append(d)
        if c == "month_end" and (d + timedelta(days=1)).day == 1:
            out.append(d)
        d += timedelta(days=1)
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
    x("CREATE SCHEMA DBC")
    x("CREATE TABLE DBC.DBCInfoV (InfoKey VARCHAR, InfoData VARCHAR)")
    x("CREATE TABLE DBC.TablesV (DatabaseName VARCHAR, TableName VARCHAR, TableKind VARCHAR, CreateTimeStamp TIMESTAMP, "
      "LastAlterTimeStamp TIMESTAMP, RequestText VARCHAR, CommentString VARCHAR)")
    x("CREATE TABLE DBC.ColumnsV (DatabaseName VARCHAR, TableName VARCHAR, ColumnName VARCHAR, ColumnId INTEGER, "
      "ColumnType VARCHAR, ColumnLength INTEGER, DecimalTotalDigits INTEGER, DecimalFractionalDigits INTEGER, "
      "Nullable VARCHAR, UpperCaseFlag VARCHAR, CharType INTEGER)")
    x("CREATE TABLE DBC.TableSizeV (Vproc INTEGER, DatabaseName VARCHAR, TableName VARCHAR, CurrentPerm BIGINT)")
    x("CREATE TABLE DBC.QryLogV (QueryID BIGINT, UserName VARCHAR, StartTime TIMESTAMP, StatementType VARCHAR, "
      "QueryBand VARCHAR, QueryText VARCHAR)")
    x("CREATE TABLE DBC.QryLogObjectsV (QueryID BIGINT, ObjectDatabaseName VARCHAR, ObjectTableName VARCHAR, "
      "ObjectType VARCHAR)")
    x("CREATE TABLE DBC.AccessRightsV (UserName VARCHAR, DatabaseName VARCHAR, TableName VARCHAR, AccessRight VARCHAR, "
      "GrantorName VARCHAR)")

    def ins(table: str, rows: list[tuple]) -> None:
        bulk_insert(con, table, rows)

    ins("DBC.DBCInfoV", [("VERSION", "17.20.03.15"), ("RELEASE", "17.20.03.15"), ("LANGUAGE SUPPORT MODE", "Standard")])
    ins("DBC.TablesV", [(db, name, kind, datetime(2016, 5, 1) + timedelta(days=i * 31), datetime(2024, 2, 1), text, None)
                        for i, ((db, name), (kind, text)) in enumerate(DDL.items())]
        + [("DBC", "TVM", "T", datetime(2010, 1, 1), datetime(2010, 1, 1), None, None)])
    cols = []
    for (db, t), cs in COLUMNS.items():
        for i, (c, typ, length, digits, frac, null, flag) in enumerate(cs, 1):
            cols.append((db, t, c, 1024 + i, typ, length, digits, frac, null, flag, 1 if typ in ("CV", "CF") else 0))
    ins("DBC.ColumnsV", cols)
    sizes = []
    for (db, t), perm in SIZES.items():
        for vproc in range(4):  # spread across AMPs (summed by the harvester)
            sizes.append((vproc, db, t, perm // 4))
    ins("DBC.TableSizeV", sizes)

    qlog, qobj = [], []
    qid = 1000
    for objs, user, cadence, per_day, band in USAGE:
        for d in _cadence(cadence):
            for k in range(per_day):
                qid += 1
                qlog.append((qid, user, datetime.combine(d, datetime.min.time()) + timedelta(hours=6, minutes=k),
                             "Select", band, f"SELECT * FROM EDW_V.V_CUSTOMER WHERE CUSTOMER_NAME = '{CANARY}'"))
                qobj.extend((qid, db, name, "Tab") for db, name in objs)
    ins("DBC.QryLogV", qlog)
    ins("DBC.QryLogObjectsV", qobj)
    ins("DBC.AccessRightsV", [("BI_SVC", "EDW_V", "All", "R", "DBA"), ("ETL_BATCH", "EDW", "All", "I", "DBA"),
                              ("ETL_BATCH", "EDW", "All", "D", "DBA"), ("CRM_APP", "EDW_V", "V_CUSTOMER", "R", "DBA"),
                              ("ETL_BATCH", "EDW", "M_REFRESH_AGG", "E", "DBA"), ("DBA", "DBC", "All", "R", "DBC")])
    if user_data:
        x("CREATE SCHEMA EDW")
        x("CREATE TABLE EDW.CUSTOMER (CUSTOMER_ID INTEGER, CUSTOMER_NAME VARCHAR, SEGMENT VARCHAR)")
        x(f"INSERT INTO EDW.CUSTOMER VALUES (7, '{CANARY} Grace', 'RETAIL')")
    return con
