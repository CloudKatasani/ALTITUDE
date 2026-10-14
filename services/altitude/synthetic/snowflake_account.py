# lint: thresholds-exempt (synthetic fixture generator: literals describe the fake estate, not decisions)
"""Synthetic Snowflake account with seeded issues and ground truth.

``generate(AccountSpec(...))`` returns every harvest-contract table as rows plus:

- ``seeded``   — list of ``{"check_id", "object"}`` pairs the diagnostics engine
  must find (one per seeded issue / affected object);
- ``controls`` — look-alike objects that must *not* be flagged for that check.

Profiles: ``seeded`` (all issues present unless listed in ``disabled_issues``)
and ``clean`` (a well-run account: no seeded issues).

Every row for a given day depends only on ``(seed, account_name, day)``, so two
harvests over overlapping windows produce identical rows for the shared days —
which the observability archive relies on for de-duplication.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from .schema import HARVEST_SCHEMA

SIZE_CREDITS = {"XSMALL": 1, "SMALL": 2, "MEDIUM": 4, "LARGE": 8, "XLARGE": 16, "XXLARGE": 32}
GB = 1024 ** 3
TB = 1024 ** 4

ALL_ISSUES = [
    "DX-COST-01", "DX-COST-02", "DX-COST-03", "DX-COST-04", "DX-COST-05", "DX-COST-06", "DX-COST-07",
    "DX-COST-08", "DX-PERF-01", "DX-PERF-02", "DX-PERF-03", "DX-PERF-04", "DX-REL-01", "DX-REL-02",
    "DX-REL-03", "DX-REL-04", "DX-SEC-01", "DX-SEC-02", "DX-SEC-03", "DX-SEC-04", "DX-SEC-05",
    "DX-GOV-01", "DX-GOV-02", "DX-GOV-03", "DX-OPS-01", "DX-OPS-02", "DX-ARCH-01", "DX-BI-01",
    "DX-BI-02", "DX-BI-03", "DX-AI-01", "DX-AI-02", "DX-AI-03",
]


@dataclass
class AccountSpec:
    account_name: str = "ACME_PROD"
    organization: str = "ACME"
    region: str = "AWS_US_EAST_1"
    edition: str = "ENTERPRISE"
    end_date: date = date(2026, 9, 30)
    days: int = 90
    seed: int = 7
    profile: str = "seeded"  # seeded | clean
    disabled_issues: set[str] = field(default_factory=set)
    anomalies: list[dict] = field(default_factory=list)  # {"date": date, "warehouse": str, "factor": float}
    price_per_credit: float = 3.0
    storage_price_per_tb_month: float = 23.0

    @property
    def start_date(self) -> date:
        return self.end_date - timedelta(days=self.days - 1)

    def seeded(self, check_id: str) -> bool:
        return self.profile == "seeded" and check_id not in self.disabled_issues


@dataclass
class SyntheticAccount:
    spec: AccountSpec
    tables: dict[str, list[dict]]
    seeded: list[dict]
    controls: list[dict]

    def ground_truth(self) -> dict:
        return {"seeded": self.seeded, "controls": self.controls}


# --------------------------------------------------------------------------- helpers


def _rng(spec: AccountSpec, *keys: Any) -> random.Random:
    h = hashlib.sha256(json.dumps([spec.seed, spec.account_name, *map(str, keys)]).encode()).hexdigest()
    return random.Random(int(h[:16], 16))


def _days(spec: AccountSpec) -> Iterable[date]:
    for i in range(spec.days):
        yield spec.start_date + timedelta(days=i)


def _ts(d: date, hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day) + timedelta(hours=hour, minutes=minute, seconds=second)


def _qid(spec: AccountSpec, d: date, wh: str, n: int) -> str:
    return "01" + hashlib.md5(f"{spec.account_name}|{d}|{wh}|{n}".encode()).hexdigest()[:18]


def _fq(name: str) -> tuple[str, str, str]:
    db, sch, obj = name.split(".")
    return db, sch, obj


# --------------------------------------------------------------------------- estate definition


def _warehouses(spec: AccountSpec) -> list[dict]:
    s = spec.seeded
    return [
        dict(name="WH_BI_PROD", size="MEDIUM", cls="bi", hours=range(7, 19), qph=10, active=0.22, bursts=4,
             auto_suspend=900 if s("DX-COST-01") else 60, max_cluster=1 if s("DX-PERF-01") else 3,
             cost_center="FINANCE_BI", monitor=not s("DX-OPS-02")),
        dict(name="WH_BI_ADHOC", size="LARGE" if s("DX-COST-02") else "SMALL", cls="adhoc", hours=range(8, 18),
             qph=4, active=0.05, bursts=3, auto_suspend=1800 if s("DX-COST-01") else 60, max_cluster=1,
             cost_center=None if s("DX-COST-07") else "ANALYTICS", monitor=not s("DX-OPS-02")),
        dict(name="WH_ELT_PROD", size="LARGE", cls="elt", hours=range(1, 5), qph=8, active=0.75, bursts=1,
             auto_suspend=60, max_cluster=1, cost_center="DATA_PLATFORM", monitor=True),
        dict(name="WH_DS", size="XLARGE", cls="data_science", hours=range(9, 17), qph=2, active=0.5, bursts=1,
             auto_suspend=120, max_cluster=1, cost_center="DATA_SCIENCE", monitor=not s("DX-OPS-02")),
        dict(name="WH_DEV", size="SMALL", cls="dev", hours=range(9, 17), qph=3, active=0.08, bursts=3,
             auto_suspend=3600 if s("DX-COST-01") else 60, max_cluster=1,
             cost_center=None if s("DX-COST-07") else "ENGINEERING", monitor=not s("DX-OPS-02")),
        dict(name="WH_AGENTS", size="XSMALL", cls="agents", hours=range(8, 18), qph=2, active=0.2, bursts=2,
             auto_suspend=60, max_cluster=1, cost_center="AI_PLATFORM", monitor=not s("DX-OPS-02")),
    ]


def _tables(spec: AccountSpec) -> list[dict]:
    s = spec.seeded
    end = _ts(spec.end_date, 0)
    old = end - timedelta(days=400)
    t = [
        dict(fq="EDW.SALES.FCT_ORDERS", rows=2_100_000_000, bytes=int(1.2 * TB), cluster="(ORDER_DATE)",
             comment="Order facts, one row per order line", owner_tag="sales-data@acme", retention=1,
             transient=False, cols=["ORDER_ID", "ORDER_DATE", "CUSTOMER_ID", "REGION", "NET_AMOUNT", "GROSS_AMOUNT",
                                    "ORDER_TS", "STATUS"], col_comment_pct=1.0, sig="ORDERS_V1"),
        dict(fq="EDW.SALES.DIM_CUSTOMER", rows=5_000_000, bytes=int(4 * GB), cluster=None,
             comment="Customer dimension (SCD2)", owner_tag="crm-data@acme", retention=1, transient=False,
             cols=["CUSTOMER_ID", "NAME", "EMAIL", "PHONE", "SSN", "SEGMENT", "VALID_FROM", "VALID_TO",
                   "IS_CURRENT", "REGION"], col_comment_pct=0.9, sig="CUST_V1"),
        dict(fq="EDW.FINANCE.FCT_REVENUE", rows=300_000_000, bytes=int(180 * GB), cluster=None,
             comment=None if s("DX-GOV-01") else "Recognised revenue by day and product",
             owner_tag=None if s("DX-GOV-01") else "finance-data@acme", retention=1, transient=False,
             cols=["REVENUE_DATE", "PRODUCT_ID", "REGION", "GROSS_AMOUNT", "NET_AMOUNT", "TAX_AMOUNT",
                   "CURRENCY", "LEDGER_ACCOUNT", "LOAD_TS", "SOURCE_SYSTEM"],
             col_comment_pct=0.1 if s("DX-AI-03") else 1.0, sig="REV_V1"),
        dict(fq="EDW.SALES.FCT_EVENTS", rows=8_000_000_000, bytes=int(4 * TB),
             cluster=None if s("DX-PERF-03") else "(EVENT_DATE)", comment="Web and app events",
             owner_tag="digital@acme", retention=1, transient=False,
             cols=["EVENT_ID", "EVENT_DATE", "EVENT_TS", "CUSTOMER_ID", "EVENT_TYPE", "PAYLOAD"],
             col_comment_pct=0.5, sig="EVT_V1"),
        dict(fq="EDW.RAW.EVENTS_LOG", rows=3_000_000_000, bytes=int(900 * GB), cluster="(LOAD_TS)",
             comment="Raw event log (bronze)", owner_tag="digital@acme", retention=1, transient=False,
             cols=["LOAD_TS", "RAW"], col_comment_pct=0.0, sig="RAWLOG_V1"),
        dict(fq="EDW.STAGING.STG_ORDERS", rows=40_000_000, bytes=int(30 * GB), cluster=None,
             comment="Staging for orders", owner_tag="sales-data@acme",
             retention=30 if s("DX-COST-06") else 0, transient=not s("DX-COST-06"),
             cols=["ORDER_ID", "PAYLOAD", "LOAD_TS"], col_comment_pct=0.0, sig="STG_ORD_V1"),
        dict(fq="EDW.SALES.DIM_REGION", rows=50, bytes=int(1 * 1024 ** 2), cluster=None, comment="Regions",
             owner_tag="sales-data@acme", retention=1, transient=False, cols=["REGION", "NAME"],
             col_comment_pct=1.0, sig="REGION_V1"),
        dict(fq="EDW.SALES.DIM_PRODUCT", rows=20_000, bytes=int(50 * 1024 ** 2), cluster=None,
             comment="Products", owner_tag="sales-data@acme", retention=1, transient=False,
             cols=["PRODUCT_ID", "NAME", "CATEGORY"], col_comment_pct=1.0, sig="PROD_V1"),
    ]
    if s("DX-COST-06"):
        t.append(dict(fq="EDW.SALES.FCT_ORDERS_CLONE_2025", rows=1_900_000_000, bytes=int(1.1 * TB), cluster=None,
                      comment="clone for 2025 audit", owner_tag=None, retention=1, transient=False,
                      cols=["ORDER_ID", "ORDER_DATE", "CUSTOMER_ID", "REGION", "NET_AMOUNT", "GROSS_AMOUNT",
                            "ORDER_TS", "STATUS"], col_comment_pct=0.0, sig="ORDERS_V0", clone_of="EDW.SALES.FCT_ORDERS",
                      created=old, last_altered=old, retained_for_clone=int(0.9 * TB)))
    if s("DX-ARCH-01"):
        t.append(dict(fq="EDW.SALES.ORDERS_COPY", rows=2_100_000_000, bytes=int(1.19 * TB), cluster=None,
                      comment=None, owner_tag=None, retention=1, transient=False,
                      cols=["ORDER_ID", "ORDER_DATE", "CUSTOMER_ID", "REGION", "NET_AMOUNT", "GROSS_AMOUNT",
                            "ORDER_TS", "STATUS"], col_comment_pct=0.0, sig="ORDERS_V1"))
    if s("DX-GOV-03"):
        for i, nm in enumerate(["CAMPAIGN_2019", "CAMPAIGN_2020", "MKTG_SEGMENTS_OLD", "TMP_JOIN_BACKUP",
                                "EXPORT_Q3_2023", "ORDERS_BKP_2022"]):
            t.append(dict(fq=f"EDW.LEGACY.{nm}", rows=10_000_000 * (i + 1), bytes=int((20 + 15 * i) * GB),
                          cluster=None, comment=None, owner_tag=None, retention=1, transient=False,
                          cols=["ID", "PAYLOAD"], col_comment_pct=0.0, sig=f"LEG_{i}",
                          created=old - timedelta(days=200), last_altered=old - timedelta(days=30 * i)))
    return t


TIER1 = ["EDW.SALES.FCT_ORDERS", "EDW.SALES.DIM_CUSTOMER", "EDW.FINANCE.FCT_REVENUE"]


def _users(spec: AccountSpec) -> list[dict]:
    s = spec.seeded
    end = _ts(spec.end_date, 12)
    created = end - timedelta(days=700)
    users = [
        dict(name="ADMIN_1", type="PERSON", password=False, mfa=True, rsa=False, sso=True, admin=True),
        dict(name="ADMIN_2", type="PERSON", password=False, mfa=True, rsa=False, sso=True, admin=True),
        dict(name="JSMITH", type="PERSON", password=True, mfa=not s("DX-SEC-01"), rsa=False, sso=False,
             admin=s("DX-SEC-02")),
        dict(name="TEMP_CONTRACTOR", type="PERSON", password=True, mfa=not s("DX-SEC-01"), rsa=False, sso=False,
             admin=s("DX-SEC-02")),
        dict(name="OPS_LEAD", type="PERSON", password=False, mfa=True, rsa=False, sso=True, admin=s("DX-SEC-02")),
        dict(name="SVC_FIVETRAN", type="LEGACY_SERVICE" if s("DX-SEC-01") else "SERVICE",
             password=s("DX-SEC-01"), mfa=False, rsa=not s("DX-SEC-01"), sso=False, admin=False),
        dict(name="SVC_DBT", type="SERVICE", password=False, mfa=False, rsa=True, sso=False, admin=False),
        dict(name="SVC_TERRAFORM", type="SERVICE", password=False, mfa=False, rsa=True, sso=False, admin=False),
        dict(name="SVC_AGENT", type="SERVICE", password=False, mfa=False, rsa=True, sso=False, admin=False),
        dict(name="SVC_POWERBI", type="SERVICE", password=False, mfa=False, rsa=True, sso=False, admin=False),
    ]
    for i in range(1, 9):
        users.append(dict(name=f"ANALYST_{i:02d}", type="PERSON", password=False, mfa=True, rsa=False, sso=True,
                          admin=False))
    if s("DX-SEC-03"):
        users.append(dict(name="OLD_ANALYST", type="PERSON", password=False, mfa=True, rsa=False, sso=True,
                          admin=False, dormant_days=240))
    for u in users:
        u["created"] = created
        u["last_login"] = end - timedelta(days=u.get("dormant_days", 0))
    return users


ANALYSTS = [f"ANALYST_{i:02d}" for i in range(1, 9)]


def _signatures(spec: AccountSpec) -> dict[str, list[dict]]:
    """Query signatures per warehouse. Each signature drives QUERY_HISTORY and ACCESS_HISTORY rows."""
    s = spec.seeded
    sales_dash_text = (
        "SELECT REGION, SUM(NET_AMOUNT) FROM EDW.SALES.FCT_ORDERS WHERE ORDER_TS >= DATEADD(day, -30, "
        + ("CURRENT_TIMESTAMP()" if s("DX-COST-03") else "CURRENT_DATE()") + ") GROUP BY REGION"
    )
    return {
        "WH_BI_PROD": [
            dict(hash="qh_bi_sales_dash", text=sales_dash_text, type="SELECT", weight=6, users=["SVC_POWERBI"],
                 role="FR_BI", exec_ms=(2500, 6000), scan=(30 * GB, 60 * GB), parts=(400, 120_000), rows=(12, 12),
                 reads=["EDW.SALES.FCT_ORDERS"], tag="powerbi", app="PowerBI", identical=True,
                 cacheable=not s("DX-COST-03")),
            dict(hash="qh_bi_finance_wide", type="SELECT", weight=2, users=["SVC_POWERBI"], role="FR_BI",
                 text=("SELECT * FROM EDW.FINANCE.FCT_REVENUE r JOIN EDW.SALES.DIM_CUSTOMER c ON r.REGION = c.REGION "
                       "WHERE r.REVENUE_DATE >= ?") if s("DX-PERF-04") else
                 ("SELECT r.REVENUE_DATE, r.REGION, SUM(r.NET_AMOUNT) FROM EDW.FINANCE.FCT_REVENUE r "
                  "WHERE r.REVENUE_DATE >= ? GROUP BY 1, 2"),
                 exec_ms=(40_000, 90_000) if s("DX-PERF-04") else (3000, 6000),
                 scan=(150 * GB, 220 * GB) if s("DX-PERF-04") else (8 * GB, 12 * GB), parts=(9000, 12_000),
                 rows=(400_000_000, 900_000_000) if s("DX-PERF-04") else (2000, 4000),
                 reads=["EDW.FINANCE.FCT_REVENUE", "EDW.SALES.DIM_CUSTOMER"] if s("DX-PERF-04") else ["EDW.FINANCE.FCT_REVENUE"],
                 tag="powerbi", app="PowerBI"),
            dict(hash="qh_bi_events", type="SELECT", weight=2, users=["SVC_POWERBI"], role="FR_BI",
                 text="SELECT EVENT_TYPE, COUNT(*) FROM EDW.SALES.FCT_EVENTS WHERE EVENT_DATE = ? GROUP BY 1",
                 exec_ms=(20_000, 45_000) if s("DX-PERF-03") else (1500, 3000),
                 scan=(3 * TB, 3.8 * TB) if s("DX-PERF-03") else (40 * GB, 50 * GB),
                 parts=(116_000, 120_000) if s("DX-PERF-03") else (1300, 1400), part_total=120_000,
                 rows=(20, 20), reads=["EDW.SALES.FCT_EVENTS"], tag="powerbi", app="PowerBI"),
            dict(hash="qh_bi_customer", type="SELECT", weight=2, users=["SVC_POWERBI"], role="FR_BI",
                 text="SELECT SEGMENT, COUNT(*) FROM EDW.SALES.DIM_CUSTOMER WHERE IS_CURRENT GROUP BY 1",
                 exec_ms=(800, 1500), scan=(1 * GB, 2 * GB), parts=(30, 40), rows=(6, 6),
                 reads=["EDW.SALES.DIM_CUSTOMER"], tag="powerbi", app="PowerBI"),
        ],
        "WH_BI_ADHOC": [
            dict(hash="qh_adhoc_lookup", type="SELECT", weight=3, users=ANALYSTS, role="FR_ANALYST",
                 text="SELECT * FROM EDW.SALES.DIM_PRODUCT WHERE CATEGORY = ?", exec_ms=(300, 1800),
                 scan=(10 * 1024 ** 2, 50 * 1024 ** 2), parts=(1, 2), rows=(10, 200), reads=["EDW.SALES.DIM_PRODUCT"],
                 tag=None, app="Snowflake Web App"),
            dict(hash="qh_adhoc_orders", type="SELECT", weight=1, users=ANALYSTS, role="FR_ANALYST",
                 text="SELECT COUNT(*) FROM EDW.SALES.ORDERS_COPY WHERE ORDER_DATE = ?" if s("DX-ARCH-01") else
                 "SELECT COUNT(*) FROM EDW.SALES.FCT_ORDERS WHERE ORDER_DATE = ?",
                 exec_ms=(500, 2500), scan=(200 * 1024 ** 2, 900 * 1024 ** 2), parts=(10, 30), rows=(1, 1),
                 reads=["EDW.SALES.ORDERS_COPY" if s("DX-ARCH-01") else "EDW.SALES.FCT_ORDERS"], tag=None,
                 app="Snowflake Web App"),
        ],
        "WH_ELT_PROD": [
            dict(hash="qh_elt_orders_load", users=["SVC_DBT"], role="FR_ENGINEER", weight=1, daily=True, hour=1,
                 type="CREATE_TABLE_AS_SELECT" if s("DX-COST-04") else "MERGE",
                 text=("CREATE OR REPLACE TABLE EDW.SALES.FCT_ORDERS AS SELECT * FROM EDW.STAGING.STG_ORDERS_HIST"
                       if s("DX-COST-04") else
                       "MERGE INTO EDW.SALES.FCT_ORDERS t USING EDW.STAGING.STG_ORDERS s ON t.ORDER_ID = s.ORDER_ID "
                       "WHEN MATCHED THEN UPDATE SET ... WHEN NOT MATCHED THEN INSERT ..."),
                 exec_ms=(1_800_000, 2_400_000) if s("DX-COST-04") else (120_000, 200_000),
                 scan=(1.1 * TB, 1.3 * TB) if s("DX-COST-04") else (30 * GB, 40 * GB), parts=(70_000, 72_000),
                 rows=(0, 0), written=(1.2 * TB, 1.25 * TB) if s("DX-COST-04") else (25 * GB, 35 * GB),
                 inserted=(2_100_000_000, 2_100_000_000) if s("DX-COST-04") else (35_000_000, 45_000_000),
                 reads=["EDW.STAGING.STG_ORDERS"], writes=["EDW.SALES.FCT_ORDERS"], tag="dbt", app="dbt"),
            dict(hash="qh_elt_region_reload", users=["SVC_DBT"], role="FR_ENGINEER", weight=1, daily=True, hour=1,
                 type="CREATE_TABLE_AS_SELECT",
                 text="CREATE OR REPLACE TABLE EDW.SALES.DIM_REGION AS SELECT * FROM EDW.STAGING.STG_REGION",
                 exec_ms=(800, 1500), scan=(1024 ** 2, 2 * 1024 ** 2), parts=(1, 1), rows=(0, 0),
                 written=(1024 ** 2, 1024 ** 2), inserted=(50, 50), reads=[], writes=["EDW.SALES.DIM_REGION"],
                 tag="dbt", app="dbt"),
            dict(hash="qh_elt_revenue_agg", users=["SVC_DBT"], role="FR_ENGINEER", weight=1, daily=True, hour=3,
                 type="INSERT",
                 text="INSERT INTO EDW.FINANCE.FCT_REVENUE SELECT ... FROM EDW.SALES.FCT_ORDERS o JOIN "
                      "EDW.SALES.DIM_PRODUCT p ON o.PRODUCT_ID = p.PRODUCT_ID GROUP BY ...",
                 exec_ms=(900_000, 1_300_000) if s("DX-PERF-02") else (150_000, 250_000),
                 scan=(300 * GB, 400 * GB), parts=(20_000, 25_000), rows=(0, 0),
                 spill_local=(400 * GB, 600 * GB) if s("DX-PERF-02") else (0, 0),
                 spill_remote=(150 * GB, 260 * GB) if s("DX-PERF-02") else (0, 0),
                 written=(2 * GB, 3 * GB), inserted=(3_000_000, 4_000_000),
                 reads=["EDW.SALES.FCT_ORDERS", "EDW.SALES.DIM_PRODUCT"], writes=["EDW.FINANCE.FCT_REVENUE"],
                 tag="dbt", app="dbt"),
            dict(hash="qh_elt_customer_merge", users=["SVC_DBT"], role="FR_ENGINEER", weight=1, daily=True, hour=2,
                 type="MERGE", text="MERGE INTO EDW.SALES.DIM_CUSTOMER t USING EDW.STAGING.STG_CUSTOMER s ON ...",
                 exec_ms=(60_000, 90_000), scan=(4 * GB, 6 * GB), parts=(300, 320), rows=(0, 0),
                 written=(500 * 1024 ** 2, 800 * 1024 ** 2), inserted=(20_000, 40_000),
                 reads=[], writes=["EDW.SALES.DIM_CUSTOMER"], tag="dbt", app="dbt"),
            dict(hash="qh_elt_personal_finance", users=["JSMITH" if s("DX-REL-03") else "SVC_DBT"],
                 role="FR_ENGINEER", weight=1, daily=True, hour=4, type="INSERT",
                 text="INSERT INTO EDW.FINANCE.FCT_REVENUE_ADJ SELECT ... FROM EDW.FINANCE.FCT_REVENUE",
                 exec_ms=(30_000, 50_000), scan=(10 * GB, 15 * GB), parts=(800, 900), rows=(0, 0),
                 written=(100 * 1024 ** 2, 200 * 1024 ** 2), inserted=(10_000, 20_000),
                 reads=["EDW.FINANCE.FCT_REVENUE"], writes=[],
                 tag="airflow:nightly_finance_adj" if s("DX-REL-03") else "dbt",
                 app="PythonConnector"),
        ],
        "WH_DS": [
            dict(hash="qh_ds_features", type="SELECT", weight=1, users=["ANALYST_07", "ANALYST_08"],
                 role="FR_ANALYST", text="SELECT CUSTOMER_ID, ... FROM EDW.SALES.FCT_EVENTS e JOIN ... WHERE ...",
                 exec_ms=(600_000, 1_200_000), scan=(1.5 * TB, 2 * TB), parts=(50_000, 60_000), part_total=120_000,
                 rows=(5_000_000, 6_000_000), reads=["EDW.SALES.FCT_EVENTS", "EDW.SALES.DIM_CUSTOMER"], tag="notebook",
                 app="Snowflake Notebooks"),
        ],
        "WH_DEV": [
            dict(hash="qh_dev_explore", type="SELECT", weight=1, users=["ANALYST_01", "ANALYST_02", "JSMITH"],
                 role="FR_ENGINEER", text="SELECT * FROM EDW.SALES.DIM_REGION", exec_ms=(200, 900),
                 scan=(1024 ** 2, 2 * 1024 ** 2), parts=(1, 1), rows=(50, 50), reads=["EDW.SALES.DIM_REGION"],
                 tag=None, app="Snowflake Web App"),
        ],
        "WH_AGENTS": [
            dict(hash="qh_agent_answers", type="SELECT", weight=1, users=["SVC_AGENT"], role="AGENT_ROLE",
                 text="SELECT REGION, SUM(NET_AMOUNT) FROM EDW.SALES.FCT_ORDERS WHERE ORDER_DATE BETWEEN ? AND ? GROUP BY 1",
                 exec_ms=(1500, 4000), scan=(2 * GB, 6 * GB), parts=(40, 120), rows=(6, 6),
                 reads=["EDW.SALES.FCT_ORDERS"], tag="cortex-agent", app="Cortex Agents"),
        ],
    }


# --------------------------------------------------------------------------- generator


def generate(spec: AccountSpec | None = None) -> SyntheticAccount:
    spec = spec or AccountSpec()
    s = spec.seeded
    T: dict[str, list[dict]] = {name: [] for name in HARVEST_SCHEMA}
    seeded: list[dict] = []
    controls: list[dict] = []

    def seed(check: str, *objects: str) -> None:
        if s(check):
            seeded.extend({"check_id": check, "object": o} for o in objects)

    def control(check: str, *objects: str) -> None:
        controls.extend({"check_id": check, "object": o} for o in objects)

    end_ts = _ts(spec.end_date, 23, 59)
    whs = _warehouses(spec)
    sigs = _signatures(spec)
    tables = _tables(spec)
    users = _users(spec)

    # ---------------------------------------------------------------- account & client inputs
    T["ACCOUNT_INFO"].append(dict(ACCOUNT_NAME=spec.account_name, ORGANIZATION_NAME=spec.organization,
                                  REGION=spec.region, EDITION=spec.edition,
                                  ACCOUNT_LOCATOR=f"XY{abs(hash(spec.account_name)) % 100000:05d}",
                                  NETWORK_POLICY=None if s("DX-SEC-04") else "NP_CORPORATE"))

    # ---------------------------------------------------------------- warehouses & monitors
    for i, w in enumerate(whs):
        T["WAREHOUSES"].append(dict(
            WAREHOUSE_NAME=w["name"], WAREHOUSE_SIZE=w["size"], AUTO_SUSPEND=w["auto_suspend"], AUTO_RESUME=True,
            MIN_CLUSTER_COUNT=1, MAX_CLUSTER_COUNT=w["max_cluster"], SCALING_POLICY="STANDARD",
            RESOURCE_MONITOR=f"RM_{w['name']}" if w["monitor"] else None, OWNER="SYSADMIN", COMMENT=None,
            STATEMENT_TIMEOUT_IN_SECONDS=172800 if w["cls"] in ("adhoc", "dev") and s("DX-COST-02") else 3600,
            WORKLOAD_CLASS=w["cls"]))
        if w["monitor"]:
            T["RESOURCE_MONITORS"].append(dict(NAME=f"RM_{w['name']}", CREDIT_QUOTA=2000.0, LEVEL="WAREHOUSE",
                                               WAREHOUSES=w["name"], NOTIFY_AT="75,90", SUSPEND_AT=100))
        if w["cost_center"]:
            T["TAG_REFERENCES"].append(dict(TAG_DATABASE="GOVERNANCE", TAG_SCHEMA="TAGS", TAG_NAME="COST_CENTER",
                                            TAG_VALUE=w["cost_center"], OBJECT_DATABASE=None, OBJECT_SCHEMA=None,
                                            OBJECT_NAME=w["name"], COLUMN_NAME=None, DOMAIN="WAREHOUSE"))
    if not s("DX-OPS-02"):
        T["RESOURCE_MONITORS"].append(dict(NAME="RM_ACCOUNT", CREDIT_QUOTA=20000.0, LEVEL="ACCOUNT", WAREHOUSES=None,
                                           NOTIFY_AT="80,95", SUSPEND_AT=None))
    seed("DX-COST-01", "WH_BI_PROD", "WH_BI_ADHOC", "WH_DEV")
    control("DX-COST-01", "WH_ELT_PROD", "WH_DS", "WH_AGENTS")
    seed("DX-COST-02", "WH_BI_ADHOC")
    control("DX-COST-02", "WH_ELT_PROD", "WH_DS")
    seed("DX-COST-07", "WH_BI_ADHOC", "WH_DEV")
    control("DX-COST-07", "WH_BI_PROD", "WH_ELT_PROD")
    seed("DX-PERF-01", "WH_BI_PROD")
    control("DX-PERF-01", "WH_ELT_PROD", "WH_BI_ADHOC")
    seed("DX-OPS-02", "ACCOUNT")

    # ---------------------------------------------------------------- daily activity
    anomalies = {(a["date"], a["warehouse"]): float(a["factor"]) for a in spec.anomalies}
    daily_wh_credits: dict[date, float] = {}
    daily_cloud: dict[date, float] = {}
    access_last: dict[str, datetime] = {}
    for d in _days(spec):
        weekday = d.weekday() < 5
        for wi, w in enumerate(whs):
            rng = _rng(spec, "wh", d, w["name"])
            cph = SIZE_CREDITS[w["size"]]
            factor = anomalies.get((d, w["name"]), 1.0)
            hours = list(w["hours"]) if (weekday or w["cls"] in ("elt",)) else []
            qn = 0
            for h in range(24):
                start = _ts(d, h)
                active = 0.0
                queued = 0.0
                if h in hours:
                    active = min(1.0, w["active"] * rng.uniform(0.85, 1.15) * factor)
                    if w["name"] == "WH_BI_PROD" and h in (8, 9, 10):
                        queued = rng.uniform(0.7, 1.2) if s("DX-PERF-01") else 0.0
                if active == 0.0:
                    continue
                clusters = 1
                if w["name"] == "WH_BI_PROD" and h in (8, 9, 10) and not s("DX-PERF-01"):
                    clusters = 2
                tail = w["bursts"] * w["auto_suspend"] / 3600.0
                billed = min(1.0, active + tail)
                compute = round(cph * billed * clusters, 6)
                attributed_total = cph * active * clusters
                cloud = round(compute * rng.uniform(0.03, 0.08), 6)
                T["WAREHOUSE_METERING_HISTORY"].append(dict(
                    START_TIME=start, END_TIME=start + timedelta(hours=1), WAREHOUSE_ID=wi + 1,
                    WAREHOUSE_NAME=w["name"], CREDITS_USED=round(compute + cloud, 6),
                    CREDITS_USED_COMPUTE=compute, CREDITS_USED_CLOUD_SERVICES=cloud))
                T["WAREHOUSE_LOAD_HISTORY"].append(dict(
                    START_TIME=start, END_TIME=start + timedelta(hours=1), WAREHOUSE_NAME=w["name"],
                    AVG_RUNNING=round(active * clusters * rng.uniform(1.0, 2.5), 4), AVG_QUEUED_LOAD=round(queued, 4),
                    AVG_QUEUED_PROVISIONING=0.0, AVG_BLOCKED=0.0))
                daily_wh_credits[d] = daily_wh_credits.get(d, 0.0) + compute + cloud
                daily_cloud[d] = daily_cloud.get(d, 0.0) + cloud

                # queries for this hour
                hour_queries = []
                for sig in sigs[w["name"]]:
                    if sig.get("daily"):
                        if h == sig["hour"]:
                            hour_queries.append(sig)
                        continue
                    n = max(1, round(w["qph"] * sig["weight"] / sum(x["weight"] for x in sigs[w["name"]] if not x.get("daily"))))
                    hour_queries.extend([sig] * n)
                if not hour_queries:
                    continue
                recs = []
                for sig in hour_queries:
                    qn += 1
                    qid = _qid(spec, d, w["name"], qn)
                    minute = rng.randint(0, 59)
                    st = start + timedelta(minutes=minute, seconds=rng.randint(0, 59))
                    cached = sig.get("identical") and sig.get("cacheable") and rng.random() < 0.85
                    ex = 5 if cached else int(rng.uniform(*sig["exec_ms"]) * factor)
                    qo = int(rng.uniform(15_000, 40_000)) if queued > 0.5 else 0
                    scan = 0 if cached else int(rng.uniform(*sig["scan"]))
                    ptotal = sig.get("part_total", int(sig["parts"][1] * 1.0) if sig["parts"][1] > 100 else sig["parts"][1])
                    if sig["hash"] == "qh_bi_sales_dash":
                        ptotal = 120_000
                    if sig["hash"] in ("qh_elt_orders_load", "qh_elt_revenue_agg"):
                        ptotal = 72_000
                    pscan = 0 if cached else int(rng.uniform(*sig["parts"]))
                    user = sig["users"][rng.randrange(len(sig["users"]))]
                    role = sig["role"]
                    text = sig["text"]
                    if not sig.get("identical") and "?" in text:
                        text = text.replace("?", f"'{d - timedelta(days=rng.randint(0, 30))}'")
                    rec = dict(
                        QUERY_ID=qid, QUERY_TEXT=text, QUERY_PARAMETERIZED_HASH=sig["hash"], QUERY_TYPE=sig["type"],
                        DATABASE_NAME="EDW", SCHEMA_NAME=None, USER_NAME=user, ROLE_NAME=role, WAREHOUSE_NAME=w["name"],
                        WAREHOUSE_SIZE=w["size"], QUERY_TAG=sig["tag"], EXECUTION_STATUS="SUCCESS", ERROR_MESSAGE=None,
                        START_TIME=st, END_TIME=st + timedelta(milliseconds=ex + qo), TOTAL_ELAPSED_TIME=ex + qo + 120,
                        EXECUTION_TIME=ex, QUEUED_OVERLOAD_TIME=qo, COMPILATION_TIME=120, BYTES_SCANNED=scan,
                        PERCENTAGE_SCANNED_FROM_CACHE=0.0 if not cached else 1.0,
                        BYTES_WRITTEN=int(rng.uniform(*sig.get("written", (0, 0)))),
                        ROWS_PRODUCED=int(rng.uniform(*sig["rows"])),
                        ROWS_INSERTED=int(rng.uniform(*sig.get("inserted", (0, 0)))),
                        PARTITIONS_SCANNED=pscan, PARTITIONS_TOTAL=ptotal,
                        BYTES_SPILLED_TO_LOCAL_STORAGE=int(rng.uniform(*sig.get("spill_local", (0, 0)))),
                        BYTES_SPILLED_TO_REMOTE_STORAGE=int(rng.uniform(*sig.get("spill_remote", (0, 0)))),
                        CREDITS_USED_CLOUD_SERVICES=round(0.00001 * (ex / 1000 + 1), 8),
                        CLIENT_APPLICATION_ID=sig["app"])
                    recs.append(rec)
                    for obj in sig.get("reads", []):
                        T["ACCESS_HISTORY"].append(dict(QUERY_ID=qid, QUERY_START_TIME=st, USER_NAME=user,
                                                        OBJECT_NAME=obj, OBJECT_DOMAIN="Table", ACCESS_TYPE="READ"))
                        access_last[obj] = max(access_last.get(obj, st), st)
                    for obj in sig.get("writes", []):
                        T["ACCESS_HISTORY"].append(dict(QUERY_ID=qid, QUERY_START_TIME=st, USER_NAME=user,
                                                        OBJECT_NAME=obj, OBJECT_DOMAIN="Table", ACCESS_TYPE="WRITE"))
                        access_last[obj] = max(access_last.get(obj, st), st)
                total_ex = sum(r["EXECUTION_TIME"] for r in recs) or 1
                for r in recs:
                    T["QUERY_HISTORY"].append(r)
                    T["QUERY_ATTRIBUTION_HISTORY"].append(dict(
                        QUERY_ID=r["QUERY_ID"], WAREHOUSE_NAME=w["name"],
                        QUERY_PARAMETERIZED_HASH=r["QUERY_PARAMETERIZED_HASH"], QUERY_TAG=r["QUERY_TAG"],
                        USER_NAME=r["USER_NAME"], START_TIME=r["START_TIME"], END_TIME=r["END_TIME"],
                        CREDITS_ATTRIBUTED_COMPUTE=round(attributed_total * r["EXECUTION_TIME"] / total_ex, 8)))

        # ------------------------------------------------ BI refresh traffic (DX-BI-03) on WH_BI_PROD
        rng = _rng(spec, "bi_refresh", d)
        refreshes = 48 if s("DX-BI-03") else 2
        for k in range(refreshes):
            st = _ts(d, 0) + timedelta(minutes=30 * k * (48 // refreshes))
            qid = _qid(spec, d, "BI_REFRESH", k)
            ex = int(rng.uniform(8000, 12000))
            T["QUERY_HISTORY"].append(dict(
                QUERY_ID=qid, QUERY_TEXT="SELECT * FROM EDW.SALES.FCT_EVENTS WHERE EVENT_TS >= DATEADD(hour, -1, CURRENT_TIMESTAMP())",
                QUERY_PARAMETERIZED_HASH="qh_bi_ops_live", QUERY_TYPE="SELECT", DATABASE_NAME="EDW", SCHEMA_NAME="SALES",
                USER_NAME="SVC_POWERBI", ROLE_NAME="FR_BI", WAREHOUSE_NAME="WH_BI_PROD", WAREHOUSE_SIZE="MEDIUM",
                QUERY_TAG="powerbi", EXECUTION_STATUS="SUCCESS", ERROR_MESSAGE=None, START_TIME=st,
                END_TIME=st + timedelta(milliseconds=ex), TOTAL_ELAPSED_TIME=ex + 100, EXECUTION_TIME=ex,
                QUEUED_OVERLOAD_TIME=0, COMPILATION_TIME=100, BYTES_SCANNED=int(rng.uniform(5, 8) * GB),
                PERCENTAGE_SCANNED_FROM_CACHE=0.0, BYTES_WRITTEN=0, ROWS_PRODUCED=50_000, ROWS_INSERTED=0,
                PARTITIONS_SCANNED=600, PARTITIONS_TOTAL=120_000, BYTES_SPILLED_TO_LOCAL_STORAGE=0,
                BYTES_SPILLED_TO_REMOTE_STORAGE=0, CREDITS_USED_CLOUD_SERVICES=0.0001, CLIENT_APPLICATION_ID="PowerBI"))
            T["QUERY_ATTRIBUTION_HISTORY"].append(dict(
                QUERY_ID=qid, WAREHOUSE_NAME="WH_BI_PROD", QUERY_PARAMETERIZED_HASH="qh_bi_ops_live", QUERY_TAG="powerbi",
                USER_NAME="SVC_POWERBI", START_TIME=st, END_TIME=st + timedelta(milliseconds=ex),
                CREDITS_ATTRIBUTED_COMPUTE=round(4 * ex / 3_600_000, 8)))
            T["ACCESS_HISTORY"].append(dict(QUERY_ID=qid, QUERY_START_TIME=st, USER_NAME="SVC_POWERBI",
                                            OBJECT_NAME="EDW.SALES.FCT_EVENTS", OBJECT_DOMAIN="Table", ACCESS_TYPE="READ"))

        # ------------------------------------------------ admin activity (DX-SEC-02) and DDL (DX-OPS-01)
        rng = _rng(spec, "admin", d)
        admins = ["ADMIN_1", "ADMIN_2"] + (["JSMITH", "TEMP_CONTRACTOR", "OPS_LEAD"] if s("DX-SEC-02") else [])
        n_admin = (6 if s("DX-SEC-02") else (1 if d.day == 1 else 0))
        for k in range(n_admin):
            u = admins[k % len(admins)]
            st = _ts(d, 10 + k % 8, rng.randint(0, 59))
            T["QUERY_HISTORY"].append(_simple_query(spec, d, f"ADM{k}", st, "SHOW GRANTS TO ROLE SYSADMIN", "SHOW", u,
                                                    "ACCOUNTADMIN", None, None, "Snowflake Web App"))
        ddl_events = []
        if weekday and d.day % 3 == 0:
            ddl_events.append(("SVC_TERRAFORM", "SYSADMIN", "terraform", "CREATE_TABLE",
                               "CREATE TABLE IF NOT EXISTS EDW.SALES.FCT_RETURNS (...)"))
        if s("DX-OPS-01") and weekday and d.day % 4 == 0:
            ddl_events.append(("JSMITH", "SYSADMIN", None, "ALTER_TABLE_ADD_COLUMN",
                               "ALTER TABLE EDW.SALES.FCT_ORDERS ADD COLUMN PROMO_CODE VARCHAR"))
            ddl_events.append(("JSMITH", "SYSADMIN", None, "CREATE_VIEW",
                               "CREATE OR REPLACE VIEW EDW.MART.V_ORDERS_SUMMARY AS SELECT ..."))
        for k, (u, role, tag, qtype, text) in enumerate(ddl_events):
            st = _ts(d, 14, 5 * k)
            T["QUERY_HISTORY"].append(_simple_query(spec, d, f"DDL{k}", st, text, qtype, u, role, "WH_ELT_PROD", tag,
                                                    "SnowSQL" if tag is None else "Terraform"))

        # ------------------------------------------------ tasks (DX-REL-01 / DX-REL-02)
        rng = _rng(spec, "tasks", d)
        task_specs = [
            ("EDW.STAGING.INGEST_EVENTS_TASK", 0, 0.30 if s("DX-REL-01") else 0.0, None),
            ("EDW.SALES.BUILD_EVENTS_AGG", 1, 0.0, "EDW.STAGING.INGEST_EVENTS_TASK"),
            ("EDW.SALES.LOAD_ORDERS_TASK", 1, 0.0, None),
            ("EDW.FINANCE.LOAD_REVENUE_TASK", 3, 0.0, "EDW.SALES.LOAD_ORDERS_TASK"),
        ]
        failed: set[str] = set()
        for name, hour, fail_p, pred in task_specs:
            db, sch, nm = _fq(name)
            sched = _ts(d, hour)
            run_id = hashlib.md5(f"{name}{d}".encode()).hexdigest()[:12]
            if pred and pred in failed:
                state, err, completed, qs = "SKIPPED", None, sched, None
            elif rng.random() < fail_p:
                state, err = "FAILED", "100038 (22018): Numeric value 'N/A' is not recognized"
                qs = sched + timedelta(minutes=1)
                completed = qs + timedelta(minutes=3)
                failed.add(name)
            else:
                state, err, qs = "SUCCEEDED", None, sched + timedelta(minutes=1)
                duration = 25
                if name == "EDW.FINANCE.LOAD_REVENUE_TASK" and s("DX-REL-02") and rng.random() < 0.45:
                    duration = 200  # completes ~06:21, after the 06:00 SLA
                completed = qs + timedelta(minutes=duration)
            T["TASK_HISTORY"].append(dict(
                NAME=nm, DATABASE_NAME=db, SCHEMA_NAME=sch, FQ_NAME=name, STATE=state,
                ERROR_CODE="100038" if err else None, ERROR_MESSAGE=err, SCHEDULED_TIME=sched, QUERY_START_TIME=qs,
                COMPLETED_TIME=completed, ROOT_TASK_ID=(pred or name), RUN_ID=run_id, ATTEMPT_NUMBER=1,
                QUERY_ID=_qid(spec, d, name, 0)))

        # ------------------------------------------------ serverless
        rng = _rng(spec, "serverless", d)
        clus = [("EDW.SALES.FCT_ORDERS", 2.0)]
        clus.append(("EDW.RAW.EVENTS_LOG", 38.0 if s("DX-COST-05") else 0.5))
        for tname, cr in clus:
            c = round(cr * rng.uniform(0.8, 1.2), 4)
            T["AUTOMATIC_CLUSTERING_HISTORY"].append(dict(
                START_TIME=_ts(d, 2), END_TIME=_ts(d, 3), TABLE_NAME=tname, CREDITS_USED=c,
                NUM_BYTES_RECLUSTERED=int(c * 40 * GB), NUM_ROWS_RECLUSTERED=int(c * 10_000_000)))
        pipe_c = round(0.6 * rng.uniform(0.8, 1.2), 4)
        T["PIPE_USAGE_HISTORY"].append(dict(START_TIME=_ts(d, 0), END_TIME=_ts(d, 23, 59), PIPE_NAME="EDW.RAW.EVENTS_PIPE",
                                            CREDITS_USED=pipe_c, BYTES_INSERTED=int(25 * GB), FILES_INSERTED=480))
        for k in range(4):
            T["COPY_HISTORY"].append(dict(FILE_NAME=f"events/{d}/part-{k:04d}.parquet", TABLE_NAME="EDW.RAW.EVENTS_LOG",
                                          PIPE_NAME="EDW.RAW.EVENTS_PIPE", LAST_LOAD_TIME=_ts(d, 6 * k),
                                          ROW_COUNT=8_000_000, ERROR_COUNT=0, STATUS="Loaded"))
        T["ACCESS_HISTORY"].append(dict(QUERY_ID=_qid(spec, d, "PIPE", 0), QUERY_START_TIME=_ts(d, 6), USER_NAME="SVC_FIVETRAN",
                                        OBJECT_NAME="EDW.RAW.EVENTS_LOG", OBJECT_DOMAIN="Table", ACCESS_TYPE="WRITE"))
        access_last["EDW.RAW.EVENTS_LOG"] = _ts(d, 6)
        if d == spec.end_date and not s("DX-COST-05"):
            access_last.setdefault("EDW.RAW.EVENTS_LOG", _ts(d, 6))

        # cortex
        rng = _rng(spec, "cortex", d)
        cortex_credits = 0.0
        if weekday:
            for k in range(6):
                c = round(rng.uniform(0.05, 0.2), 4)
                cortex_credits += c
                T["CORTEX_USAGE_HISTORY"].append(dict(
                    START_TIME=_ts(d, 9 + k), END_TIME=_ts(d, 9 + k, 1), FUNCTION_NAME="COMPLETE",
                    MODEL_NAME="claude-sonnet-5-5", AGENT_NAME=None if s("DX-AI-02") else "SALES_AGENT",
                    ROLE_NAME="FR_ANALYST" if s("DX-AI-02") else "AGENT_ROLE",
                    USER_NAME=ANALYSTS[k % len(ANALYSTS)] if s("DX-AI-02") else "SVC_AGENT",
                    TOKENS=int(c * 1_000_000), TOKEN_CREDITS=c))

        # metering daily (billing truth)
        total_clus = sum(r["CREDITS_USED"] for r in T["AUTOMATIC_CLUSTERING_HISTORY"][-len(clus):])
        cloud = daily_cloud.get(d, 0.0)
        compute = daily_wh_credits.get(d, 0.0) - cloud
        adj = -min(cloud, 0.1 * compute)
        T["METERING_DAILY_HISTORY"].append(dict(
            USAGE_DATE=d, SERVICE_TYPE="WAREHOUSE_METERING", CREDITS_USED_COMPUTE=round(compute, 6),
            CREDITS_USED_CLOUD_SERVICES=round(cloud, 6), CREDITS_USED=round(compute + cloud, 6),
            CREDITS_ADJUSTMENT_CLOUD_SERVICES=round(adj, 6), CREDITS_BILLED=round(compute + cloud + adj, 6)))
        for stype, cr in (("AUTO_CLUSTERING", total_clus), ("PIPE", pipe_c), ("AI_SERVICES", cortex_credits)):
            if cr:
                T["METERING_DAILY_HISTORY"].append(dict(
                    USAGE_DATE=d, SERVICE_TYPE=stype, CREDITS_USED_COMPUTE=round(cr, 6), CREDITS_USED_CLOUD_SERVICES=0.0,
                    CREDITS_USED=round(cr, 6), CREDITS_ADJUSTMENT_CLOUD_SERVICES=0.0, CREDITS_BILLED=round(cr, 6)))

        # logins
        rng = _rng(spec, "logins", d)
        for u in users:
            if u["last_login"].date() < d:
                continue
            if u["type"] == "PERSON" and not weekday:
                continue
            first = "RSA_KEYPAIR" if u["rsa"] else ("SAML2_ASSERTION" if u["sso"] else "PASSWORD")
            second = "MFA" if (u["mfa"] and first == "PASSWORD") else None
            T["LOGIN_HISTORY"].append(dict(
                EVENT_ID=hashlib.md5(f"{u['name']}{d}".encode()).hexdigest()[:16], EVENT_TIMESTAMP=_ts(d, 8, rng.randint(0, 59)),
                USER_NAME=u["name"], CLIENT_IP=f"10.0.{rng.randint(0, 9)}.{rng.randint(1, 250)}",
                REPORTED_CLIENT_TYPE="SNOWFLAKE_UI" if u["type"] == "PERSON" else "PYTHON_DRIVER",
                FIRST_AUTHENTICATION_FACTOR=first, SECOND_AUTHENTICATION_FACTOR=second, IS_SUCCESS="YES",
                ERROR_CODE=None, ERROR_MESSAGE=None))
        if rng.random() < 0.2:
            T["LOGIN_HISTORY"].append(dict(
                EVENT_ID=hashlib.md5(f"fail{d}".encode()).hexdigest()[:16], EVENT_TIMESTAMP=_ts(d, 3, 12),
                USER_NAME="ADMIN_1", CLIENT_IP="203.0.113.7", REPORTED_CLIENT_TYPE="OTHER",
                FIRST_AUTHENTICATION_FACTOR="PASSWORD", SECOND_AUTHENTICATION_FACTOR=None, IS_SUCCESS="NO",
                ERROR_CODE="390100", ERROR_MESSAGE="INCORRECT_USERNAME_PASSWORD"))

        # DQ results
        for tname, metric in (("EDW.SALES.FCT_ORDERS", "NULL_COUNT"), ("EDW.SALES.DIM_CUSTOMER", "DUPLICATE_COUNT")):
            T["DATA_QUALITY_MONITORING_RESULTS"].append(dict(MEASUREMENT_TIME=_ts(d, 7), TABLE_NAME=tname,
                                                             METRIC_NAME=metric, VALUE=0.0, EXPECTATION_VIOLATED=False))

        # storage
        tot = sum(t["bytes"] for t in tables)
        T["STORAGE_USAGE"].append(dict(USAGE_DATE=d, STORAGE_BYTES=tot, STAGE_BYTES=int(200 * GB),
                                       FAILSAFE_BYTES=int(tot * 0.05), HYBRID_TABLE_STORAGE_BYTES=0))

    seed("DX-COST-03", "qh_bi_sales_dash")
    control("DX-COST-03", "qh_bi_customer")
    seed("DX-COST-04", "EDW.SALES.FCT_ORDERS")
    control("DX-COST-04", "EDW.SALES.DIM_REGION")
    seed("DX-COST-05", "EDW.RAW.EVENTS_LOG")
    control("DX-COST-05", "EDW.SALES.FCT_ORDERS")
    seed("DX-PERF-02", "qh_elt_revenue_agg")
    control("DX-PERF-02", "qh_elt_orders_load", "qh_ds_features")
    seed("DX-PERF-03", "EDW.SALES.FCT_EVENTS")
    control("DX-PERF-03", "EDW.SALES.FCT_ORDERS")
    seed("DX-PERF-04", "qh_bi_finance_wide")
    control("DX-PERF-04", "qh_ds_features")
    seed("DX-REL-01", "EDW.STAGING.INGEST_EVENTS_TASK")
    control("DX-REL-01", "EDW.SALES.LOAD_ORDERS_TASK", "EDW.SALES.BUILD_EVENTS_AGG")
    seed("DX-REL-02", "EDW.FINANCE.FCT_REVENUE")
    control("DX-REL-02", "EDW.SALES.FCT_ORDERS")
    seed("DX-REL-03", "JSMITH")
    control("DX-REL-03", "SVC_DBT")
    seed("DX-SEC-02", "ACCOUNTADMIN")
    seed("DX-OPS-01", "JSMITH")
    control("DX-OPS-01", "SVC_TERRAFORM")
    seed("DX-BI-03", "RPT-006")
    control("DX-BI-03", "RPT-001")

    # ---------------------------------------------------------------- tasks inventory
    task_defs = [
        ("EDW.STAGING.INGEST_EVENTS_TASK", None, "EDW.SALES.FCT_EVENTS"),
        ("EDW.SALES.BUILD_EVENTS_AGG", "EDW.STAGING.INGEST_EVENTS_TASK", None),
        ("EDW.SALES.LOAD_ORDERS_TASK", None, "EDW.SALES.FCT_ORDERS"),
        ("EDW.FINANCE.LOAD_REVENUE_TASK", "EDW.SALES.LOAD_ORDERS_TASK", "EDW.FINANCE.FCT_REVENUE"),
    ]
    for name, pred, target in task_defs:
        db, sch, nm = _fq(name)
        T["TASKS"].append(dict(TASK_NAME=nm, DATABASE_NAME=db, SCHEMA_NAME=sch, FQ_NAME=name, OWNER="FR_ENGINEER",
                               WAREHOUSE="WH_ELT_PROD", SCHEDULE=None if pred else "USING CRON 0 1 * * * UTC",
                               PREDECESSORS=pred, STATE="started", TARGET_TABLE=target, DEFINITION=f"CALL {nm}_PROC()"))

    # ---------------------------------------------------------------- tables, storage metrics, columns, tags
    end = _ts(spec.end_date, 0)
    for i, t in enumerate(tables):
        db, sch, nm = _fq(t["fq"])
        created = t.get("created", end - timedelta(days=500))
        last_altered = t.get("last_altered", end - timedelta(days=1))
        T["TABLES"].append(dict(
            TABLE_ID=1000 + i, TABLE_CATALOG=db, TABLE_SCHEMA=sch, TABLE_NAME=nm, FQ_NAME=t["fq"], TABLE_TYPE="BASE TABLE",
            IS_TRANSIENT=t["transient"], IS_ICEBERG=False, CLUSTERING_KEY=t["cluster"], ROW_COUNT=t["rows"],
            BYTES=t["bytes"], RETENTION_TIME=t["retention"], CREATED=created, LAST_ALTERED=last_altered,
            LAST_DDL=created, TABLE_OWNER="SYSADMIN", COMMENT=t["comment"],
            CLONE_GROUP_ID=1000 if t["fq"] in ("EDW.SALES.FCT_ORDERS", "EDW.SALES.FCT_ORDERS_CLONE_2025") else 1000 + i,
            COLUMN_SIGNATURE=hashlib.md5(",".join(t["cols"]).encode()).hexdigest()[:16]))
        tt = int(t["bytes"] * (0.9 if t["retention"] >= 7 and "STAGING" in t["fq"] else 0.02 * t["retention"]))
        T["TABLE_STORAGE_METRICS"].append(dict(
            ID=1000 + i, TABLE_CATALOG=db, TABLE_SCHEMA=sch, TABLE_NAME=nm, FQ_NAME=t["fq"], IS_TRANSIENT=t["transient"],
            ACTIVE_BYTES=t["bytes"], TIME_TRAVEL_BYTES=tt, FAILSAFE_BYTES=0 if t["transient"] else int(t["bytes"] * 0.05),
            RETAINED_FOR_CLONE_BYTES=t.get("retained_for_clone", 0), DELETED=False,
            CLONE_GROUP_ID=1000 if "FCT_ORDERS" in t["fq"] and "COPY" not in t["fq"] else 1000 + i))
        n_comment = round(len(t["cols"]) * t["col_comment_pct"])
        for j, c in enumerate(t["cols"]):
            T["COLUMNS"].append(dict(TABLE_CATALOG=db, TABLE_SCHEMA=sch, TABLE_NAME=nm, FQ_NAME=t["fq"], COLUMN_NAME=c,
                                     ORDINAL_POSITION=j + 1,
                                     DATA_TYPE="NUMBER" if c.endswith(("_ID", "AMOUNT")) else "VARCHAR",
                                     IS_NULLABLE="YES", COMMENT=f"{c.lower().replace('_', ' ')}" if j < n_comment else None))
        if t["owner_tag"]:
            T["TAG_REFERENCES"].append(dict(TAG_DATABASE="GOVERNANCE", TAG_SCHEMA="TAGS", TAG_NAME="DATA_OWNER",
                                            TAG_VALUE=t["owner_tag"], OBJECT_DATABASE=db, OBJECT_SCHEMA=sch,
                                            OBJECT_NAME=nm, COLUMN_NAME=None, DOMAIN="TABLE"))
        if t["fq"] in TIER1:
            T["TAG_REFERENCES"].append(dict(TAG_DATABASE="GOVERNANCE", TAG_SCHEMA="TAGS", TAG_NAME="TIER",
                                            TAG_VALUE="tier1", OBJECT_DATABASE=db, OBJECT_SCHEMA=sch, OBJECT_NAME=nm,
                                            COLUMN_NAME=None, DOMAIN="TABLE"))
    seed("DX-COST-06", "EDW.STAGING.STG_ORDERS", "EDW.SALES.FCT_ORDERS_CLONE_2025")
    control("DX-COST-06", "EDW.SALES.FCT_ORDERS", "EDW.SALES.DIM_REGION")
    seed("DX-GOV-01", "EDW.FINANCE.FCT_REVENUE")
    control("DX-GOV-01", "EDW.SALES.FCT_ORDERS", "EDW.SALES.DIM_CUSTOMER")
    seed("DX-AI-03", "EDW.FINANCE.FCT_REVENUE")
    control("DX-AI-03", "EDW.SALES.FCT_ORDERS")
    legacy = [t["fq"] for t in tables if t["fq"].startswith("EDW.LEGACY.")]
    seed("DX-GOV-03", *legacy, *(["EDW.SALES.FCT_ORDERS_CLONE_2025"] if s("DX-COST-06") else []))
    control("DX-GOV-03", "EDW.SALES.FCT_ORDERS", "EDW.SALES.DIM_REGION", "EDW.SALES.DIM_PRODUCT")
    seed("DX-ARCH-01", "EDW.SALES.ORDERS_COPY", "EDW.MART.V_REVENUE_FINAL")
    control("DX-ARCH-01", "EDW.MART.V_ORDERS_SUMMARY")

    # PII tags & masking (DX-SEC-05)
    for col, masked in (("SSN", True), ("PHONE", True), ("EMAIL", not s("DX-SEC-05"))):
        T["TAG_REFERENCES"].append(dict(TAG_DATABASE="GOVERNANCE", TAG_SCHEMA="TAGS", TAG_NAME="PII", TAG_VALUE=col.lower(),
                                        OBJECT_DATABASE="EDW", OBJECT_SCHEMA="SALES", OBJECT_NAME="DIM_CUSTOMER",
                                        COLUMN_NAME=col, DOMAIN="COLUMN"))
        if masked:
            T["POLICY_REFERENCES"].append(dict(
                POLICY_NAME=f"MP_{col}", POLICY_KIND="MASKING_POLICY", REF_DATABASE_NAME="EDW", REF_SCHEMA_NAME="SALES",
                REF_ENTITY_NAME="DIM_CUSTOMER", REF_ENTITY_DOMAIN="TABLE", REF_COLUMN_NAME=col, TAG_NAME=None,
                POLICY_STATUS="ACTIVE"))
    seed("DX-SEC-05", "EDW.SALES.DIM_CUSTOMER.EMAIL")
    control("DX-SEC-05", "EDW.SALES.DIM_CUSTOMER.SSN")

    # DMFs (DX-GOV-02)
    dmf_tables = ["EDW.SALES.FCT_ORDERS", "EDW.SALES.DIM_CUSTOMER"] + ([] if s("DX-GOV-02") else ["EDW.FINANCE.FCT_REVENUE"])
    for tname in dmf_tables:
        T["DATA_METRIC_FUNCTION_REFERENCES"].append(dict(
            METRIC_DATABASE_NAME="SNOWFLAKE", METRIC_NAME="NULL_COUNT", REF_ENTITY_NAME=tname, REF_ENTITY_DOMAIN="TABLE",
            SCHEDULE="TRIGGER_ON_CHANGES", SCHEDULE_STATUS="STARTED"))
    seed("DX-GOV-02", "EDW.FINANCE.FCT_REVENUE")
    control("DX-GOV-02", "EDW.SALES.FCT_ORDERS")

    # ---------------------------------------------------------------- views & dependencies (DX-ARCH-01)
    chain = [f"EDW.MART.V_REV_{i}" for i in range(1, 7)] + ["EDW.MART.V_REVENUE_FINAL"]
    if not s("DX-ARCH-01"):
        chain = ["EDW.MART.V_REV_1", "EDW.MART.V_REVENUE_FINAL"]
    prev = "EDW.FINANCE.FCT_REVENUE"
    for v in chain:
        db, sch, nm = _fq(v)
        T["VIEWS"].append(dict(TABLE_CATALOG=db, TABLE_SCHEMA=sch, TABLE_NAME=nm, FQ_NAME=v,
                               VIEW_DEFINITION=f"CREATE VIEW {v} AS SELECT * FROM {prev}", IS_SECURE=False, COMMENT=None))
        T["OBJECT_DEPENDENCIES"].append(dict(REFERENCING_OBJECT_NAME=v, REFERENCING_OBJECT_DOMAIN="VIEW",
                                             REFERENCED_OBJECT_NAME=prev,
                                             REFERENCED_OBJECT_DOMAIN="TABLE" if prev == "EDW.FINANCE.FCT_REVENUE" else "VIEW",
                                             DEPENDENCY_TYPE="BY_NAME"))
        prev = v
    for v, src in (("EDW.MART.V_ORDERS_BASE", "EDW.SALES.FCT_ORDERS"), ("EDW.MART.V_ORDERS_SUMMARY", "EDW.MART.V_ORDERS_BASE")):
        db, sch, nm = _fq(v)
        T["VIEWS"].append(dict(TABLE_CATALOG=db, TABLE_SCHEMA=sch, TABLE_NAME=nm, FQ_NAME=v,
                               VIEW_DEFINITION=f"CREATE VIEW {v} AS SELECT * FROM {src}", IS_SECURE=False,
                               COMMENT="Orders summary"))
        T["OBJECT_DEPENDENCIES"].append(dict(REFERENCING_OBJECT_NAME=v, REFERENCING_OBJECT_DOMAIN="VIEW",
                                             REFERENCED_OBJECT_NAME=src,
                                             REFERENCED_OBJECT_DOMAIN="TABLE" if src.startswith("EDW.SALES") else "VIEW",
                                             DEPENDENCY_TYPE="BY_NAME"))

    # ---------------------------------------------------------------- users, roles, grants, network
    for u in users:
        T["USERS"].append(dict(
            NAME=u["name"], TYPE=u["type"], LOGIN_NAME=u["name"].lower(),
            DEFAULT_ROLE="FR_ANALYST" if u["name"].startswith("ANALYST") else "PUBLIC", HAS_PASSWORD=u["password"],
            HAS_MFA=u["mfa"], HAS_RSA_PUBLIC_KEY=u["rsa"], EXT_AUTHN_UID=u["name"].lower() + "@acme.com" if u["sso"] else None,
            DISABLED=False, CREATED_ON=u["created"], LAST_SUCCESS_LOGIN=u["last_login"],
            NETWORK_POLICY="NP_SERVICES" if u["type"] != "PERSON" and not s("DX-SEC-04") else None, OWNER="USERADMIN",
            COMMENT=None))
    seed("DX-SEC-01", "JSMITH", "TEMP_CONTRACTOR", "SVC_FIVETRAN")
    control("DX-SEC-01", "SVC_DBT", "ADMIN_1", "ANALYST_01")
    seed("DX-SEC-03", "OLD_ANALYST", "ROLE_LEGACY_MKTG")
    control("DX-SEC-03", "ANALYST_01", "FR_ANALYST")
    seed("DX-SEC-04", "ACCOUNT")
    roles = ["ACCOUNTADMIN", "SECURITYADMIN", "SYSADMIN", "USERADMIN", "PUBLIC", "FR_ANALYST", "FR_ENGINEER", "FR_BI",
             "AR_EDW_READ", "AR_EDW_WRITE", "AGENT_ROLE"] + (["ROLE_LEGACY_MKTG"] if s("DX-SEC-03") else [])
    created = end - timedelta(days=600)
    for r in roles:
        T["ROLES"].append(dict(NAME=r, ROLE_TYPE="ROLE", OWNER="SECURITYADMIN", COMMENT=None, CREATED_ON=created))
    hierarchy = [("AR_EDW_READ", "FR_ANALYST"), ("AR_EDW_READ", "FR_BI"), ("AR_EDW_READ", "AGENT_ROLE"),
                 ("AR_EDW_WRITE", "FR_ENGINEER"), ("FR_ANALYST", "SYSADMIN"), ("FR_ENGINEER", "SYSADMIN"),
                 ("FR_BI", "SYSADMIN"), ("AGENT_ROLE", "SYSADMIN"), ("SYSADMIN", "ACCOUNTADMIN"),
                 ("SECURITYADMIN", "ACCOUNTADMIN"), ("USERADMIN", "SECURITYADMIN")]
    for child, parent in hierarchy:
        T["GRANTS_TO_ROLES"].append(dict(PRIVILEGE="USAGE", GRANTED_ON="ROLE", NAME=child, TABLE_CATALOG=None,
                                         TABLE_SCHEMA=None, GRANTED_TO="ROLE", GRANTEE_NAME=parent, GRANT_OPTION=False,
                                         GRANTED_BY="SECURITYADMIN", CREATED_ON=created))
    for priv, role in (("SELECT", "AR_EDW_READ"), ("INSERT", "AR_EDW_WRITE"), ("UPDATE", "AR_EDW_WRITE")):
        T["GRANTS_TO_ROLES"].append(dict(PRIVILEGE=priv, GRANTED_ON="TABLE", NAME="FCT_ORDERS", TABLE_CATALOG="EDW",
                                         TABLE_SCHEMA="SALES", GRANTED_TO="ROLE", GRANTEE_NAME=role, GRANT_OPTION=False,
                                         GRANTED_BY="SYSADMIN", CREATED_ON=created))
    if s("DX-SEC-03"):
        T["GRANTS_TO_ROLES"].append(dict(PRIVILEGE="SELECT", GRANTED_ON="TABLE", NAME="CAMPAIGN_2019", TABLE_CATALOG="EDW",
                                         TABLE_SCHEMA="LEGACY", GRANTED_TO="ROLE", GRANTEE_NAME="ROLE_LEGACY_MKTG",
                                         GRANT_OPTION=False, GRANTED_BY="SYSADMIN", CREATED_ON=created))
    for u in users:
        role = ("FR_ANALYST" if u["name"].startswith(("ANALYST", "OLD_")) else
                "FR_BI" if u["name"] == "SVC_POWERBI" else "AGENT_ROLE" if u["name"] == "SVC_AGENT" else
                "SYSADMIN" if u["name"] == "SVC_TERRAFORM" else "FR_ENGINEER")
        T["GRANTS_TO_USERS"].append(dict(ROLE=role, GRANTED_TO="USER", GRANTEE_NAME=u["name"], GRANTED_BY="USERADMIN",
                                         CREATED_ON=created))
        if u["admin"]:
            T["GRANTS_TO_USERS"].append(dict(ROLE="ACCOUNTADMIN", GRANTED_TO="USER", GRANTEE_NAME=u["name"],
                                             GRANTED_BY="ACCOUNTADMIN", CREATED_ON=created))
    T["NETWORK_POLICIES"].append(dict(NAME="NP_SERVICES", ALLOWED_IP_LIST="10.0.0.0/8", BLOCKED_IP_LIST=None,
                                      ALLOWED_NETWORK_RULE_LIST=None, OWNER="SECURITYADMIN"))
    if not s("DX-SEC-04"):
        T["NETWORK_POLICIES"].append(dict(NAME="NP_CORPORATE", ALLOWED_IP_LIST="10.0.0.0/8,192.0.2.0/24",
                                          BLOCKED_IP_LIST=None, ALLOWED_NETWORK_RULE_LIST=None, OWNER="SECURITYADMIN"))

    # ---------------------------------------------------------------- replication (DX-REL-04)
    if not s("DX-REL-04"):
        T["REPLICATION_GROUPS"].append(dict(NAME="FG_EDW", TYPE="FAILOVER", OBJECT_TYPES="DATABASES",
                                            ALLOWED_DATABASES="EDW", REPLICATION_SCHEDULE="60 MINUTE", IS_PRIMARY=True))
    seed("DX-REL-04", "EDW")

    # ---------------------------------------------------------------- alerts, budgets, AI
    if not s("DX-OPS-02"):
        for name, cls in (("ALERT_CREDIT_SPIKE", "credit_anomaly"), ("ALERT_TIER1_TASK_FAILED", "task_failure"),
                          ("ALERT_ACCOUNTADMIN_USE", "privileged_use")):
            T["ALERTS"].append(dict(NAME=name, DATABASE_NAME="OBS", SCHEMA_NAME="ALERTS", STATE="started",
                                    CONDITION="SELECT ...", ACTION="CALL SYSTEM$SEND_EMAIL(...)", ALERT_CLASS=cls))
    if not s("DX-AI-02"):
        T["BUDGETS"].append(dict(NAME="BUDGET_CORTEX", SCOPE="CORTEX", SPENDING_LIMIT=500.0, OBJECTS="AGENT_ROLE"))
    T["BUDGETS"].append(dict(NAME="BUDGET_ACCOUNT", SCOPE="ACCOUNT", SPENDING_LIMIT=60000.0, OBJECTS=None))
    seed("DX-AI-02", "CORTEX")
    if not s("DX-AI-01"):
        for dom in ("sales", "finance"):
            T["SEMANTIC_VIEWS"].append(dict(NAME=f"SV_{dom.upper()}", DATABASE_NAME="EDW", SCHEMA_NAME="SEMANTIC",
                                            KPI_DOMAIN=dom, COMMENT=f"Certified {dom} KPIs"))
    seed("DX-AI-01", "sales", "finance")
    T["CORTEX_SEARCH_SERVICES"].append(dict(NAME="CSS_POLICIES", DATABASE_NAME="DOCS", SCHEMA_NAME="SEARCH",
                                            SOURCE_TABLE="DOCS.RAW.POLICY_DOCS", TARGET_LAG="1 day"))

    # ---------------------------------------------------------------- BI layer (DX-BI-01/02/03)
    reports = [
        ("RPT-001", "Sales Overview", "Sales", "S1", "qh_bi_sales_dash", 4200, 24),
        ("RPT-004", "Revenue Dashboard", "Finance", "S4", "qh_bi_finance_wide", 1500, 24),
        ("RPT-005", "Finance Revenue Pack", "Finance", "S5", "qh_bi_finance_wide", 900, 24),
        ("RPT-006", "Ops Live Monitor", "Operations", "S6", "qh_bi_ops_live", 3 if s("DX-BI-03") else 900,
         48 if s("DX-BI-03") else 2),
        ("RPT-007", "Customer 360", "Sales", "S7", "qh_bi_customer", 1100, 24),
    ]
    if s("DX-BI-01"):
        reports += [("RPT-002", "Sales Overview (Copy)", "Sales", "S1", "qh_bi_sales_dash", 35, 24),
                    ("RPT-003", "Sales Overview - Finance", "Finance", "S1", "qh_bi_sales_dash", 60, 24)]
    for rid, name, ws, struct, qh, views, refresh in reports:
        T["BI_REPORTS"].append(dict(REPORT_ID=rid, TOOL="powerbi", NAME=name, WORKSPACE=ws, OWNER=f"{ws.lower()}-bi@acme",
                                    DATASET=f"DS_{ws.upper()}", STRUCTURE_HASH=struct, QUERY_PARAMETERIZED_HASH=qh,
                                    VIEWS_90D=views, REFRESHES_PER_DAY=refresh, LAST_VIEWED=end - timedelta(days=2),
                                    CREATED=end - timedelta(days=300)))
    measures = [("RPT-001", "Revenue", "SUM(NET_AMOUNT)", "FCT_ORDERS.NET_AMOUNT"),
                ("RPT-001", "Orders", "COUNT(DISTINCT ORDER_ID)", "FCT_ORDERS.ORDER_ID"),
                ("RPT-004", "Revenue", "SUM(NET_AMOUNT)", "FCT_REVENUE.NET_AMOUNT"),
                ("RPT-004", "Orders", "COUNT(DISTINCT ORDER_ID)", "FCT_ORDERS.ORDER_ID"),
                ("RPT-005", "Revenue", "SUM(GROSS_AMOUNT)" if s("DX-BI-02") else "SUM(NET_AMOUNT)",
                 "FCT_REVENUE.GROSS_AMOUNT" if s("DX-BI-02") else "FCT_REVENUE.NET_AMOUNT"),
                ("RPT-005", "Orders", "COUNT(DISTINCT ORDER_ID)", "FCT_ORDERS.ORDER_ID"),
                ("RPT-007", "Active Customers", "COUNT(DISTINCT CUSTOMER_ID)", "DIM_CUSTOMER.CUSTOMER_ID")]
    for rid, kpi, expr, cols in measures:
        T["BI_MEASURES"].append(dict(REPORT_ID=rid, KPI_NAME=kpi, EXPRESSION=expr, SOURCE_COLUMNS=cols))
    seed("DX-BI-01", "RPT-002", "RPT-003")
    control("DX-BI-01", "RPT-007")
    seed("DX-BI-02", "Revenue")
    control("DX-BI-02", "Orders")

    # ---------------------------------------------------------------- capacity (DX-COST-08) & client inputs
    total_credits = sum(r["CREDITS_BILLED"] for r in T["METERING_DAILY_HISTORY"])
    run_rate = total_credits / spec.days * 365
    commit = round(run_rate * (1.6 if s("DX-COST-08") else 1.02), 0)
    seed("DX-COST-08", "ACCOUNT")
    inputs = {
        "contract_price_per_credit": spec.price_per_credit,
        "storage_price_per_tb_month": spec.storage_price_per_tb_month,
        "capacity_commitment": {"annual_credits": commit, "start_date": f"{spec.end_date.year}-01-01",
                                "end_date": f"{spec.end_date.year}-12-31"},
        "tier1_tables": TIER1,
        "freshness_slas": [{"table": "EDW.FINANCE.FCT_REVENUE", "loaded_by": "EDW.FINANCE.LOAD_REVENUE_TASK",
                            "deadline_utc": "06:00"},
                           {"table": "EDW.SALES.FCT_ORDERS", "loaded_by": "EDW.SALES.LOAD_ORDERS_TASK",
                            "deadline_utc": "06:00"}],
        "rpo_hours": {"EDW": 4},
        "production_databases": ["EDW"],
        "top_kpi_domains": ["sales", "finance"],
        "cost_center_tag": "COST_CENTER",
        "owner_tag": "DATA_OWNER",
        "bi_tools": ["powerbi"],
        "industry": "utilities",
    }
    for k, v in inputs.items():
        T["CLIENT_INPUTS"].append(dict(KEY=k, VALUE=json.dumps(v, sort_keys=True)))

    return SyntheticAccount(spec=spec, tables=T, seeded=seeded, controls=controls)


def _simple_query(spec: AccountSpec, d: date, key: str, st: datetime, text: str, qtype: str, user: str, role: str,
                  wh: str | None, tag: str | None, app: str) -> dict:
    return dict(
        QUERY_ID=_qid(spec, d, key, 0), QUERY_TEXT=text, QUERY_PARAMETERIZED_HASH=hashlib.md5(text.encode()).hexdigest()[:12],
        QUERY_TYPE=qtype, DATABASE_NAME="EDW", SCHEMA_NAME=None, USER_NAME=user, ROLE_NAME=role, WAREHOUSE_NAME=wh,
        WAREHOUSE_SIZE=None, QUERY_TAG=tag, EXECUTION_STATUS="SUCCESS", ERROR_MESSAGE=None, START_TIME=st,
        END_TIME=st + timedelta(milliseconds=300), TOTAL_ELAPSED_TIME=300, EXECUTION_TIME=200, QUEUED_OVERLOAD_TIME=0,
        COMPILATION_TIME=100, BYTES_SCANNED=0, PERCENTAGE_SCANNED_FROM_CACHE=0.0, BYTES_WRITTEN=0, ROWS_PRODUCED=1,
        ROWS_INSERTED=0, PARTITIONS_SCANNED=0, PARTITIONS_TOTAL=0, BYTES_SPILLED_TO_LOCAL_STORAGE=0,
        BYTES_SPILLED_TO_REMOTE_STORAGE=0, CREDITS_USED_CLOUD_SERVICES=0.00001, CLIENT_APPLICATION_ID=app)


def build_snapshot(directory: str | Path, spec: AccountSpec | None = None, snapshot_id: str | None = None,
                   metadata: dict | None = None):
    """Generate an account and seal it as a diagnostic snapshot. Returns ``(Snapshot, SyntheticAccount)``."""
    from altitude.core.snapshot import SnapshotWriter

    account = generate(spec)
    spec = account.spec
    snapshot_id = snapshot_id or f"SNAP-{spec.organization}-{spec.end_date.isoformat()}-{spec.profile.upper()}"
    meta = {"account_name": spec.account_name, "organization": spec.organization, "window_start": spec.start_date.isoformat(),
            "window_end": spec.end_date.isoformat(), "source": "synthetic", "profile": spec.profile,
            **(metadata or {})}
    writer = SnapshotWriter(directory, snapshot_id, kind="diagnostic", metadata=meta)
    for name, info in HARVEST_SCHEMA.items():
        writer.add_table_from_rows(name, account.tables.get(name, []), info["columns"])
    snap = writer.seal(sealed_at=datetime(spec.end_date.year, spec.end_date.month, spec.end_date.day, 23, 59, 59))
    return snap, account


def score_detection(findings: list[dict], account: SyntheticAccount) -> dict:
    """Score findings against ground truth.

    ``findings``: dicts with ``check_id`` and ``affected_objects`` (list of str).
    - a seeded item is *detected* when some finding for its check lists the object;
    - a finding is a *false positive* when none of its objects are seeded for that
      check, or when it lists a control object for that check.
    """
    seeded = {(x["check_id"], x["object"]) for x in account.seeded}
    controls = {(x["check_id"], x["object"]) for x in account.controls}
    detected = set()
    fps = []
    for f in findings:
        objs = set(f.get("affected_objects") or [])
        hits = {(f["check_id"], o) for o in objs} & seeded
        detected |= hits
        flagged_controls = {(f["check_id"], o) for o in objs} & controls
        if not hits or flagged_controls:
            fps.append({"check_id": f["check_id"], "objects": sorted(objs),
                        "controls_flagged": sorted(o for _, o in flagged_controls)})
    missed = sorted(seeded - detected)
    n = len(findings)
    return {
        "seeded": len(seeded),
        "detected": len(detected),
        "recall": (len(detected) / len(seeded)) if seeded else 1.0,
        "findings": n,
        "false_positives": fps,
        "false_positive_rate": (len(fps) / n) if n else 0.0,
        "missed": [{"check_id": c, "object": o} for c, o in missed],
    }
