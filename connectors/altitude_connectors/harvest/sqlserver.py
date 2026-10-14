"""SQL Server / Azure SQL harvester (Section 10.3).

Reads (and only reads) the objects listed in ``knowledge/connectors/sqlserver.yaml``:
``sys.objects``/``sys.sql_modules``/``sys.columns``/``sys.sql_expression_dependencies``,
plan-cache and Query Store usage, ``msdb`` SQL Agent jobs and the ``SSISDB``
catalog. SSIS package logic is read from ``.dtsx`` files in the client's
repository when supplied (``script_dirs``); only extracted SQL and task
metadata is kept.
"""

from __future__ import annotations

import html
import re
from typing import Any

from ..sqlrefs import code_refs
from .base import Harvester

TYPE_MAP = {"U": "table", "V": "view", "P": "procedure", "FN": "function", "IF": "function", "TF": "function",
            "TR": "trigger"}
CHAR_TYPES = {"char", "varchar", "binary", "varbinary"}
NCHAR_TYPES = {"nchar", "nvarchar"}
NUMERIC_TYPES = {"decimal", "numeric"}
# msdb.dbo.sysschedules.freq_type codes.
FREQ_TYPES = {1: "once", 4: "daily", 8: "weekly", 16: "monthly", 32: "monthly_relative", 64: "agent_start",
              128: "idle"}
PAGE_BYTES = 8192
_SSIS_PATH = re.compile(r"\\SSISDB\\([^\\]+)\\([^\\]+)\\([^\\\"]+?\.dtsx)", re.IGNORECASE)

Q_VERSION = "SELECT SERVERPROPERTY('ProductVersion') AS product_version, DB_NAME() AS database_name, DB_ID() AS database_id"
Q_OBJECTS = """
SELECT o.object_id, s.name AS schema_name, o.name AS object_name, o.type AS type_code, o.type_desc,
       o.create_date, o.modify_date, o.parent_object_id
FROM sys.objects AS o
JOIN sys.schemas AS s ON s.schema_id = o.schema_id
WHERE o.is_ms_shipped = 0 AND o.type IN ('U', 'V', 'P', 'FN', 'IF', 'TF', 'TR')
"""
Q_MODULES = "SELECT m.object_id, m.definition FROM sys.sql_modules AS m"
Q_COLUMNS = """
SELECT c.object_id, c.name AS column_name, c.column_id, t.name AS type_name, c.max_length, c.precision, c.scale,
       c.is_nullable, c.collation_name, c.is_identity
FROM sys.columns AS c
JOIN sys.types AS t ON t.user_type_id = c.user_type_id
JOIN sys.objects AS o ON o.object_id = c.object_id
WHERE o.is_ms_shipped = 0 AND o.type IN ('U', 'V')
"""
Q_DEPENDENCIES = """
SELECT d.referencing_id, d.referenced_id, d.referenced_database_name, d.referenced_schema_name,
       d.referenced_entity_name
FROM sys.sql_expression_dependencies AS d
"""
Q_PARTITION_STATS = """
SELECT ps.object_id, SUM(ps.row_count) AS row_count, SUM(ps.reserved_page_count) AS reserved_pages
FROM sys.dm_db_partition_stats AS ps
WHERE ps.index_id IN (0, 1)
GROUP BY ps.object_id
"""
Q_QUERY_STORE_STATE = "SELECT o.actual_state_desc FROM sys.database_query_store_options AS o"
Q_QUERY_STORE = """
SELECT q.query_id, q.object_id, qt.query_sql_text, rs.count_executions, rsi.start_time
FROM sys.query_store_query AS q
JOIN sys.query_store_query_text AS qt ON qt.query_text_id = q.query_text_id
JOIN sys.query_store_plan AS p ON p.query_id = q.query_id
JOIN sys.query_store_runtime_stats AS rs ON rs.plan_id = p.plan_id
JOIN sys.query_store_runtime_stats_interval AS rsi ON rsi.runtime_stats_interval_id = rs.runtime_stats_interval_id
"""
Q_PLAN_CACHE = """
SELECT qs.execution_count, qs.last_execution_time, st.objectid, st.text
FROM sys.dm_exec_query_stats AS qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) AS st
"""
Q_PROC_STATS = """
SELECT ps.object_id, ps.execution_count, ps.last_execution_time
FROM sys.dm_exec_procedure_stats AS ps
WHERE ps.database_id = DB_ID()
"""
Q_PERMISSIONS = """
SELECT pr.name AS grantee, pr.type_desc AS grantee_type, pe.permission_name, pe.state_desc, pe.major_id
FROM sys.database_permissions AS pe
JOIN sys.database_principals AS pr ON pr.principal_id = pe.grantee_principal_id
WHERE pe.class = 1
"""
Q_JOBS = """
SELECT j.job_id, j.name AS job_name, j.enabled, s.step_id, s.step_name, s.subsystem, s.command, s.database_name
FROM msdb.dbo.sysjobs AS j
JOIN msdb.dbo.sysjobsteps AS s ON s.job_id = j.job_id
"""
Q_SCHEDULES = """
SELECT js.job_id, sc.name AS schedule_name, sc.freq_type, sc.freq_interval, sc.enabled
FROM msdb.dbo.sysjobschedules AS js
JOIN msdb.dbo.sysschedules AS sc ON sc.schedule_id = js.schedule_id
"""
Q_JOB_HISTORY = "SELECT h.job_id, h.run_date, h.run_status FROM msdb.dbo.sysjobhistory AS h WHERE h.step_id = 0"
Q_SSIS_PACKAGES = """
SELECT f.name AS folder_name, pr.name AS project_name, pk.name AS package_name, pr.last_deployed_time
FROM SSISDB.catalog.packages AS pk
JOIN SSISDB.catalog.projects AS pr ON pr.project_id = pk.project_id
JOIN SSISDB.catalog.folders AS f ON f.folder_id = pr.folder_id
"""
Q_SSIS_EXECUTIONS = """
SELECT e.folder_name, e.project_name, e.package_name, e.start_time, e.status, e.executed_as_name
FROM SSISDB.catalog.executions AS e
"""


