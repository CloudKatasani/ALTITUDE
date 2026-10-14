"""Teradata harvester (Section 10.1).

Reads ``DBC.TablesV`` (RequestText carries view/macro/procedure DDL),
``DBC.ColumnsV`` (CASESPECIFIC and CHAR padding attributes — TD-02/TD-03),
``DBC.TableSizeV``, DBQL (``DBC.QryLogV``/``DBC.QryLogObjectsV``) and
``DBC.AccessRightsV``; BTEQ scripts are read from the client's repository with
``.LOGON`` credentials redacted before anything leaves the boundary.
"""

from __future__ import annotations

import re
from typing import Any

from .base import Harvester

SYSTEM_DATABASES = ("DBC", "SYSLIB", "SYSUDTLIB", "SYSSPATIAL", "SYSBAR", "SYSJDBC", "SYSXML", "TD_SYSFNLIB",
                    "TDSTATS", "TDQCD", "TDWM", "SYSTEMFE", "SYSADMIN", "SQLJ", "LOCKLOGSHREDDER", "TD_SYSXML",
                    "TDMAPS", "TD_SERVER_DB", "DBCMNGR", "CRASHDUMPS", "PUBLIC", "ALL", "DEFAULT", "EXTUSER")
_DBS = ", ".join(f"'{d}'" for d in SYSTEM_DATABASES)
KIND_MAP = {"T": "table", "O": "table", "Q": "table", "V": "view", "P": "procedure", "E": "procedure",
            "M": "macro", "F": "function", "R": "function", "G": "trigger"}
COLUMN_TYPES = {"CV": "VARCHAR", "CF": "CHAR", "I": "INTEGER", "I1": "BYTEINT", "I2": "SMALLINT", "I8": "BIGINT",
                "D": "DECIMAL", "DA": "DATE", "TS": "TIMESTAMP", "SZ": "TIMESTAMP WITH TIME ZONE", "AT": "TIME",
                "F": "FLOAT", "CO": "CLOB", "BO": "BLOB", "BV": "VARBYTE", "JN": "JSON", "XM": "XML",
                "PD": "PERIOD(DATE)", "PS": "PERIOD(TIMESTAMP)"}
ACCESS_RIGHTS = {"R": "SELECT", "I": "INSERT", "U": "UPDATE", "D": "DELETE", "E": "EXECUTE", "PE": "EXECUTE",
                 "EF": "EXECUTE", "CT": "CREATE TABLE", "CV": "CREATE VIEW", "DT": "DROP TABLE", "IX": "INDEX",
                 "ST": "STATISTICS", "DP": "DUMP", "RS": "RESTORE"}
_SCRIPT_BAND = re.compile(r"ScriptName\s*=\s*([^;]+);", re.IGNORECASE)
_LOGON = re.compile(r"^(\s*\.LOGON\s+).*$", re.IGNORECASE | re.MULTILINE)
_TABLE_KIND = re.compile(r"CREATE\s+(SET|MULTISET)\s+(?:GLOBAL\s+TEMPORARY\s+|VOLATILE\s+)?TABLE", re.IGNORECASE)

Q_VERSION = "SELECT InfoKey, InfoData FROM DBC.DBCInfoV"
Q_TABLES = f"""
SELECT DatabaseName, TableName, TableKind, CreateTimeStamp, LastAlterTimeStamp, RequestText, CommentString
FROM DBC.TablesV
WHERE DatabaseName NOT IN ({_DBS})
"""
Q_COLUMNS = f"""
SELECT DatabaseName, TableName, ColumnName, ColumnId, ColumnType, ColumnLength, DecimalTotalDigits,
       DecimalFractionalDigits, Nullable, UpperCaseFlag, CharType
FROM DBC.ColumnsV
WHERE DatabaseName NOT IN ({_DBS})
"""
Q_SIZES = f"""
SELECT DatabaseName, TableName, SUM(CurrentPerm) AS CurrentPerm
FROM DBC.TableSizeV
WHERE DatabaseName NOT IN ({_DBS})
GROUP BY DatabaseName, TableName
"""
Q_OBJECT_USAGE = """
SELECT o.ObjectDatabaseName, o.ObjectTableName, q.UserName, CAST(q.StartTime AS DATE) AS QueryDate,
       COUNT(*) AS QueryCount
FROM DBC.QryLogObjectsV AS o
JOIN DBC.QryLogV AS q ON q.QueryID = o.QueryID
WHERE o.ObjectTableName IS NOT NULL
GROUP BY o.ObjectDatabaseName, o.ObjectTableName, q.UserName, CAST(q.StartTime AS DATE)
"""
Q_SCRIPT_USAGE = """
SELECT q.QueryBand, q.UserName, CAST(q.StartTime AS DATE) AS QueryDate, COUNT(*) AS QueryCount
FROM DBC.QryLogV AS q
WHERE q.QueryBand IS NOT NULL
GROUP BY q.QueryBand, q.UserName, CAST(q.StartTime AS DATE)
"""
Q_RIGHTS = f"""
SELECT UserName, DatabaseName, TableName, AccessRight
FROM DBC.AccessRightsV
WHERE DatabaseName NOT IN ({_DBS})
"""


