"""Kill-test (principle 6): the read-only connection has no write capability.

Every write/DDL/DCL/procedural statement — including multi-statement smuggling
and comment tricks — is refused *before* the driver sees it, the refusal is
logged, and the emulated source is unchanged afterwards.
"""

import duckdb
import pytest

from altitude.core.errors import ReadOnlyViolation
from altitude_connectors.manifest import load_manifest
from altitude_connectors.readonly import ReadOnlyConnection, classify_statement

WRITES = [
    "INSERT INTO dbo.DimCustomer VALUES (3, 'x', 'y', 'z')",
    "insert dbo.DimCustomer (CustomerKey) values (3)",
    "UPDATE dbo.DimCustomer SET Segment = 'x'",
    "  update\tdbo.DimCustomer set Segment='x'",
    "DELETE FROM dbo.DimCustomer",
    "dElEtE dbo.DimCustomer",
    "MERGE INTO dbo.DimCustomer AS t USING stg.Customer_Load AS s ON t.CustomerCode = s.CustomerCode "
    "WHEN MATCHED THEN DELETE",
    "CREATE TABLE dbo.evil (a INT)",
    "CREATE VIEW dbo.v AS SELECT 1 AS a",
    "DROP TABLE dbo.DimCustomer",
    "DROP DATABASE SalesDW",
    "ALTER TABLE dbo.DimCustomer ADD evil INT",
    "ALTER LOGIN sa WITH PASSWORD = 'x'",
    "TRUNCATE TABLE dbo.FactSales",
    "GRANT SELECT ON dbo.DimCustomer TO public",
    "REVOKE SELECT ON dbo.DimCustomer FROM bi_readers",
    "DENY SELECT ON dbo.DimCustomer TO bi_readers",
    "EXEC sp_who",
    "EXEC('DELETE FROM dbo.DimCustomer')",
    "EXECUTE etl.usp_LoadFactSales",
    "CALL etl.usp_LoadFactSales()",
    "SELECT 1; DROP TABLE dbo.DimCustomer",
    "SELECT 1;DELETE FROM dbo.DimCustomer;",
    "SELECT 1 -- harmless\n; DELETE FROM dbo.DimCustomer",
    "SELECT 1 /* ; */ ; DELETE FROM dbo.DimCustomer",
    "/* looks like a comment */ DELETE FROM dbo.DimCustomer",
    "-- SELECT\nDELETE FROM dbo.DimCustomer",
    "SELECT 1 -- comment \n DROP TABLE dbo.DimCustomer",
    "SELECT 1 /*! ; DROP TABLE dbo.DimCustomer */",
    "SELECT 1 /* unterminated comment DROP TABLE x",
    "SELECT 'unterminated; DROP TABLE dbo.DimCustomer",
    "SELECT 'a'; DROP TABLE dbo.DimCustomer; --'",
    "SELECT 1\nGO\nDROP TABLE dbo.DimCustomer",
    "SELECT * INTO dbo.stolen FROM sys.objects",
    "SELECT name FROM sys.objects WITH (UPDLOCK) OUTPUT deleted.name",
    "WITH d AS (DELETE FROM dbo.DimCustomer RETURNING *) SELECT * FROM d",
    "SELECT * FROM OPENQUERY(LINKED, 'DELETE FROM x')",
    "SELECT * FROM OPENROWSET('SQLNCLI', 'srv', 'DELETE FROM x')",
    "SELECT xp_cmdshell('dir')",
    "DECLARE @x INT; SELECT 1",
    "SET ROWCOUNT 0",
    "BEGIN TRAN",
    "COMMIT",
    "USE master",
    "WAITFOR DELAY '00:00:05'",
    "BACKUP DATABASE SalesDW TO DISK = 'c:\\x.bak'",
    "DBCC CHECKDB",
    "KILL 55",
    "EXPLAIN ANALYZE DELETE FROM dbo.DimCustomer",
    "",
    "   ",
    "\x00SELECT 1",
]

TERADATA_WRITES = ["INS INTO EDW.CUSTOMER VALUES (1, 'x', 'y')", "DEL FROM EDW.CUSTOMER ALL",
                   "UPD EDW.CUSTOMER SET SEGMENT = 'x'", "REPLACE VIEW EDW_V.V AS SELECT 1 AS a",
                   "CT EDW.X (A INT)", "COLLECT STATISTICS ON EDW.CUSTOMER COLUMN (CUSTOMER_ID)",
                   "LOCKING ROW FOR WRITE SELECT * FROM DBC.TablesV", "DATABASE EDW"]
ORACLE_WRITES = ["SELECT * FROM DBA_OBJECTS FOR UPDATE", "SELECT ORDERS_SEQ.NEXTVAL FROM DUAL",
                 "BEGIN DELETE FROM SALES.ORDERS; END;", "SELECT DBMS_SQL.OPEN_CURSOR FROM DUAL",
                 "CREATE OR REPLACE VIEW SALES.V AS SELECT 1 AS A FROM DUAL"]

READS = [
    ("SELECT 1", "tsql"),
    ("select name, type from sys.objects where is_ms_shipped = 0", "tsql"),
    ("WITH x AS (SELECT 1 AS a) SELECT a FROM x", "tsql"),
    ("SELECT REPLACE(name, 'a', 'b') AS n FROM sys.objects", "tsql"),
    ("SELECT 'DROP TABLE x; DELETE FROM y' AS s", "tsql"),
    ("SELECT 1 -- DROP TABLE x", "tsql"),
    ("SELECT 1 /* DELETE FROM x; */", "tsql"),
    ("SELECT name FROM sys.objects;", "tsql"),
    ("(SELECT 1)", "tsql"),
    ("SELECT a FROM t UNION ALL SELECT b FROM u", "tsql"),
    ("EXPLAIN SELECT * FROM t", "duckdb"),
    ("DESCRIBE t", "duckdb"),
    ("SHOW TABLES", "duckdb"),
    ("SEL * FROM DBC.TablesV", "teradata"),
    ("SELECT OWNER, OBJECT_NAME FROM DBA_OBJECTS WHERE OBJECT_TYPE = 'TABLE'", "oracle"),
]


