"""Legacy grants -> Snowflake RBAC (Section 14.2).

Role model:

- **access roles** hold object privileges, one per (database, schema, privilege set):
  ``AR_<DB>_<SCHEMA>_<RO|RW|EXEC>`` with ALL + FUTURE grants in the schema;
- **functional roles** represent a job function, one per grantee group: ``FR_<GROUP>``; they inherit access
  roles and roll up to ``SYSADMIN``;
- users only ever receive functional roles — never object privileges.

Legacy grants that cannot or should not be carried over (system/DDL/ownership privileges, grants on objects
dispositioned ``retire``, grantees the caller retires) are marked ``intentionally_retired``. When the grants
come from the canonical ``grant`` table, every row is updated with its mapping (``mapping_status`` =
``mapped`` | ``retired``; ``mapped_to`` = access role | ``intentionally_retired``).
"""

from __future__ import annotations

import fnmatch
import re
from collections import defaultdict
from typing import Any

from .context import coerce
from .impl_common import out_dir, safe
from .registry import SkillError

RETIRED = "intentionally_retired"

#: legacy privilege -> access level (privilege sets are fixed by Section 14.2, not tunable thresholds)
PRIVILEGE_LEVEL = {
    "SELECT": "RO", "READ": "RO", "REFERENCES": "RO",
    "INSERT": "RW", "UPDATE": "RW", "DELETE": "RW", "TRUNCATE": "RW", "MERGE": "RW", "WRITE": "RW",
    "EXECUTE": "EXEC", "EXEC": "EXEC", "USAGE": "EXEC",
}
LEVEL_ORDER = ["RO", "RW", "EXEC"]
LEVEL_PRIVILEGES = {
    "RO": [("SELECT", "TABLES"), ("SELECT", "VIEWS"), ("SELECT", "MATERIALIZED VIEWS"), ("REFERENCES", "TABLES")],
    "RW": [("SELECT", "TABLES"), ("SELECT", "VIEWS"), ("INSERT", "TABLES"), ("UPDATE", "TABLES"),
           ("DELETE", "TABLES"), ("TRUNCATE", "TABLES")],
    "EXEC": [("USAGE", "PROCEDURES"), ("USAGE", "FUNCTIONS")],
}
_IDENT = re.compile(r"[^A-Z0-9_]+")


def _ident(s: str) -> str:
    out = _IDENT.sub("_", str(s).upper()).strip("_")
    return out or "UNNAMED"


def _parse_object(fq: str | None, default_db: str | None, db_map: dict[str, str]) -> tuple[str, str, str] | None:
    """(database, schema, object) — object ``*`` for schema-wide grants; None for system-level grants."""
    if not fq:
        return None
    parts = [p.strip().strip('"[]') for p in str(fq).split(".")]
    if len(parts) == 1:  # a bare database/schema name: schema-wide grant
        parts.append("*")
    db, schema, obj = ([None, None] + parts)[-3:]
    if db is None:
        if not default_db:
            raise SkillError(f"object {fq!r} has no database part; pass 'database' for the target database")
        db = default_db
    db = db_map.get(db, db_map.get(db.upper(), db))
    return _ident(db), _ident(schema), obj


def _retired_objects(ctx: Any, source_system_id: str) -> set[str]:
    """Lower-cased fq names of this system's objects whose latest assessed disposition is ``retire``."""
    rows = ctx.store.query(
        "SELECT o.fq_name, d.disposition FROM source_object o JOIN object_disposition d USING (object_id) "
        "WHERE o.source_system_id = ? ORDER BY d.snapshot_id", [source_system_id])
    latest: dict[str, str] = {}
    for r in rows:
        latest[r["fq_name"].lower()] = r["disposition"]
    return {k for k, v in latest.items() if v == "retire"}


def _matches(value: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(value.lower(), p.lower()) for p in patterns)


