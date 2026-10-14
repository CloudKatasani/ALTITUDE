"""Synthetic drift cases: two DuckDB databases emulating a legacy source and its Snowflake target.

Each case seeds one known semantic drift into otherwise identical data, so tests (and
``altitude validation demo``) can prove the engine detects it and the triage agent clusters it
to the right Pattern Library issue. All data is generated deterministically in SQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import duckdb

from .endpoint import Endpoint
from .suite import QuerySpec, TableSpec

ORDERS = """
CREATE TABLE orders AS
SELECT i AS order_id, 100 + i % 7 AS customer_id, CAST(i * 3.25 AS DECIMAL(12, 2)) AS amount,
       DATE '2026-09-01' + CAST(i % 10 AS INTEGER) AS order_date
FROM range(1, 41) t(i);
"""

CUSTOMER = """
CREATE TABLE customer AS
SELECT i AS customer_id,
       ['Smith', 'Jones', 'Brown', 'Taylor', 'Wilson', 'Evans'][(i % 6) + 1] AS last_name,
       CASE WHEN i % 4 = 0 THEN NULL ELSE ['A', 'B', 'C'][(i % 3) + 1] END AS middle_name,
       ['Active', 'Closed', 'Pending'][(i % 3) + 1] AS status,
       CAST('C' || i AS VARCHAR) AS code
FROM range(1, 31) t(i);
"""

EVENTS = """
CREATE TABLE events AS
SELECT i AS event_id,
       TIMESTAMP '2026-10-01 08:00:00' + to_milliseconds(i * 60000 + 997) AS event_ts
