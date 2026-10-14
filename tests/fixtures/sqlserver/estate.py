"""Emulated SQL Server estate ("SalesDW") in DuckDB.

Catalog tables are shaped like the real SQL Server views (``sys.objects``,
``sys.sql_modules``, ``sys.columns``, ``sys.sql_expression_dependencies``,
Query Store, ``msdb`` SQL Agent tables, ``SSISDB.catalog``). The estate has
~60 database objects plus Agent jobs and SSIS packages, with:

- T-SQL procedures containing cursors, WHILE loops, dynamic SQL, TRY/CATCH,
  RAISERROR, @@ROWCOUNT/@@ERROR and full truncate-and-reload patterns;
- a four-deep view chain, unused/legacy objects, a dormant quarter-end view,
  month-end and regulatory procedures on a monthly Agent schedule;
- *user tables with rows* carrying canary values, which a correct extraction
  agent can never read.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb

HERE = Path(__file__).parent
SSIS_DIR = HERE / "ssis"
AS_OF = datetime(2026, 9, 30, 23, 0, 0)
DB = "SalesDW"
CANARY = "CANARY-ROWDATA-7731"
CANARY_QUERY_LITERAL = "CANARY-ROWDATA-QUERYTEXT-55"

# (schema, table, [(column, type, max_length, precision, scale, nullable)])
_I = ("int", 4, 10, 0)
_BI = ("bigint", 8, 19, 0)
_DT = ("date", 3, 10, 0)
_DTM = ("datetime", 8, 23, 3)
_MONEY = ("money", 8, 19, 4)


def _nv(n: int) -> tuple:
    return ("nvarchar", n * 2, 0, 0)


def _v(n: int) -> tuple:
    return ("varchar", n, 0, 0)


def _dec(p: int, s: int) -> tuple:
    return ("decimal", 9, p, s)


TABLES: dict[str, list[tuple[str, tuple, bool]]] = {
    "stg.Customer_Load": [("CustomerCode", _nv(20), False), ("CustomerName", _nv(100), True), ("Segment", _nv(50), True),
                          ("Email", _nv(200), True), ("Phone", _v(30), True), ("PostalCode", _v(10), True),
                          ("Country", _v(2), True)],
    "stg.Sales_Load": [("OrderNumber", _v(20), False), ("OrderDate", _DT, False), ("DateKey", _I, False),
                       ("CustomerKey", _I, False), ("ProductKey", _I, False), ("StoreKey", _I, False),
                       ("Quantity", _I, False), ("Amount", _MONEY, False)],
    "stg.Product_Load": [("ProductCode", _nv(20), False), ("ProductName", _nv(100), True),
                         ("StandardCost", _MONEY, True), ("ListPrice", _MONEY, True)],
    "stg.Inventory_Load": [("ProductKey", _I, False), ("StoreKey", _I, False), ("OnHandQty", _I, False),
                           ("SnapshotDate", _DT, False)],
    "stg.Returns_Load": [("ReturnId", _I, False), ("ProductCode", _nv(20), False), ("ReturnDate", _DT, False),
                         ("Quantity", _I, False), ("Reason", _nv(200), True)],
    "dbo.DimCustomer": [("CustomerKey", _I, False), ("CustomerCode", _nv(20), False), ("CustomerName", _nv(100), True),
                        ("Segment", _nv(50), True), ("CreatedDate", _DTM, True), ("UpdatedDate", _DTM, True)],
    "dbo.CustomerAddress": [("CustomerKey", _I, False), ("Email", _nv(200), True), ("Phone", _v(30), True),
                            ("PostalCode", _v(10), True), ("Country", _v(2), True)],
    "dbo.DimProduct": [("ProductKey", _I, False), ("ProductCode", _nv(20), False), ("ProductName", _nv(100), True),
                       ("StandardCost", _MONEY, True), ("ListPrice", _MONEY, True)],
    "dbo.DimDate": [("DateKey", _I, False), ("FullDate", _DT, False), ("CalendarYear", _I, False),
                    ("CalendarMonth", _I, False), ("FiscalQuarter", ("tinyint", 1, 3, 0), False)],
    "dbo.DimStore": [("StoreKey", _I, False), ("StoreName", _nv(100), False), ("RegionKey", _I, False)],
    "dbo.Region": [("RegionKey", _I, False), ("RegionName", _nv(50), False)],
    "dbo.DimEmployee": [("EmployeeKey", _I, False), ("EmployeeName", _nv(100), False), ("StoreKey", _I, True),
                        ("Salary", _MONEY, True)],
    "dbo.FactSales": [("OrderNumber", _v(20), False), ("OrderDate", _DT, False), ("DateKey", _I, False),
                      ("CustomerKey", _I, False), ("ProductKey", _I, False), ("StoreKey", _I, False),
                      ("Quantity", _I, False), ("Amount", _MONEY, False)],
    "dbo.FactInventory": [("ProductKey", _I, False), ("StoreKey", _I, False), ("OnHandQty", _I, False),
                          ("SnapshotDate", _DT, False)],
    "dbo.FactReturns": [("ReturnId", _I, False), ("ProductKey", _I, False), ("ReturnDate", _DT, False),
                        ("Quantity", _I, False), ("Reason", _nv(200), True)],
    "dbo.FactBudget": [("CostCenter", _v(20), False), ("FiscalYear", _I, False), ("BudgetAmount", _MONEY, True),
                       ("ActualAmount", _MONEY, True)],
    "dbo.SalesTarget": [("RegionName", _nv(50), False), ("CalendarYear", _I, False), ("TargetAmount", _MONEY, True)],
    "dbo.ExchangeRate": [("CurrencyCode", ("char", 3, 0, 0), False), ("RateDate", _DT, False),
                         ("Rate", _dec(18, 8), False)],
    "dbo.Promotion": [("PromotionKey", _I, False), ("PromotionName", _nv(100), False)],
    "dbo.Customer_Backup_2019": [("CustomerKey", _I, False), ("CustomerName", _nv(100), True),
                                 ("Payload", ("xml", -1, 0, 0), True)],
    "dbo.tmp_SalesFix": [("OrderNumber", _v(20), False), ("Amount", _MONEY, True)],
    "dbo.OldBudget2018": [("CostCenter", _v(20), False), ("FiscalYear", _I, False), ("BudgetAmount", _MONEY, True)],
    "dbo.FactSales_Archive": [("OrderNumber", _v(20), False), ("OrderDate", _DT, False), ("DateKey", _I, False),
                              ("CustomerKey", _I, False), ("ProductKey", _I, False), ("StoreKey", _I, False),
                              ("Quantity", _I, False), ("Amount", _MONEY, False)],
    "audit.LoadLog": [("LoadLogId", _BI, False), ("ProcName", ("sysname", 256, 0, 0), False), ("RowsAffected", _I, True),
                      ("Status", _v(20), True), ("LoggedAt", ("datetime2", 8, 27, 7), False)],
    "audit.ErrorLog": [("ErrorLogId", _BI, False), ("ProcName", ("sysname", 256, 0, 0), False),
                       ("ErrorNumber", _I, True), ("ErrorMessage", _nv(-1), True),
                       ("LoggedAt", ("datetime2", 8, 27, 7), False)],
    "audit.SalesAudit": [("OrderNumber", _v(20), False), ("Action", ("char", 1, 0, 0), False), ("ChangedAt", _DTM, False)],
    "rpt.MonthEndClose": [("PeriodKey", _I, False), ("RegionName", _nv(50), False), ("Revenue", _MONEY, True),
                          ("Returns", _I, True), ("ClosedAt", _DTM, False)],
    "rpt.RegulatoryFiling": [("PeriodKey", _I, False), ("RegionName", _nv(50), False), ("Revenue", _MONEY, True),
                             ("FiledAt", _DTM, False)],
}

ROW_COUNTS = {
    "dbo.FactSales": 250_000_000, "dbo.FactSales_Archive": 900_000_000, "dbo.FactInventory": 40_000_000,
    "dbo.DimCustomer": 2_500_000, "dbo.CustomerAddress": 2_400_000, "stg.Sales_Load": 1_200_000,
    "dbo.FactReturns": 3_000_000, "dbo.DimDate": 7_305, "dbo.DimProduct": 45_000, "dbo.DimStore": 640,
    "dbo.Region": 12, "audit.LoadLog": 180_000, "audit.SalesAudit": 9_000_000, "dbo.Customer_Backup_2019": 1_900_000,
}

SCHEMAS = {"dbo": 1, "stg": 5, "rpt": 6, "audit": 7, "etl": 8}
TYPE_CODES = {"FUNCTION": None, "VIEW": "V", "PROCEDURE": "P", "TRIGGER": "TR"}
TYPE_DESC = {"U": "USER_TABLE", "V": "VIEW", "P": "SQL_STORED_PROCEDURE", "FN": "SQL_SCALAR_FUNCTION",
             "IF": "SQL_INLINE_TABLE_VALUED_FUNCTION", "TF": "SQL_TABLE_VALUED_FUNCTION", "TR": "SQL_TRIGGER"}

# Query Store ad hoc workload: (text, cadence, executions per interval)
ADHOC = [
    ("SELECT RegionName, CalendarYear, Amount FROM rpt.vw_SalesByRegion WHERE CalendarYear = 2026", "weekly", 40),
    ("SELECT * FROM rpt.vw_ExecDashboard ORDER BY CalendarYear, CalendarMonth", "weekly", 25),
    ("SELECT TOP 100 * FROM rpt.vw_CustomerSales ORDER BY Amount DESC", "weekly", 12),
    ("SELECT ProductName, OnHandQty FROM rpt.vw_InventoryStatus WHERE OnHandQty < 10", "weekly", 30),
    ("SELECT CustomerKey, Email FROM rpt.vw_CustomerPII WHERE PostalCode = '10001'", "weekly", 5),
    ("SELECT PeriodKey, Revenue FROM rpt.vw_MonthEnd", "monthly", 8),
    ("SELECT ProductName, Margin FROM rpt.vw_ProductMargin", "quarter_end_2026_03", 3),
    (f"SELECT CustomerKey FROM dbo.DimCustomer WHERE CustomerName = '{CANARY_QUERY_LITERAL}'", "weekly", 2),
    ("SELECT CurrencyCode, Rate FROM dbo.ExchangeRate", "until_2025_06", 4),
    ("SELECT d.CalendarYear, f.Amount FROM dbo.FactSales f JOIN dbo.DimDate d ON d.DateKey = f.DateKey", "weekly", 10),
    ("SELECT EmployeeName, StoreKey FROM dbo.DimEmployee", "monthly", 1),
    ("SELECT r.ReturnDate, r.Reason FROM rpt.vw_Returns r", "until_2025_06", 2),
]

PROC_STATS = {  # name: (execution_count, last_execution_time)
    "etl.usp_LogLoad": (150, datetime(2026, 9, 30, 2, 40)),
    "etl.usp_LoadDimCustomer": (30, datetime(2026, 9, 30, 2, 5)),
    "etl.usp_LoadDimProduct": (30, datetime(2026, 9, 30, 2, 10)),
    "etl.usp_LoadFactSales": (30, datetime(2026, 9, 30, 2, 20)),
    "etl.usp_LoadFactInventory": (30, datetime(2026, 9, 30, 2, 30)),
    "etl.usp_LoadFactReturns": (30, datetime(2026, 9, 30, 2, 35)),
    "etl.usp_MonthEndClose": (1, datetime(2026, 9, 1, 3, 0)),
    "etl.usp_RegulatoryFiling": (1, datetime(2026, 9, 1, 3, 30)),
    "dbo.usp_GetCustomerOrders": (5400, datetime(2026, 9, 30, 17, 12)),
    "dbo.usp_SearchCustomers": (800, datetime(2026, 9, 30, 16, 2)),
    "dbo.usp_RefreshExchangeRates": (3, datetime(2025, 5, 10, 4, 0)),
}

JOBS = [  # (name, enabled, freq_type or None, [(step_name, subsystem, command)], history cadence)
    ("Nightly DW Load", 1, 4, [
        ("Dim customer", "TSQL", "EXEC etl.usp_LoadDimCustomer"),
        ("Dim product", "TSQL", "EXEC etl.usp_LoadDimProduct"),
        ("Fact sales", "TSQL", "EXEC etl.usp_LoadFactSales"),
        ("Fact inventory", "TSQL", "EXEC etl.usp_LoadFactInventory"),
        ("Fact returns", "TSQL", "EXEC etl.usp_LoadFactReturns"),
    ], "daily"),
    ("SSIS Staging Load", 1, 4, [
        ("Staging", "SSIS", '/ISSERVER "\\"\\SSISDB\\DW\\Staging\\LoadStaging.dtsx\\"" /SERVER "\\"SQLPROD01\\""'),
        ("Products", "SSIS", '/ISSERVER "\\"\\SSISDB\\DW\\Staging\\LoadProducts.dtsx\\"" /SERVER "\\"SQLPROD01\\""'),
    ], "daily"),
    ("Month End Close", 1, 16, [
        ("Close period", "TSQL", "DECLARE @p INT = CONVERT(INT, FORMAT(DATEADD(month, -1, GETDATE()), 'yyyyMM'));\n"
                                 "EXEC etl.usp_MonthEndClose @PeriodKey = @p"),
        ("Regulatory filing", "TSQL", "DECLARE @p INT = CONVERT(INT, FORMAT(DATEADD(month, -1, GETDATE()), 'yyyyMM'));\n"
                                      "EXEC etl.usp_RegulatoryFiling @PeriodKey = @p"),
    ], "monthly"),
    ("Weekly FX Refresh", 0, 8, [("Refresh", "TSQL", "EXEC dbo.usp_RefreshExchangeRates")], "until_2025_05"),
    ("Legacy Budget Reconcile", 0, None, [("Reconcile", "TSQL", "EXEC dbo.usp_Old_ReconcileBudget")], "once_2023"),
]

SSIS = [("DW", "Staging", "LoadStaging.dtsx", "daily"), ("DW", "Staging", "LoadProducts.dtsx", "daily"),
        ("Legacy", "Budget", "ExportBudget.dtsx", None)]

PERMISSIONS = [  # (grantee, type_desc, permission, state, object)
    ("bi_readers", "DATABASE_ROLE", "SELECT", "GRANT", "rpt.vw_SalesByRegion"),
    ("bi_readers", "DATABASE_ROLE", "SELECT", "GRANT", "rpt.vw_ExecDashboard"),
    ("bi_readers", "DATABASE_ROLE", "SELECT", "GRANT", "rpt.vw_CustomerSales"),
    ("bi_readers", "DATABASE_ROLE", "SELECT", "GRANT", "rpt.vw_InventoryStatus"),
    ("bi_readers", "DATABASE_ROLE", "SELECT", "GRANT", "rpt.vw_MonthEnd"),
    ("finance_readers", "DATABASE_ROLE", "SELECT", "GRANT", "rpt.vw_CustomerPII"),
    ("analysts", "DATABASE_ROLE", "SELECT", "GRANT", "dbo.FactSales"),
    ("analysts", "DATABASE_ROLE", "SELECT", "GRANT", "dbo.DimCustomer"),
    ("analysts", "DATABASE_ROLE", "SELECT", "DENY", "dbo.DimEmployee"),
    ("etl_svc", "SQL_USER", "EXECUTE", "GRANT", "etl.usp_LoadFactSales"),
    ("etl_svc", "SQL_USER", "EXECUTE", "GRANT", "etl.usp_MonthEndClose"),
    ("app_user", "SQL_USER", "EXECUTE", "GRANT", "dbo.usp_GetCustomerOrders"),
    ("app_user", "SQL_USER", "EXECUTE", "GRANT", "dbo.usp_SearchCustomers"),
]


def _modules() -> list[tuple[str, str, str]]:
    """(schema.name, type_code, definition) from modules.sql."""
    text = (HERE / "modules.sql").read_text()
    out = []
    for chunk in re.split(r"^GO\s*$", text, flags=re.MULTILINE):
        body = "\n".join(l for l in chunk.strip().splitlines() if not (l.startswith("-- ") and "module script" in l
                                                                         or l.startswith("-- Used by")))
        body = body.strip()
        m = re.match(r"CREATE\s+(FUNCTION|VIEW|PROCEDURE|TRIGGER)\s+([\w.]+)", body, re.IGNORECASE)
        if not m:
            continue
        kind, name = m.group(1).upper(), m.group(2)
        code = TYPE_CODES[kind]
        if code is None:
            code = "IF" if re.search(r"RETURNS\s+TABLE", body, re.I) else "FN"
        out.append((name, code, body + "\n"))
    return out


def _weeks(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        out.append(d)
        d += timedelta(days=7)
    return out


def _cadence_dates(cadence: str | None) -> list[date]:
    end = AS_OF.date()
    if cadence == "weekly":
        return _weeks(date(2025, 6, 2), end - timedelta(days=2))
    if cadence == "daily":
        out, d = [], date(2025, 6, 1)
        while d <= end:
            out.append(d)
            d += timedelta(days=1)
        return out
    if cadence == "monthly":
        out, d = [], date(2025, 6, 1)
        while d <= end:
            out.append(d)
            d = (d.replace(day=28) + timedelta(days=5)).replace(day=1)
        return out
    if cadence == "quarter_end_2026_03":
        return [date(2026, 3, 30), date(2026, 4, 2)]
    if cadence == "until_2025_06":
        return _weeks(date(2025, 6, 2), date(2025, 6, 30))
    if cadence == "until_2025_05":
        return _weeks(date(2025, 3, 1), date(2025, 5, 10))
    if cadence == "once_2023":
        return [date(2023, 3, 31)]
    return []


def build(*, query_store: bool = True, user_data: bool = True) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    x = con.execute
    x("CREATE SCHEMA sys")
    x("CREATE TABLE sys.schemas (schema_id INTEGER, name VARCHAR, principal_id INTEGER)")
    x("CREATE TABLE sys.objects (object_id INTEGER, name VARCHAR, schema_id INTEGER, parent_object_id INTEGER, "
      "type VARCHAR, type_desc VARCHAR, create_date TIMESTAMP, modify_date TIMESTAMP, is_ms_shipped INTEGER)")
    x("CREATE TABLE sys.sql_modules (object_id INTEGER, definition VARCHAR, uses_ansi_nulls INTEGER)")
    x("CREATE TABLE sys.types (user_type_id INTEGER, system_type_id INTEGER, name VARCHAR)")
    x("CREATE TABLE sys.columns (object_id INTEGER, name VARCHAR, column_id INTEGER, user_type_id INTEGER, "
      "max_length INTEGER, precision INTEGER, scale INTEGER, is_nullable INTEGER, collation_name VARCHAR, "
      "is_identity INTEGER)")
    x("CREATE TABLE sys.sql_expression_dependencies (referencing_id INTEGER, referencing_minor_id INTEGER, "
      "referenced_server_name VARCHAR, referenced_database_name VARCHAR, referenced_schema_name VARCHAR, "
      "referenced_entity_name VARCHAR, referenced_id INTEGER, is_caller_dependent INTEGER)")
    x("CREATE TABLE sys.dm_db_partition_stats (object_id INTEGER, index_id INTEGER, partition_number INTEGER, "
      "row_count BIGINT, reserved_page_count BIGINT)")
    x("CREATE TABLE sys.database_query_store_options (desired_state_desc VARCHAR, actual_state_desc VARCHAR)")
    x("CREATE TABLE sys.query_store_query_text (query_text_id INTEGER, query_sql_text VARCHAR)")
    x("CREATE TABLE sys.query_store_query (query_id INTEGER, query_text_id INTEGER, object_id INTEGER)")
    x("CREATE TABLE sys.query_store_plan (plan_id INTEGER, query_id INTEGER)")
    x("CREATE TABLE sys.query_store_runtime_stats_interval (runtime_stats_interval_id INTEGER, start_time TIMESTAMP, "
      "end_time TIMESTAMP)")
    x("CREATE TABLE sys.query_store_runtime_stats (runtime_stats_id INTEGER, plan_id INTEGER, "
      "runtime_stats_interval_id INTEGER, count_executions BIGINT, last_execution_time TIMESTAMP)")
    x("CREATE TABLE sys.dm_exec_query_stats (sql_handle VARCHAR, execution_count BIGINT, creation_time TIMESTAMP, "
      "last_execution_time TIMESTAMP)")
    x("CREATE TABLE sys._sql_text (sql_handle VARCHAR, dbid INTEGER, objectid INTEGER, text VARCHAR)")
    x("CREATE MACRO sys.dm_exec_sql_text(h) AS TABLE SELECT dbid, objectid, text FROM sys._sql_text WHERE sql_handle = h")
    x("CREATE TABLE sys.dm_exec_procedure_stats (database_id INTEGER, object_id INTEGER, cached_time TIMESTAMP, "
      "last_execution_time TIMESTAMP, execution_count BIGINT)")
    x("CREATE TABLE sys.database_principals (principal_id INTEGER, name VARCHAR, type_desc VARCHAR)")
    x("CREATE TABLE sys.database_permissions (class INTEGER, class_desc VARCHAR, major_id INTEGER, "
      "grantee_principal_id INTEGER, permission_name VARCHAR, state_desc VARCHAR)")
    x("CREATE MACRO serverproperty(p) AS CASE WHEN p = 'ProductVersion' THEN '16.0.4135.4' ELSE NULL END")
    x(f"CREATE MACRO db_name() AS '{DB}'")
    x("CREATE MACRO db_id() AS 5")

    x("ATTACH ':memory:' AS msdb")
    x("CREATE SCHEMA msdb.dbo")
    x("CREATE TABLE msdb.dbo.sysjobs (job_id VARCHAR, name VARCHAR, enabled INTEGER, description VARCHAR)")
    x("CREATE TABLE msdb.dbo.sysjobsteps (job_id VARCHAR, step_id INTEGER, step_name VARCHAR, subsystem VARCHAR, "
      "command VARCHAR, database_name VARCHAR)")
    x("CREATE TABLE msdb.dbo.sysschedules (schedule_id INTEGER, name VARCHAR, enabled INTEGER, freq_type INTEGER, "
      "freq_interval INTEGER)")
    x("CREATE TABLE msdb.dbo.sysjobschedules (schedule_id INTEGER, job_id VARCHAR)")
    x("CREATE TABLE msdb.dbo.sysjobhistory (instance_id INTEGER, job_id VARCHAR, step_id INTEGER, run_status INTEGER, "
      "run_date INTEGER, run_time INTEGER)")
    x("ATTACH ':memory:' AS SSISDB")
    x("CREATE SCHEMA SSISDB.catalog")
    x("CREATE TABLE SSISDB.catalog.folders (folder_id INTEGER, name VARCHAR)")
    x("CREATE TABLE SSISDB.catalog.projects (project_id INTEGER, folder_id INTEGER, name VARCHAR, "
      "last_deployed_time TIMESTAMP)")
    x("CREATE TABLE SSISDB.catalog.packages (package_id INTEGER, project_id INTEGER, name VARCHAR)")
    x("CREATE TABLE SSISDB.catalog.executions (execution_id INTEGER, folder_name VARCHAR, project_name VARCHAR, "
      "package_name VARCHAR, status INTEGER, start_time TIMESTAMP, executed_as_name VARCHAR)")

    ins = lambda table, rows: rows and con.executemany(  # noqa: E731
        f"INSERT INTO {table} VALUES ({', '.join('?' for _ in rows[0])})", rows)

    ins("sys.schemas", [(sid, name, 1) for name, sid in SCHEMAS.items()])
    type_ids: dict[str, int] = {}
    for t in sorted({c[1][0] for cols in TABLES.values() for c in cols}):
        type_ids[t] = len(type_ids) + 34
    ins("sys.types", [(tid, tid, name) for name, tid in type_ids.items()])

    ids: dict[str, int] = {}
    objects, columns = [], []
    created = datetime(2017, 4, 3, 9, 0)
    for i, (fq, cols) in enumerate(TABLES.items()):
        sch, name = fq.split(".")
        oid = 245_575_913 + i * 16
        ids[fq.lower()] = oid
        objects.append((oid, name, SCHEMAS[sch], 0, "U", TYPE_DESC["U"], created + timedelta(days=i * 30),
                        created + timedelta(days=i * 45), 0))
        for ci, (cname, (tname, length, prec, scale), nullable) in enumerate(cols, 1):
            if tname == "nvarchar" and length == -2:
                length = -1
            collation = "SQL_Latin1_General_CP1_CI_AS" if "char" in tname or tname == "sysname" else None
            columns.append((oid, cname, ci, type_ids[tname], length, prec, scale, int(nullable), collation,
                            int(ci == 1 and cname.endswith(("Key", "Id")) and not fq.startswith("stg"))))
    modules = _modules()
    for j, (fq, code, body) in enumerate(modules):
        sch, name = fq.split(".")
        oid = 645_577_338 + j * 16
        ids[fq.lower()] = oid
        parent = ids["dbo.factsales"] if code == "TR" else 0
        objects.append((oid, name, SCHEMAS[sch], parent, code, TYPE_DESC[code], created + timedelta(days=200 + j * 20),
                        datetime(2024, 1, 15) + timedelta(days=j * 13), 0))
    # one system object that must be filtered out
    objects.append((-101, "sysdiagrams", 1, 0, "U", "USER_TABLE", created, created, 1))
    ins("sys.objects", objects)
    ins("sys.columns", columns)
    ins("sys.sql_modules", [(ids[fq.lower()], body, 1) for fq, _, body in modules])
    # view columns (subset — views expose their select list)
    view_cols = {"rpt.vw_SalesByRegion": [("RegionName", "nvarchar"), ("CalendarYear", "int"), ("Amount", "money")],
                 "rpt.vw_CustomerPII": [("CustomerKey", "int"), ("CustomerName", "nvarchar"), ("Email", "nvarchar"),
                                         ("Phone", "varchar"), ("PostalCode", "varchar")]}
    ins("sys.columns", [(ids[v.lower()], c, i, type_ids[t], 100 if "char" in t else 4, 0, 0, 1,
                         "SQL_Latin1_General_CP1_CI_AS" if "char" in t else None, 0)
                        for v, cols in view_cols.items() for i, (c, t) in enumerate(cols, 1)])

    # SQL Server records static references only (never through dynamic SQL strings).
    from altitude_connectors.sqlrefs import blank_comments_and_strings

    deps = []
    names = sorted(ids, key=len, reverse=True)
    for fq, _, body in modules:
        clean = blank_comments_and_strings(body).lower()
        for target in names:
            if target == fq.lower():
                continue
            if re.search(rf"(?<![\w.]){re.escape(target)}(?![\w])", clean):
                sch, ent = target.split(".")
                deps.append((ids[fq.lower()], 0, None, None, sch, ent, ids[target], 0))
    deps.append((ids["dbo.usp_refreshexchangerates"], 0, "FXSRV", "Treasury", "dbo", "DailyRates", None, 0))
    ins("sys.sql_expression_dependencies", deps)

    ins("sys.dm_db_partition_stats", [(ids[fq.lower()], 1, 1, rows, max(rows // 60, 9)) for fq, rows in ROW_COUNTS.items()])

    # ---------------------------------------------------------------- usage
    ins("sys.database_query_store_options", [("READ_WRITE", "READ_WRITE" if query_store else "OFF")])
    intervals: dict[date, int] = {}
    qs_text, qs_query, qs_plan, qs_stats, pc_stats, pc_text = [], [], [], [], [], []
    for qi, (text, cadence, count) in enumerate(ADHOC, 1):
        qs_text.append((qi, text))
        qs_query.append((qi, qi, 0))
        qs_plan.append((qi, qi))
        dates = _cadence_dates(cadence)
        for d in dates:
            iid = intervals.setdefault(d, len(intervals) + 1)
            qs_stats.append((len(qs_stats) + 1, qi, iid, count, datetime(d.year, d.month, d.day, 14)))
        if dates:
            pc_stats.append((f"0x{qi:04X}", count * len(dates), datetime(2025, 6, 1),
                             datetime(dates[-1].year, dates[-1].month, dates[-1].day, 14)))
            pc_text.append((f"0x{qi:04X}", 5, None, text))
    # module statements: one inside a scalar function (counts as function usage), one inside a procedure (ignored)
    module_q = [(ids["dbo.fn_fiscalquarter"], "RETURN CASE WHEN MONTH(@d) BETWEEN 7 AND 9 THEN 1 END", 200),
                (ids["dbo.usp_getcustomerorders"], "SELECT DISTINCT f.OrderNumber FROM dbo.FactSales f", 100)]
    for mo, text, count in module_q:
        qi = len(qs_text) + 1
        qs_text.append((qi, text))
        qs_query.append((qi, qi, mo))
        qs_plan.append((qi, qi))
        for d in _cadence_dates("weekly"):
            iid = intervals.setdefault(d, len(intervals) + 1)
            qs_stats.append((len(qs_stats) + 1, qi, iid, count, datetime(d.year, d.month, d.day, 15)))
        pc_stats.append((f"0xM{qi:03X}", count, datetime(2026, 9, 1), datetime(2026, 9, 29)))
        pc_text.append((f"0xM{qi:03X}", 5, mo, text))
    ins("sys.query_store_query_text", qs_text)
    ins("sys.query_store_query", qs_query)
    ins("sys.query_store_plan", qs_plan)
    ins("sys.query_store_runtime_stats_interval",
        [(iid, datetime(d.year, d.month, d.day), datetime(d.year, d.month, d.day, 23, 59)) for d, iid in intervals.items()])
    ins("sys.query_store_runtime_stats", qs_stats)
    ins("sys.dm_exec_query_stats", pc_stats)
    ins("sys._sql_text", pc_text)
    ins("sys.dm_exec_procedure_stats", [(5, ids[p.lower()], datetime(2026, 8, 31), last, n)
                                        for p, (n, last) in PROC_STATS.items()]
        + [(7, 999, datetime(2026, 8, 31), datetime(2026, 9, 30), 77)])  # another database: filtered by DB_ID()

    principals = sorted({(p[0], p[1]) for p in PERMISSIONS})
    pid = {name: i + 5 for i, (name, _) in enumerate(principals)}
    ins("sys.database_principals", [(pid[n], n, t) for n, t in principals])
    ins("sys.database_permissions", [(1, "OBJECT_OR_COLUMN", ids[o.lower()], pid[g], perm, st)
                                     for g, _, perm, st, o in PERMISSIONS]
        + [(0, "DATABASE", 0, pid["analysts"], "CONNECT", "GRANT")])

    # ---------------------------------------------------------------- SQL Agent
    jobs, steps, schedules, jobsched, history = [], [], [], [], []
    for ji, (name, enabled, freq, jsteps, cadence) in enumerate(JOBS, 1):
        jid = f"{ji:08X}-0000-4000-8000-00000000000{ji}"
        jobs.append((jid, name, enabled, None))
        for si, (sname, subsystem, cmd) in enumerate(jsteps, 1):
            steps.append((jid, si, sname, subsystem, cmd, DB if subsystem == "TSQL" else None))
        if freq is not None:
            schedules.append((ji, f"{name} schedule", enabled, freq, 1))
            jobsched.append((ji, jid))
        for d in _cadence_dates(cadence):
            history.append((len(history) + 1, jid, 0, 1, int(d.strftime("%Y%m%d")), 20000))
            history.append((len(history) + 1, jid, 1, 1, int(d.strftime("%Y%m%d")), 20000))
    ins("msdb.dbo.sysjobs", jobs)
    ins("msdb.dbo.sysjobsteps", steps)
    ins("msdb.dbo.sysschedules", schedules)
    ins("msdb.dbo.sysjobschedules", jobsched)
    ins("msdb.dbo.sysjobhistory", history)

    folders = sorted({f for f, _, _, _ in SSIS})
    ins("SSISDB.catalog.folders", [(i + 1, f) for i, f in enumerate(folders)])
    projects = sorted({(f, p) for f, p, _, _ in SSIS})
    ins("SSISDB.catalog.projects", [(i + 1, folders.index(f) + 1, p, datetime(2024, 11, 2)) for i, (f, p) in enumerate(projects)])
    ins("SSISDB.catalog.packages", [(i + 1, projects.index((f, p)) + 1, k) for i, (f, p, k, _) in enumerate(SSIS)])
    execs = []
    for f, p, k, cadence in SSIS:
        for d in _cadence_dates(cadence):
            execs.append((len(execs) + 1, f, p, k, 7, datetime(d.year, d.month, d.day, 1, 30), "CORP\\svc_ssis"))
    ins("SSISDB.catalog.executions", execs)

    # ---------------------------------------------------------------- user data (must never be harvested)
    if user_data:
        for sch in ("dbo", "stg", "rpt", "audit", "etl"):
            x(f"CREATE SCHEMA IF NOT EXISTS {sch}")
        x("CREATE TABLE dbo.DimCustomer (CustomerKey INTEGER, CustomerCode VARCHAR, CustomerName VARCHAR, Segment VARCHAR)")
        x(f"INSERT INTO dbo.DimCustomer VALUES (1, 'C-0001', '{CANARY}-Jane Doe', 'Retail'), "
          f"(2, 'C-0002', '{CANARY}-John Roe', 'SMB')")
        x("CREATE TABLE dbo.CustomerAddress (CustomerKey INTEGER, Email VARCHAR, Phone VARCHAR, PostalCode VARCHAR, Country VARCHAR)")
        x(f"INSERT INTO dbo.CustomerAddress VALUES (1, '{CANARY}@example.com', '555-0100', '10001', 'US')")
        x("CREATE TABLE dbo.FactSales (OrderNumber VARCHAR, Amount DECIMAL(19,4))")
        x(f"INSERT INTO dbo.FactSales VALUES ('{CANARY}-SO-1', 12.5)")
    return con