def _sql(access: dict[str, dict], functional: dict[str, dict], users: list[dict], source: str) -> str:
    out = [f"-- Snowflake RBAC generated from legacy grants ({source}); Section 14.2 role model.",
           "-- Access roles hold object privileges; functional roles inherit access roles; users get functional",
           "-- roles only. Review before applying; apply with SECURITYADMIN.",
           "USE ROLE SECURITYADMIN;", ""]
    for name in sorted(access):
        out.append(f"CREATE ROLE IF NOT EXISTS {name} COMMENT = 'access role: {access[name]['database']}."
                   f"{access[name]['schema']} {access[name]['level']}';")
    for name in sorted(functional):
        out.append(f"CREATE ROLE IF NOT EXISTS {name} COMMENT = 'functional role: {functional[name]['group']}';")
    out.append("")
    for name in sorted(access):
        a = access[name]
        db, sch = a["database"], f"{a['database']}.{a['schema']}"
        out += [f"-- {name}", f"GRANT USAGE ON DATABASE {db} TO ROLE {name};",
                f"GRANT USAGE ON SCHEMA {sch} TO ROLE {name};"]
        for priv, kind in LEVEL_PRIVILEGES[a["level"]]:
            out.append(f"GRANT {priv} ON ALL {kind} IN SCHEMA {sch} TO ROLE {name};")
            out.append(f"GRANT {priv} ON FUTURE {kind} IN SCHEMA {sch} TO ROLE {name};")
        out.append("")
    for name in sorted(functional):
        for ar in functional[name]["access_roles"]:
            out.append(f"GRANT ROLE {ar} TO ROLE {name};")
        out.append(f"GRANT ROLE {name} TO ROLE SYSADMIN;")
    if users:
        out.append("")
        out.append("-- user assignments (functional roles only; prefer SCIM-provisioned group membership)")
        for u in users:
            out.append(f'GRANT ROLE {u["role"]} TO USER "{u["user"]}";')
    return "\n".join(out).rstrip() + "\n"