def format_type(c: dict[str, Any]) -> str:
    code = str(c["columntype"]).strip()
    base = COLUMN_TYPES.get(code, code)
    if code in {"CV", "CF", "BV"}:
        return f"{base}({c['columnlength']})"
    if code == "D":
        return f"{base}({c['decimaltotaldigits']},{c['decimalfractionaldigits']})"
    return base


def redact_bteq(text: str) -> str:
    """Remove credentials from BTEQ ``.LOGON`` lines before the script is shipped."""
    return _LOGON.sub(lambda m: m.group(1) + "<redacted>;", text)


class TeradataHarvester(Harvester):
    source = "teradata"

    def collect(self) -> None:
        info = {r["infokey"]: r["infodata"] for r in self.q(Q_VERSION)}
        self.system_version = info.get("VERSION") or info.get("RELEASE")
        key: dict[tuple[str, str], str] = {}
        for t in self.q(Q_TABLES):
            otype = KIND_MAP.get(str(t["tablekind"]).strip())
            if otype is None:
                continue
            fq = f"{t['databasename'].strip()}.{t['tablename'].strip()}"
            text = t.get("requesttext")
            oid = self.add_object(fq, otype, text if otype != "table" else None,
                                  created_at=t["createtimestamp"], modified_at=t["lastaltertimestamp"])
            key[(t["databasename"].strip().upper(), t["tablename"].strip().upper())] = oid
            if otype == "table" and text:
                m = _TABLE_KIND.search(text)
                if m:
                    self.set_attr(oid, "table_kind", m.group(1).upper())
                if re.search(r"\bVOLATILE\b|\bGLOBAL\s+TEMPORARY\b", text, re.IGNORECASE):
                    self.set_attr(oid, "temporary", True)
                pi = re.search(r"(UNIQUE\s+)?PRIMARY\s+INDEX\s*\(([^)]*)\)", text, re.IGNORECASE)
                if pi:
                    self.set_attr(oid, "primary_index", pi.group(2).strip())

        for c in self.q(Q_COLUMNS):
            oid = key.get((c["databasename"].strip().upper(), c["tablename"].strip().upper()))
            code = str(c["columntype"]).strip()
            flag = str(c.get("uppercaseflag") or "").strip()
            char = code in {"CV", "CF"}
            self.add_column(oid, c["columnname"].strip(), c["columnid"], format_type(c), c["nullable"] == "Y",
                            casespecific=(flag in {"C", "B"}) if char else None,
                            char_padded=True if code == "CF" else None)

        for s in self.q(Q_SIZES):
            oid = key.get((s["databasename"].strip().upper(), s["tablename"].strip().upper()))
            if oid:
                self.set_attr(oid, "size_bytes", int(s["currentperm"] or 0))

        scripts: dict[str, str] = {}
        for path in self.script_files():
            base = next(d for d in self.script_dirs if path.is_relative_to(d))
            rel = path.relative_to(base).as_posix()
            text = redact_bteq(path.read_text())
            oid = self.add_object(f"bteq:{rel}", "script", text, script_kind="bteq")
            scripts[path.name.lower()] = oid
            controls = len(re.findall(r"^\s*\.(IF|GOTO|LABEL)\b", text, re.IGNORECASE | re.MULTILINE))
            self.set_attr(oid, "bteq_control_statements", controls)

        for oid in sorted(self.texts):
            self.edges_from_code(oid, self.texts[oid], "code:DBC.TablesV.RequestText"
                                 if not self.objects[oid]["fq_name"].startswith("bteq:") else "bteq")

        for u in self.q(Q_OBJECT_USAGE):
            oid = key.get((str(u["objectdatabasename"]).strip().upper(), str(u["objecttablename"]).strip().upper()))
            self.add_usage(oid, u["querydate"], int(u["querycount"]), u["username"])
        for u in self.q(Q_SCRIPT_USAGE):
            m = _SCRIPT_BAND.search(str(u["queryband"]))
            if m:
                self.add_usage(scripts.get(m.group(1).strip().lower()), u["querydate"], int(u["querycount"]),
                               u["username"])

        for r in self.q(Q_RIGHTS):
            right = ACCESS_RIGHTS.get(str(r["accessright"]).strip())
            if right is None:
                continue
            table = str(r["tablename"]).strip()
            obj = f"{r['databasename'].strip()}.{table}" if table.upper() != "ALL" else f"{r['databasename'].strip()}.*"
            self.add_grant(r["username"].strip(), "user", right, obj)