def format_type(row: dict[str, Any]) -> str:
    t = str(row["type_name"]).lower()
    length = row.get("max_length")
    if t in CHAR_TYPES or t in NCHAR_TYPES:
        if length is None:
            return t
        if int(length) == -1:
            return f"{t}(max)"
        return f"{t}({int(length) // 2 if t in NCHAR_TYPES else int(length)})"
    if t in NUMERIC_TYPES:
        return f"{t}({row.get('precision')},{row.get('scale')})"
    if t in {"datetime2", "time", "datetimeoffset"} and row.get("scale") is not None:
        return f"{t}({row.get('scale')})"
    return t


def parse_dtsx(xml: str) -> tuple[str, dict[str, Any]]:
    """Extract SQL and task metadata from an SSIS package (no connection strings or data)."""
    parts: list[str] = []
    meta = {"execute_sql_tasks": 0, "data_flows": 0, "script_tasks": 0}
    for m in re.finditer(r'DTS:ObjectName="([^"]*)"[^>]*?DTS:ExecutableType="([^"]*)"', xml):
        kind = m.group(2)
        if "ScriptTask" in kind:
            meta["script_tasks"] += 1
            parts.append(f"-- script task: {m.group(1)} (C# code; re-engineer, MS-07)")
        elif "Pipeline" in kind:
            meta["data_flows"] += 1
            parts.append(f"-- data flow: {m.group(1)}")
    for m in re.finditer(r'SQLTask:SqlStatementSource="([^"]*)"', xml):
        meta["execute_sql_tasks"] += 1
        parts.append(html.unescape(m.group(1)).strip().rstrip(";") + ";")
    for m in re.finditer(r'<property[^>]*name="SqlCommand"[^>]*>([^<]+)</property>', xml):
        parts.append(html.unescape(m.group(1)).strip().rstrip(";") + ";")
    for m in re.finditer(r'<component[^>]*componentClassID="([^"]*)"[^>]*>(.*?)</component>', xml, re.S):
        table = re.search(r'<property[^>]*name="OpenRowset"[^>]*>([^<]+)</property>', m.group(2))
        if not table:
            continue
        name = html.unescape(table.group(1)).strip()
        if "Destination" in m.group(1) or "Destination" in m.group(2)[:200]:
            parts.append(f"INSERT INTO {name} -- data flow destination")
        else:
            parts.append(f"SELECT * FROM {name}; -- data flow source")
    return "\n".join(parts) + "\n", meta