def generate_rbac_from_legacy_grants(context: Any = None, source_system_id: str | None = None,
                                     grants: list | None = None, database: str | None = None,
                                     database_map: dict | None = None, grantee_groups: dict | None = None,
                                     retire_grantees: list | None = None, retire_objects: list | None = None,
                                     persist: bool = True) -> dict:
    """Map legacy grants to a Snowflake access-role / functional-role model and generate the SQL."""
    from altitude.core.ids import stable_id

    ctx = coerce(context)
    db_map = {str(k): str(v) for k, v in (database_map or {}).items()}
    groups = {str(k).lower(): str(v) for k, v in (grantee_groups or {}).items()}
    retire_grantees, retire_objects = list(retire_grantees or []), list(retire_objects or [])
    disposition_retired: set[str] = set()
    if source_system_id:
        system = ctx.store.get("source_system", source_system_id=source_system_id)
        if system is None:
            raise SkillError(f"unknown source system {source_system_id!r}")
        rows = ctx.store.query('SELECT grant_id, grantee, grantee_type, privilege, object_fq_name FROM "grant" '
                               "WHERE source_system_id = ? ORDER BY grant_id", [source_system_id])
        legacy = [{"grant_id": r["grant_id"], "grantee": r["grantee"], "grantee_type": r["grantee_type"],
                   "privilege": r["privilege"], "object": r["object_fq_name"]} for r in rows]
        default_db = database or system["name"]
        disposition_retired = _retired_objects(ctx, source_system_id)
        source = f"source_system {source_system_id} ({system['dialect']} {system['name']})"
    elif grants:
        legacy = [{"grant_id": stable_id("GRT", "input", str(g["grantee"]).lower(), str(g["privilege"]).upper(),
                                         str(g.get("object") or "").lower()), **g} for g in grants]
        default_db = database
        source = "input grant list"
    else:
        raise SkillError("one of source_system_id or grants is required")

    access: dict[str, dict] = {}
    functional: dict[str, dict] = {}
    user_roles: set[tuple[str, str]] = set()
    decisions: list[dict] = []
    for g in legacy:
        grantee, gtype = str(g["grantee"]), str(g.get("grantee_type") or "user").lower()
        priv = str(g["privilege"]).upper().strip()
        obj = g.get("object")
        reason = None
        level = PRIVILEGE_LEVEL.get(priv)
        if _matches(grantee, retire_grantees):
            reason = "grantee retired by the caller"
        elif obj is None:
            reason = "system-level privilege: administration is held by SYSADMIN/SECURITYADMIN, not migrated"
        elif level is None:
            reason = f"{priv} is a DDL/ownership privilege: owned by deployment roles, not granted to job functions"
        elif str(obj).lower() in disposition_retired or _matches(str(obj), retire_objects):
            reason = "object is dispositioned retire: it will not exist in Snowflake"
        parsed = None if reason else _parse_object(obj, default_db, db_map)
        if reason or parsed is None:
            decisions.append({**g, "status": "retired", "mapped_to": RETIRED, "reason": reason})
            continue
        db, schema, objname = parsed
        ar = f"AR_{db}_{schema}_{level}"
        group = groups.get(grantee.lower(), grantee)
        fr = f"FR_{_ident(group)}"
        a = access.setdefault(ar, {"name": ar, "database": db, "schema": schema, "level": level,
                                   "privileges": [f"{p} ON ALL/FUTURE {k}" for p, k in LEVEL_PRIVILEGES[level]],
                                   "legacy_objects": set(), "legacy_privileges": set(), "granted_to": set()})
        a["legacy_objects"].add(str(obj))
        a["legacy_privileges"].add(priv)
        a["granted_to"].add(fr)
        f = functional.setdefault(fr, {"name": fr, "group": group, "grantees": set(), "access_roles": set()})
        f["grantees"].add((grantee, gtype))
        f["access_roles"].add(ar)
        if gtype == "user":
            user_roles.add((grantee, fr))
        decisions.append({**g, "status": "mapped", "mapped_to": ar, "functional_role": fr, "reason": None})

    for a in access.values():
        a["schema_wide"] = "*" in {o.split(".")[-1] for o in a["legacy_objects"]}
        for k in ("legacy_objects", "legacy_privileges", "granted_to"):
            a[k] = sorted(a[k])
    for f in functional.values():
        f["grantees"] = [{"grantee": n, "grantee_type": t} for n, t in sorted(f["grantees"])]
        f["access_roles"] = sorted(f["access_roles"], key=lambda r: (r.rsplit("_", 1)[0], LEVEL_ORDER.index(
            r.rsplit("_", 1)[1])))
    users = [{"user": u, "role": r} for u, r in sorted(user_roles)]
    sql = _sql(access, functional, users, source)

    widened = [{"access_role": a["name"], "legacy_objects": a["legacy_objects"]}
               for a in access.values() if not a["schema_wide"]]
    persisted = False
    if source_system_id and persist:
        for d in decisions:
            ctx.store.update("grant", {"grant_id": d["grant_id"]},
                             {"mapped_to": d["mapped_to"], "mapping_status": d["status"]})
        persisted = True

    key = source_system_id or stable_id("RBAC", sorted(d["grant_id"] for d in decisions))
    path = out_dir(ctx, "generate_rbac_from_legacy_grants") / f"{key}.sql"
    path.write_text(sql)
    by_status: dict[str, list[str]] = defaultdict(list)
    for d in decisions:
        by_status[d["status"]].append(d["grant_id"])
    return safe({
        "source": source, "grants": len(decisions), "mapped": len(by_status["mapped"]),
        "retired": len(by_status["retired"]),
        "role_model": {"access_roles": sorted(access.values(), key=lambda a: a["name"]),
                       "functional_roles": sorted(functional.values(), key=lambda f: f["name"]),
                       "user_assignments": users,
                       "hierarchy": "access roles -> functional roles -> SYSADMIN; users receive functional roles only",
                       "direct_user_object_grants": 0},
        "grant_mappings": [{k: d.get(k) for k in ("grant_id", "grantee", "grantee_type", "privilege", "object",
                                                  "status", "mapped_to", "functional_role", "reason")}
                           for d in decisions],
        "review_notes": [f"{w['access_role']} grants schema-wide access; legacy grants covered only "
                         f"{len(w['legacy_objects'])} object(s): {', '.join(w['legacy_objects'][:5])}"
                         for w in widened],
        "sql": sql, "sql_path": str(path), "persisted": persisted,
    })
