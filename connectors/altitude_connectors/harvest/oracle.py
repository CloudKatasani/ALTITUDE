"""Oracle (incl. Exadata) harvester (Section 10.2).

Reads the data dictionary (``DBA_OBJECTS``, ``DBA_SOURCE``, ``DBA_VIEWS``,
``DBA_TAB_COLUMNS``, ``DBA_TABLES``, ``DBA_DEPENDENCIES``, ``DBA_SCHEDULER_*``,
``DBA_TAB_PRIVS``) and ``UNIFIED_AUDIT_TRAIL`` for usage. AWR/ASH are never
read (Diagnostics Pack licensing, OR-11).
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .base import Harvester

SYSTEM_OWNERS = ("SYS", "SYSTEM", "OUTLN", "DBSNMP", "XDB", "MDSYS", "CTXSYS", "ORDSYS", "WMSYS", "APEX_PUBLIC_USER",
                 "AUDSYS", "GSMADMIN_INTERNAL", "LBACSYS", "OJVMSYS", "DVSYS", "PUBLIC")
_OWNERS = ", ".join(f"'{o}'" for o in SYSTEM_OWNERS)
TYPE_MAP = {"TABLE": "table", "VIEW": "view", "MATERIALIZED VIEW": "view", "PROCEDURE": "procedure",
            "FUNCTION": "function", "PACKAGE": "package", "PACKAGE BODY": "package", "TRIGGER": "trigger"}
BLOCK_BYTES = 8192
_FREQ = re.compile(r"FREQ\s*=\s*(\w+)", re.IGNORECASE)
_CALL = re.compile(r"\b([A-Za-z_][\w$#]*(?:\.[A-Za-z_][\w$#]*){0,2})\s*(?:\(|;)")

Q_VERSION = "SELECT VERSION FROM PRODUCT_COMPONENT_VERSION WHERE PRODUCT LIKE 'Oracle%'"
Q_OBJECTS = f"""
SELECT OWNER, OBJECT_NAME, OBJECT_TYPE, STATUS, CREATED, LAST_DDL_TIME
FROM DBA_OBJECTS
WHERE OWNER NOT IN ({_OWNERS})
  AND OBJECT_TYPE IN ('TABLE', 'VIEW', 'MATERIALIZED VIEW', 'PROCEDURE', 'FUNCTION', 'PACKAGE', 'PACKAGE BODY', 'TRIGGER')
"""
Q_SOURCE = f"""
SELECT OWNER, NAME, TYPE, LINE, TEXT
FROM DBA_SOURCE
WHERE OWNER NOT IN ({_OWNERS})
ORDER BY OWNER, NAME, TYPE, LINE
"""
Q_VIEWS = f"SELECT OWNER, VIEW_NAME, TEXT FROM DBA_VIEWS WHERE OWNER NOT IN ({_OWNERS})"
Q_TABLES = f"SELECT OWNER, TABLE_NAME, NUM_ROWS, BLOCKS, TEMPORARY FROM DBA_TABLES WHERE OWNER NOT IN ({_OWNERS})"
Q_COLUMNS = f"""
SELECT OWNER, TABLE_NAME, COLUMN_NAME, COLUMN_ID, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE, NULLABLE,
       CHAR_USED