FROM range(1, 21) t(i);
"""

ORDERS_TS = """
CREATE TABLE orders AS
SELECT i AS order_id, TIMESTAMP '2026-09-01 00:00:00' + to_hours(i * 5) AS order_ts
FROM range(1, 25) t(i);
"""


@dataclass
class DriftCase:
    name: str
    source: Endpoint
    target: Endpoint
    spec: TableSpec
    expected_issue: str | None
    expected_signature: str | None
    description: str

    def close(self) -> None:
        self.source.con.close()
        self.target.con.close()


def _pair(source_sql: str, target_sql: str) -> tuple[Endpoint, Endpoint]:
    s, t = duckdb.connect(), duckdb.connect()
    s.execute(source_sql)
    t.execute(target_sql)
    return Endpoint(s, "duckdb", "source"), Endpoint(t, "duckdb", "target")


def _customer_spec(case: str, dialect: str, **kw) -> TableSpec:
    return TableSpec(object_id=f"CRM.CUSTOMER[{case}]", source_table="customer", tier="tier1", key_columns=["customer_id"],
                     source_dialect=dialect, data_owner="owner.crm@client", **kw)


def td01() -> DriftCase:
    s, t = _pair(ORDERS, ORDERS + "INSERT INTO orders SELECT * FROM orders WHERE order_id IN (5, 6, 7);")
    spec = TableSpec(object_id="SALES.ORDERS[TD-01]", source_table="orders", tier="tier1", key_columns=["order_id"],
                     partition_column="order_date", source_dialect="teradata", data_owner="owner.sales@client")
    return DriftCase("TD-01", s, t, spec, "TD-01", "duplicate_rows",
                     "Teradata SET table discarded re-delivered duplicates; the Snowflake table kept 3 of them")


def td02() -> DriftCase:
    s, t = _pair(CUSTOMER, CUSTOMER + "UPDATE customer SET last_name = upper(last_name) "
                                      "WHERE customer_id IN (3, 8, 13, 19);")
    return DriftCase("TD-02", s, t, _customer_spec("TD-02", "teradata"), "TD-02", "case_only",
                     "NOT CASESPECIFIC upsert matched case variants in Teradata; Snowflake stored the other casing")


def td03() -> DriftCase:
    s, t = _pair(CUSTOMER, CUSTOMER + "UPDATE customer SET code = code || '   ' WHERE customer_id % 6 = 0;")
    return DriftCase("TD-03", s, t, _customer_spec("TD-03", "teradata"), "TD-03", "trailing_space",
                     "CHAR(n) codes landed with pad characters")


def or01() -> DriftCase:
    s, t = _pair(CUSTOMER, CUSTOMER + "UPDATE customer SET middle_name = '' WHERE middle_name IS NULL;")
    return DriftCase("OR-01", s, t, _customer_spec("OR-01", "oracle"), "OR-01", "empty_vs_null",
                     "Oracle NULL (stored for '') landed as empty strings")


def or02() -> DriftCase:
    target = ORDERS.replace("CAST(i * 3.25 AS DECIMAL(12, 2))", "CAST(i * 3.25 AS DECIMAL(12, 0))")
    s, t = _pair(ORDERS, target)
    spec = TableSpec(object_id="SALES.ORDERS[OR-02]", source_table="orders", tier="tier1", key_columns=["order_id"],
                     source_dialect="oracle", data_owner="owner.sales@client")
    return DriftCase("OR-02", s, t, spec, "OR-02", "scale_truncation", "Unscaled NUMBER became NUMBER(38,0)")


def or03() -> DriftCase:
    s, t = _pair(ORDERS_TS, ORDERS_TS.replace("AS order_ts", "AS order_ts_raw") +
                 "ALTER TABLE orders ADD COLUMN order_ts DATE; UPDATE orders SET order_ts = CAST(order_ts_raw AS DATE);"
                 "ALTER TABLE orders DROP COLUMN order_ts_raw;")
    spec = TableSpec(object_id="SALES.ORDERS_TS[OR-03]", source_table="orders", tier="tier1", key_columns=["order_id"],
                     source_dialect="oracle", data_owner="owner.sales@client")
    return DriftCase("OR-03", s, t, spec, "OR-03", "time_component_lost", "Oracle DATE mapped to Snowflake DATE")


def ms01() -> DriftCase:
    s, t = _pair(CUSTOMER, CUSTOMER + "UPDATE customer SET status = upper(status) WHERE customer_id % 5 = 0;")
    q = QuerySpec(
        id="KPI-CUSTOMERS-BY-STATUS",
        description="Customers per status (report query)",
        # SQL Server groups case-insensitively; the emulation groups on lower(status)
        source_sql="SELECT max(status) AS status, count(*) AS n FROM customer GROUP BY lower(status) ORDER BY 1",
        target_sql="SELECT status, count(*) AS n FROM customer GROUP BY status ORDER BY 1",
    )
    return DriftCase("MS-01", s, t, _customer_spec("MS-01", "sqlserver", queries=[q]), "MS-01", "case_only",
                     "Case-insensitive collation hid casing differences that Snowflake keeps")


def ms02() -> DriftCase:
    s, t = _pair(EVENTS, EVENTS + "UPDATE events SET event_ts = event_ts + to_milliseconds(2) WHERE event_id % 2 = 0;")
    spec = TableSpec(object_id="WEB.EVENTS[MS-02]", source_table="events", tier="tier1", key_columns=["event_id"],
                     source_dialect="sqlserver", data_owner="owner.web@client")
    return DriftCase("MS-02", s, t, spec, "MS-02", "timestamp_precision", "DATETIME 1/300 s rounding")


def clean() -> DriftCase:
    s, t = _pair(ORDERS, ORDERS)
    spec = TableSpec(object_id="SALES.ORDERS", source_table="orders", tier="tier1", key_columns=["order_id"],
                     partition_column="order_date", source_dialect="teradata", data_owner="owner.sales@client",
                     queries=[QuerySpec("KPI-REVENUE", "SELECT sum(amount) FROM orders")],
                     perf=[{"query_id": "KPI-REVENUE", "baseline_p50_ms": 800, "baseline_p95_ms": 2000,
                            "target_p50_ms": 600, "target_p95_ms": 1500, "sla_p95_ms": 3000}])
    return DriftCase("clean", s, t, spec, None, None, "Identical source and target")


CASES: dict[str, Callable[[], DriftCase]] = {
    "TD-01": td01, "TD-02": td02, "TD-03": td03, "OR-01": or01, "OR-02": or02, "OR-03": or03,
    "MS-01": ms01, "MS-02": ms02, "clean": clean,
}