class SqlServerHarvester(Harvester):
    source = "sqlserver"

    def default_prefix(self) -> list[str]:
        return [self.system_name, "dbo"]

    def collect(self) -> None:
        ver = self.q(Q_VERSION)[0]
        self.system_version = str(ver["product_version"])
        db = str(ver["database_name"])
        self.index.default_prefix = [db.lower(), "dbo"]
        by_sys_id: dict[int, str] = {}
        parents: dict[str, int] = {}

        for o in self.q(Q_OBJECTS):
            otype = TYPE_MAP[str(o["type_code"]).strip()]
            fq = f"{db}.{o['schema_name']}.{o['object_name']}"
            oid = self.add_object(fq, otype, created_at=o["create_date"], modified_at=o["modify_date"],
                                  source_type=o["type_desc"])
            by_sys_id[int(o["object_id"])] = oid
            if otype == "trigger" and o.get("parent_object_id"):
                parents[oid] = int(o["parent_object_id"])

        for m in self.q(Q_MODULES):
            oid = by_sys_id.get(int(m["object_id"]))
            if oid:
                self.texts[oid] = m["definition"]

        for c in self.q(Q_COLUMNS):
            self.add_column(by_sys_id.get(int(c["object_id"])), c["column_name"], c["column_id"], format_type(c),
                            bool(c["is_nullable"]), collation=c["collation_name"],
                            identity=True if c["is_identity"] else None)

        for r in self.q(Q_PARTITION_STATS):
            oid = by_sys_id.get(int(r["object_id"]))
            if oid:
                self.set_attr(oid, "row_count", int(r["row_count"] or 0))
                self.set_attr(oid, "size_bytes", int(r["reserved_pages"] or 0) * PAGE_BYTES)

        self._collect_ssis()
        self._collect_jobs()

        # Lineage: classify reads/writes/calls from module code, then add catalog edges the scanner missed.
        for oid in sorted(self.texts):
            if self.objects[oid]["object_type"] in {"view", "procedure", "function", "trigger"}:
                self.edges_from_code(oid, self.texts[oid], "code:sys.sql_modules")
        for trg, parent in parents.items():
            self.add_edge(trg, by_sys_id.get(parent), "reads", "sys.objects.parent_object_id")
        linked = {(f, t) for f, t, _ in self.edges}
        for d in self.q(Q_DEPENDENCIES):
            src = by_sys_id.get(int(d["referencing_id"]))
            tgt = by_sys_id.get(int(d["referenced_id"])) if d.get("referenced_id") is not None else None
            if tgt is None:
                parts = [p for p in (d.get("referenced_database_name"), d.get("referenced_schema_name"),
                                     d.get("referenced_entity_name")) if p]
                tgt = self.resolve(".".join(parts)) if parts else None
            if src and tgt and (src, tgt) not in linked:
                kind = "calls" if self.objects[tgt]["object_type"] in {"procedure", "function"} else "reads"
                self.add_edge(src, tgt, kind, "sys.sql_expression_dependencies")

        self._collect_usage(by_sys_id)

        for p in self.q(Q_PERMISSIONS):
            if p["state_desc"] not in ("GRANT", "GRANT_WITH_GRANT_OPTION"):
                continue
            oid = by_sys_id.get(int(p["major_id"]))
            grantee_type = "role" if "ROLE" in str(p["grantee_type"]).upper() else "user"
            self.add_grant(p["grantee"], grantee_type, p["permission_name"],
                           self.objects[oid]["fq_name"] if oid else None)

    # ------------------------------------------------------------------ usage
    def _collect_usage(self, by_sys_id: dict[int, str]) -> None:
        state = self.q(Q_QUERY_STORE_STATE)
        qs_on = bool(state) and str(state[0]["actual_state_desc"]).upper() in {"READ_WRITE", "READ_ONLY"}
        self.notes.append(f"usage source: {'query_store' if qs_on else 'plan_cache'}")
        if qs_on:
            for r in self.q(Q_QUERY_STORE):
                module = by_sys_id.get(int(r["object_id"])) if r.get("object_id") else None
                if module is None:
                    self.usage_from_query_text(r["query_sql_text"], r["start_time"], r["count_executions"])
                elif self.objects[module]["object_type"] in {"function", "view"}:
                    self.add_usage(module, r["start_time"], r["count_executions"])
        else:
            for r in self.q(Q_PLAN_CACHE):
                module = by_sys_id.get(int(r["objectid"])) if r.get("objectid") else None
                if module is None:
                    self.usage_from_query_text(r["text"], r["last_execution_time"], r["execution_count"])
                elif self.objects[module]["object_type"] in {"function", "view"}:
                    self.add_usage(module, r["last_execution_time"], r["execution_count"])
        for r in self.q(Q_PROC_STATS):
            self.add_usage(by_sys_id.get(int(r["object_id"])), r["last_execution_time"], r["execution_count"])

    # ------------------------------------------------------------------ SSIS
    def _collect_ssis(self) -> None:
        dtsx = {p.name.lower(): p for p in self.script_files() if p.suffix.lower() == ".dtsx"}
        self.packages: dict[tuple[str, str, str], str] = {}
        for p in self.q(Q_SSIS_PACKAGES):
            fq = f"SSISDB.{p['folder_name']}.{p['project_name']}.{p['package_name']}"
            text, meta = None, {}
            f = dtsx.get(str(p["package_name"]).lower())
            if f is not None:
                text, meta = parse_dtsx(f.read_text())
            oid = self.add_object(fq, "etl_job", text, tool="ssis", deployed_at=p["last_deployed_time"], **meta)
            self.packages[(p["folder_name"].lower(), p["project_name"].lower(), p["package_name"].lower())] = oid
            if text:
                self.edges_from_code(oid, text, "dtsx")
        for e in self.q(Q_SSIS_EXECUTIONS):
            oid = self.packages.get((str(e["folder_name"]).lower(), str(e["project_name"]).lower(),
                                     str(e["package_name"]).lower()))
            self.add_usage(oid, e["start_time"], 1, e.get("executed_as_name"))

    # ------------------------------------------------------------------ SQL Agent
    def _collect_jobs(self) -> None:
        jobs: dict[str, dict[str, Any]] = {}
        for r in sorted(self.q(Q_JOBS), key=lambda r: (str(r["job_name"]), int(r["step_id"]))):
            j = jobs.setdefault(str(r["job_id"]), {"name": r["job_name"], "enabled": r["enabled"], "steps": []})
            j["steps"].append(r)
        job_oid: dict[str, str] = {}
        for jid, j in sorted(jobs.items(), key=lambda kv: kv[1]["name"]):
            lines = []
            for s in j["steps"]:
                lines.append(f"-- step {s['step_id']}: {s['step_name']} ({s['subsystem']})")
                lines.append(str(s["command"]).strip())
            oid = self.add_object(f"msdb.job.{j['name']}", "schedule", "\n".join(lines) + "\n",
                                  enabled=bool(j["enabled"]), scheduler="sql_agent")
            job_oid[jid] = oid
            for s in j["steps"]:
                cmd = str(s["command"])
                if str(s["subsystem"]).upper() == "SSIS":
                    for m in _SSIS_PATH.finditer(cmd):
                        target = self.packages.get(tuple(x.lower() for x in m.groups()))
                        self.add_edge(oid, target, "schedules", "msdb.dbo.sysjobsteps")
                    continue
                for kind, names in code_refs(cmd).by_kind().items():
                    for name in sorted(names):
                        target = self.resolve(name)
                        if target is None:
                            continue
                        if self.objects[target]["object_type"] in {"procedure", "function", "etl_job"}:
                            self.add_edge(oid, target, "schedules", "msdb.dbo.sysjobsteps")
                        else:
                            self.add_edge(oid, target, kind, "msdb.dbo.sysjobsteps")
        freqs: dict[str, set[str]] = {}
        for s in self.q(Q_SCHEDULES):
            if not s["enabled"]:
                continue
            oid = job_oid.get(str(s["job_id"]))
            if oid:
                freqs.setdefault(oid, set()).add(FREQ_TYPES.get(int(s["freq_type"]), "other"))
        for oid, f in freqs.items():
            self.set_attr(oid, "schedule_frequency", ",".join(sorted(f)))
        for h in self.q(Q_JOB_HISTORY):
            self.add_usage(job_oid.get(str(h["job_id"])), h["run_date"], 1)