FROM DBA_TAB_COLUMNS
WHERE OWNER NOT IN ({_OWNERS})
"""
Q_DEPENDENCIES = f"""
SELECT OWNER, NAME, TYPE, REFERENCED_OWNER, REFERENCED_NAME, REFERENCED_TYPE
FROM DBA_DEPENDENCIES
WHERE OWNER NOT IN ({_OWNERS})
"""
Q_JOBS = f"""
SELECT OWNER, JOB_NAME, JOB_TYPE, JOB_ACTION, REPEAT_INTERVAL, ENABLED, RUN_COUNT, LAST_START_DATE
FROM DBA_SCHEDULER_JOBS
WHERE OWNER NOT IN ({_OWNERS})
"""
Q_JOB_RUNS = f"""
SELECT OWNER, JOB_NAME, LOG_DATE, STATUS
FROM DBA_SCHEDULER_JOB_RUN_DETAILS
WHERE OWNER NOT IN ({_OWNERS})
"""
Q_AUDIT = """
SELECT OBJECT_SCHEMA, OBJECT_NAME, DBUSERNAME, EVENT_TIMESTAMP
FROM UNIFIED_AUDIT_TRAIL
WHERE OBJECT_NAME IS NOT NULL AND ACTION_NAME IN ('SELECT', 'EXECUTE', 'INSERT', 'UPDATE', 'DELETE', 'MERGE')
"""
Q_ROLES = "SELECT ROLE FROM DBA_ROLES"
Q_PRIVS = f"SELECT GRANTEE, OWNER, TABLE_NAME, PRIVILEGE FROM DBA_TAB_PRIVS WHERE OWNER NOT IN ({_OWNERS})"


def format_type(c: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    t = str(c["data_type"]).upper()
    attrs: dict[str, Any] = {}
    if t in {"VARCHAR2", "NVARCHAR2", "CHAR", "NCHAR", "RAW"}:
        unit = " CHAR" if c.get("char_used") == "C" else (" BYTE" if c.get("char_used") == "B" else "")
        if c.get("char_used"):
            attrs["char_semantics"] = "char" if c["char_used"] == "C" else "byte"
        return f"{t}({c['data_length']}{unit})", attrs
    if t == "NUMBER":
        if c.get("data_precision") is None:
            attrs["unscaled_number"] = True
            return "NUMBER", attrs
        return f"NUMBER({c['data_precision']},{c.get('data_scale') or 0})", attrs
    if t == "DATE":
        attrs["has_time_component"] = True
    return t, attrs


class OracleHarvester(Harvester):
    source = "oracle"

    def collect(self) -> None:
        ver = self.q(Q_VERSION)
        self.system_version = str(ver[0]["version"]) if ver else None
        key: dict[tuple[str, str], str] = {}
        for o in self.q(Q_OBJECTS):
            otype = TYPE_MAP[o["object_type"]]
            fq = f"{o['owner']}.{o['object_name']}"
            oid = self.add_object(fq, otype, created_at=o["created"], modified_at=o["last_ddl_time"],
                                  status=o["status"])
            if o["object_type"] == "MATERIALIZED VIEW":
                self.set_attr(oid, "materialized", True)
            if o["status"] != "VALID":
                self.set_attr(oid, "invalid", True)
            key[(o["owner"].upper(), o["object_name"].upper())] = oid

        sources: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for s in self.q(Q_SOURCE):
            oid = key.get((s["owner"].upper(), s["name"].upper()))
            if oid:
                sources[oid][s["type"]].append(s["text"] if s["text"].endswith("\n") else s["text"] + "\n")
        for oid, parts in sources.items():
            order = ["PACKAGE", "PACKAGE BODY"] + sorted(t for t in parts if t not in ("PACKAGE", "PACKAGE BODY"))
            text = "\n".join("CREATE OR REPLACE " + "".join(parts[t]) for t in order if t in parts)
            self.texts[oid] = text
        for v in self.q(Q_VIEWS):
            oid = key.get((v["owner"].upper(), v["view_name"].upper()))
            if oid:
                self.texts[oid] = f"CREATE OR REPLACE VIEW {v['owner']}.{v['view_name']} AS\n{v['text'].strip()}\n"

        for t in self.q(Q_TABLES):
            oid = key.get((t["owner"].upper(), t["table_name"].upper()))
            if not oid:
                continue
            if t.get("num_rows") is not None:
                self.set_attr(oid, "row_count", int(t["num_rows"]))
            if t.get("blocks") is not None:
                self.set_attr(oid, "size_bytes", int(t["blocks"]) * BLOCK_BYTES)
            if t.get("temporary") == "Y":
                self.set_attr(oid, "temporary", True)

        for c in self.q(Q_COLUMNS):
            oid = key.get((c["owner"].upper(), c["table_name"].upper()))
            dtype, attrs = format_type(c)
            self.add_column(oid, c["column_name"], c["column_id"], dtype, c["nullable"] == "Y", **attrs)

        for oid in sorted(self.texts):
            self.edges_from_code(oid, self.texts[oid], "code:DBA_SOURCE")
        linked = {(f, t) for f, t, _ in self.edges}
        for d in self.q(Q_DEPENDENCIES):
            src = key.get((d["owner"].upper(), d["name"].upper()))
            tgt = key.get((str(d["referenced_owner"]).upper(), str(d["referenced_name"]).upper()))
            if src and tgt and (src, tgt) not in linked and src != tgt:
                code_target = d["referenced_type"] in {"PROCEDURE", "FUNCTION", "PACKAGE", "PACKAGE BODY"}
                self.add_edge(src, tgt, "calls" if code_target else "reads", "DBA_DEPENDENCIES")
                linked.add((src, tgt))

        self._collect_jobs()
        for a in self.q(Q_AUDIT):
            oid = key.get((str(a["object_schema"]).upper(), str(a["object_name"]).upper()))
            self.add_usage(oid, a["event_timestamp"], 1, a["dbusername"])

        roles = {r["role"].upper() for r in self.q(Q_ROLES)}
        for p in self.q(Q_PRIVS):
            self.add_grant(p["grantee"], "role" if p["grantee"].upper() in roles else "user", p["privilege"],
                           f"{p['owner']}.{p['table_name']}")

    def _resolve_call(self, name: str) -> str | None:
        parts = name.split(".")
        for n in range(len(parts), 0, -1):
            oid = self.resolve(".".join(parts[:n]))
            if oid:
                return oid
        return None

    def _collect_jobs(self) -> None:
        jobs: dict[tuple[str, str], str] = {}
        for j in self.q(Q_JOBS):
            action = str(j["job_action"] or "")
            oid = self.add_object(f"SCHEDULER.{j['owner']}.{j['job_name']}", "schedule", action.strip() + "\n",
                                  scheduler="dbms_scheduler", enabled=str(j["enabled"]).upper() == "TRUE",
                                  job_type=j["job_type"])
            jobs[(j["owner"].upper(), j["job_name"].upper())] = oid
            m = _FREQ.search(str(j["repeat_interval"] or ""))
            if m:
                freq = m.group(1).lower()
                self.set_attr(oid, "schedule_frequency", freq)
                if re.search(r"BYMONTHDAY\s*=\s*-1", str(j["repeat_interval"]), re.IGNORECASE):
                    self.set_attr(oid, "month_end", True)
            if j["job_type"] == "STORED_PROCEDURE":
                self.add_edge(oid, self._resolve_call(action.strip()), "schedules", "DBA_SCHEDULER_JOBS")
            else:
                for name in sorted(set(_CALL.findall(action))):
                    target = self._resolve_call(name)
                    if target and self.objects[target]["object_type"] in {"procedure", "function", "package"}:
                        self.add_edge(oid, target, "schedules", "DBA_SCHEDULER_JOBS")
                self.edges_from_code(oid, action, "DBA_SCHEDULER_JOBS")
        for r in self.q(Q_JOB_RUNS):
            self.add_usage(jobs.get((r["owner"].upper(), r["job_name"].upper())), r["log_date"], 1)