class SpyConnection:
    """A DB-API connection that records every statement it is asked to run."""

    def __init__(self, real):
        self.real = real
        self.executed = []

    def cursor(self):
        spy = self

        class _Cur:
            def __init__(self):
                self._c = spy.real.cursor()
                self.description = None

            def execute(self, sql, params=None):
                spy.executed.append(sql)
                self._c.execute(sql, params or [])
                self.description = self._c.description

            def fetchall(self):
                return self._c.fetchall()

        return _Cur()


@pytest.mark.parametrize("sql", WRITES)
def test_kill_test_tsql_writes_refused(sql):
    with pytest.raises(ReadOnlyViolation):
        classify_statement(sql, "sqlserver")


@pytest.mark.parametrize("sql", TERADATA_WRITES)
def test_kill_test_teradata_writes_refused(sql):
    with pytest.raises(ReadOnlyViolation):
        classify_statement(sql, "teradata")


@pytest.mark.parametrize("sql", ORACLE_WRITES)
def test_kill_test_oracle_writes_refused(sql):
    with pytest.raises(ReadOnlyViolation):
        classify_statement(sql, "oracle")


@pytest.mark.parametrize("sql,dialect", READS)
def test_read_statements_allowed(sql, dialect):
    v = classify_statement(sql, dialect)
    assert v.kind in {"select", "explain", "describe", "show"}


def test_kill_test_against_live_source_nothing_reaches_driver_and_source_unchanged(mssql):
    raw = mssql.build()
    before = {t: raw.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
              for t in ("sys.objects", "dbo.DimCustomer", "msdb.dbo.sysjobs")}
    spy = SpyConnection(raw)
    conn = ReadOnlyConnection(spy, "sqlserver", execute_dialect="duckdb")
    for sql in WRITES:
        with pytest.raises(ReadOnlyViolation):
            conn.execute(sql)
    assert spy.executed == []  # no write ever reached the driver
    assert len(conn.log.refused()) == len(WRITES)  # every refusal is logged
    assert all(e.reason for e in conn.log.refused())
    after = {t: raw.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in before}
    assert after == before
    # the same connection still reads
    assert conn.query("SELECT count(*) AS n FROM sys.objects")[0]["n"] == before["sys.objects"]
    assert len(spy.executed) == 1 and conn.log.entries[-1].verdict == "allowed"


def test_wrapper_exposes_no_write_path(mssql):
    conn = ReadOnlyConnection(mssql.build(), "sqlserver", execute_dialect="duckdb")
    cur = conn.cursor()
    with pytest.raises(ReadOnlyViolation):
        cur.executemany("INSERT INTO t VALUES (?)", [(1,)])
    with pytest.raises(ReadOnlyViolation):
        cur.callproc("etl.usp_LoadFactSales")
    for attr in ("raw", "connection", "_raw", "con", "execute_raw", "autocommit"):
        with pytest.raises(AttributeError):
            getattr(conn, attr)
    conn.commit()  # no-op: nothing can have been written
    conn.close()
    with pytest.raises(ReadOnlyViolation):
        conn.execute("SELECT 1")
    with pytest.raises(TypeError):
        ReadOnlyConnection(conn, "sqlserver")


def test_scope_blocks_user_tables_so_row_data_cannot_be_read(mssql):
    scope = load_manifest("sqlserver").scope
    conn = ReadOnlyConnection(mssql.build(), "sqlserver", scope=scope, execute_dialect="duckdb")
    for sql in ["SELECT * FROM dbo.DimCustomer", "SELECT CustomerName FROM SalesDW.dbo.DimCustomer",
                "SELECT o.name FROM sys.objects o JOIN dbo.FactSales f ON 1 = 1",
                "SELECT name FROM sys.objects WHERE name IN (SELECT CustomerName FROM dbo.DimCustomer)",
                "WITH c AS (SELECT * FROM dbo.CustomerAddress) SELECT * FROM c",
                "SHOW TABLES"]:
        with pytest.raises(ReadOnlyViolation):
            conn.execute(sql)
    assert conn.query("SELECT name FROM sys.objects WHERE is_ms_shipped = 0")
    # a CTE that shadows a user-table name is not a table read
    assert conn.query("WITH dimcustomer AS (SELECT 1 AS a) SELECT a FROM dimcustomer") == [{"a": 1}]


def test_statement_log_records_every_statement(mssql_agent):
    log = mssql_agent.statement_log
    assert len(log) == len(log.allowed()) > 10
    assert not log.refused()
    assert all(e.objects or "SERVERPROPERTY" in e.sql for e in log.entries)
    assert all(e.rows is not None for e in log.entries)


def test_duckdb_read_only_session_rejects_writes_too(tmp_path):
    """Defence in depth for the CLI path: catalogs are opened read-only as well."""
    p = tmp_path / "cat.duckdb"
    duckdb.connect(str(p)).execute("CREATE TABLE t (a INT)").close()
    con = duckdb.connect(str(p), read_only=True)
    with pytest.raises(duckdb.Error):
        con.execute("INSERT INTO t VALUES (1)")
