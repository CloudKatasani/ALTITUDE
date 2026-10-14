"""Terraform landing-zone generator (Section 15.2): YAML role/warehouse model -> Snowflake provider HCL.

The renderer is deterministic (sorted, no timestamps) so ``altitude generate --check`` can detect drift.
Resource names follow ``<type>.<lower_snake(identifier)>``; every cross-resource reference is an HCL
expression (``snowflake_database.prod_sales_raw.name``) so Terraform orders creation correctly and the
structural linter (:mod:`altitude.foundation.tflint`) can verify that every reference is defined.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Union

from .landing_zone import LandingZone


class Expr(str):
    """A raw HCL expression (reference, function call) — emitted unquoted."""


@dataclass
class Block:
    kind: str
    labels: tuple[str, ...] = ()
    body: list[Union[tuple[str, Any], "Block"]] = field(default_factory=list)

    def attr(self, key: str, value: Any) -> "Block":
        self.body.append((key, value))
        return self

    def block(self, kind: str, *labels: str) -> "Block":
        b = Block(kind, labels)
        self.body.append(b)
        return b


def _value(v: Any) -> str:
    if isinstance(v, Expr):
        return str(v)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {_value(x)}" for k, x in v.items()) + " }"
    raise TypeError(f"cannot render {v!r} as HCL")


def render(block: Block, indent: int = 0) -> str:
    pad = "  " * indent
    head = " ".join([block.kind, *(json.dumps(label) for label in block.labels)])
    lines = [f"{pad}{head} {{"]
    attrs = [x for x in block.body if isinstance(x, tuple)]
    width = max((len(k) for k, _ in attrs), default=0)
    for item in block.body:
        if isinstance(item, Block):
            lines.append(render(item, indent + 1))
        else:
            k, v = item
            lines.append(f"{pad}  {k.ljust(width)} = {_value(v)}")
    lines.append(f"{pad}}}")
    return "\n".join(lines)


def tf_name(identifier: str) -> str:
    return identifier.lower().replace(".", "_").replace("-", "_").replace(" ", "_")


def ref(rtype: str, identifier: str, attr: str = "name") -> Expr:
    return Expr(f"{rtype}.{tf_name(identifier)}.{attr}")


class Module:
    def __init__(self) -> None:
        self.files: dict[str, list[Block]] = {}

    def resource(self, file: str, rtype: str, identifier: str, suffix: str = "") -> Block:
        b = Block("resource", (rtype, tf_name(identifier) + (f"_{suffix}" if suffix else "")))
        self.files.setdefault(file, []).append(b)
        return b

    def add(self, file: str, block: Block) -> Block:
        self.files.setdefault(file, []).append(block)
        return block

    def rendered(self) -> dict[str, str]:
        return {f: "\n\n".join(render(b) for b in blocks) + "\n" for f, blocks in sorted(self.files.items())}


# --------------------------------------------------------------------------- builders
def _providers(m: Module, lz: LandingZone) -> None:
    tf = m.add("providers.tf", Block("terraform"))
    tf.attr("required_version", ">= 1.6")
    rp = tf.block("required_providers")
    rp.attr("snowflake", {"source": lz["provider"]["source"], "version": lz["provider"]["version"]})
    p = m.add("providers.tf", Block("provider", ("snowflake",)))
    p.attr("organization_name", Expr("var.organization_name"))
    p.attr("account_name", Expr("var.account_name"))
    p.attr("user", Expr("var.terraform_user"))
    p.attr("role", Expr("var.terraform_role"))
    p.attr("authenticator", "SNOWFLAKE_JWT")
    p.attr("private_key", Expr("var.private_key"))
    p.attr("preview_features_enabled", ["snowflake_network_rule_resource", "snowflake_execute_resource",
                                        "snowflake_tag_association_resource",
                                        "snowflake_tag_masking_policy_association_resource"])
    for name, desc, sensitive in (("organization_name", "Snowflake organization name", False),
                                  ("account_name", "Snowflake account name", False),
                                  ("terraform_user", "Service user Terraform authenticates as", False),
                                  ("terraform_role", "Role Terraform uses (needs SYSADMIN + SECURITYADMIN rights)", False),
                                  ("private_key", "PEM private key for the Terraform service user", True)):
        v = m.add("variables.tf", Block("variable", (name,)))
        v.attr("type", Expr("string"))
        v.attr("description", desc)
        if sensitive:
            v.attr("sensitive", True)
    v = m.add("variables.tf", Block("variable", ("service_user_public_keys",)))
    v.attr("type", Expr("map(string)"))
    v.attr("description", "RSA public keys per service user (key-pair auth; no passwords for services)")
    v.attr("default", {})


def _databases(m: Module, lz: LandingZone) -> None:
    gov = lz["governance"]
    g = m.resource("databases.tf", "snowflake_database", gov["database"])
    g.attr("name", gov["database"]).attr("comment", "Platform governance: tags, policies, network rules")
    for schema in sorted({gov["tag_schema"], gov["policy_schema"], lz["network"]["schema"]}):
        s = m.resource("databases.tf", "snowflake_schema", f"{gov['database']}_{schema}")
        s.attr("database", ref("snowflake_database", gov["database"])).attr("name", schema)
        s.attr("with_managed_access", "true")
    for db in lz.databases:
        d = m.resource("databases.tf", "snowflake_database", db.name)
        d.attr("name", db.name)
        d.attr("data_retention_time_in_days", db.retention_days)
        d.attr("comment", f"{db.env} {db.domain} {db.layer} layer; owner {db.owner}")
        for schema in lz["schemas"]:
            s = m.resource("databases.tf", "snowflake_schema", f"{db.name}_{schema}")
            s.attr("database", ref("snowflake_database", db.name)).attr("name", schema)
            s.attr("with_managed_access", "true" if db.managed_access else "false")
            if schema == "STAGING":
                s.attr("is_transient", "true")
                s.attr("data_retention_time_in_days", 0)


def _roles(m: Module, lz: LandingZone) -> None:
    levels = lz["access_levels"]
    for role, (db, level) in lz.access_roles.items():
        r = m.resource("roles.tf", "snowflake_account_role", role)
        r.attr("name", role).attr("comment", f"Access role: {level} on {db}")
        g = m.resource("grants.tf", "snowflake_grant_privileges_to_account_role", role, "db")
        g.attr("account_role_name", ref("snowflake_account_role", role))
        g.attr("privileges", levels[level]["database"])
        g.block("on_account_object").attr("object_type", "DATABASE").attr("object_name", ref("snowflake_database", db))
        s = m.resource("grants.tf", "snowflake_grant_privileges_to_account_role", role, "schemas")
        s.attr("account_role_name", ref("snowflake_account_role", role))
        s.attr("privileges", levels[level]["schema"])
        s.block("on_schema").attr("all_schemas_in_database", ref("snowflake_database", db))
        fs = m.resource("grants.tf", "snowflake_grant_privileges_to_account_role", role, "future_schemas")
        fs.attr("account_role_name", ref("snowflake_account_role", role))
        fs.attr("privileges", levels[level]["schema"])
        fs.block("on_schema").attr("future_schemas_in_database", ref("snowflake_database", db))
        for plural, privs in sorted(levels[level]["future_objects"].items()):
            f = m.resource("grants.tf", "snowflake_grant_privileges_to_account_role", role,
                           "future_" + tf_name(plural))
            f.attr("account_role_name", ref("snowflake_account_role", role))
            f.attr("privileges", privs)
            fut = f.block("on_schema_object").block("future")
            fut.attr("object_type_plural", plural).attr("in_database", ref("snowflake_database", db))
        if level == "RW":   # RW inherits RO
            h = m.resource("roles.tf", "snowflake_grant_account_role", role, "inherits_ro")
            h.attr("role_name", ref("snowflake_account_role", lz.access_role(db, "RO")))
            h.attr("parent_role_name", ref("snowflake_account_role", role))
    gov_admin = lz["governance"]["admin_role"]
    for fr in [*lz["functional_roles"], {"name": gov_admin, "description": "Owns tags, masking and network policies",
                                          "warehouses": []}]:
        r = m.resource("roles.tf", "snowflake_account_role", fr["name"])
        r.attr("name", fr["name"]).attr("comment", f"Functional role: {fr['description']}")
        to_sys = m.resource("roles.tf", "snowflake_grant_account_role", fr["name"], "to_sysadmin")
        to_sys.attr("role_name", ref("snowflake_account_role", fr["name"])).attr("parent_role_name", "SYSADMIN")
        for ar in lz.functional_access.get(fr["name"], []):
            g = m.resource("roles.tf", "snowflake_grant_account_role", f"{ar}_to_{fr['name']}")
            g.attr("role_name", ref("snowflake_account_role", ar))
            g.attr("parent_role_name", ref("snowflake_account_role", fr["name"]))
        for wh in fr["warehouses"]:
            w = m.resource("grants.tf", "snowflake_grant_privileges_to_account_role", f"{fr['name']}_{wh}", "usage")
            w.attr("account_role_name", ref("snowflake_account_role", fr["name"]))
            w.attr("privileges", ["USAGE"])
            w.block("on_account_object").attr("object_type", "WAREHOUSE").attr("object_name", ref("snowflake_warehouse", wh))


def _warehouses(m: Module, lz: LandingZone) -> None:
    for w in lz.warehouses:
        mon = w["monitor"]
        rm_name = mon.get("name", f"RM_{w['name']}")
        rm = m.resource("warehouses.tf", "snowflake_resource_monitor", rm_name)
        rm.attr("name", rm_name).attr("credit_quota", mon["credit_quota"]).attr("frequency", mon["frequency"])
        rm.attr("start_timestamp", "IMMEDIATELY").attr("notify_triggers", mon["notify_at"])
        rm.attr("suspend_trigger", mon["suspend_at"])
        r = m.resource("warehouses.tf", "snowflake_warehouse", w["name"])
        r.attr("name", w["name"]).attr("warehouse_size", w["size"]).attr("auto_suspend", w["auto_suspend"])
        r.attr("auto_resume", "true").attr("initially_suspended", True)
        r.attr("min_cluster_count", w["min_clusters"]).attr("max_cluster_count", w["max_clusters"])
        r.attr("scaling_policy", w["scaling_policy"])
        r.attr("statement_timeout_in_seconds", w["statement_timeout_seconds"])
        r.attr("resource_monitor", ref("snowflake_resource_monitor", rm_name))
        r.attr("comment", f"workload_class={w['workload_class']}")
        t = m.resource("governance.tf", "snowflake_tag_association", f"{w['name']}_cost_center")
        t.attr("object_identifiers", [ref("snowflake_warehouse", w["name"], "fully_qualified_name")])
        t.attr("object_type", "WAREHOUSE")
        t.attr("tag_id", ref("snowflake_tag", "COST_CENTER", "fully_qualified_name"))
        t.attr("tag_value", w["cost_center"])
    am = lz["account_monitor"]
    rm = m.resource("warehouses.tf", "snowflake_resource_monitor", am["name"])
    rm.attr("name", am["name"]).attr("credit_quota", am["credit_quota"]).attr("frequency", am["frequency"])
    rm.attr("start_timestamp", "IMMEDIATELY").attr("notify_triggers", am["notify_at"])
    rm.attr("suspend_trigger", am["suspend_at"])
    x = m.resource("warehouses.tf", "snowflake_execute", am["name"], "account_level")
    x.attr("execute", f"ALTER ACCOUNT SET RESOURCE_MONITOR = {am['name']}")
    x.attr("revert", "ALTER ACCOUNT UNSET RESOURCE_MONITOR")
    x.attr("depends_on", [Expr(f"snowflake_resource_monitor.{tf_name(am['name'])}")])


def _network(m: Module, lz: LandingZone) -> None:
    net = lz["network"]
    schema_id = f"{net['database']}_{net['schema']}"
    for r in net["rules"]:
        b = m.resource("network.tf", "snowflake_network_rule", r["name"])
        b.attr("name", r["name"]).attr("database", ref("snowflake_database", net["database"]))
        b.attr("schema", ref("snowflake_schema", schema_id)).attr("type", r["type"]).attr("mode", r["mode"])
        b.attr("value_list", r["values"])
    for p in net["policies"]:
        b = m.resource("network.tf", "snowflake_network_policy", p["name"])
        b.attr("name", p["name"])
        b.attr("allowed_network_rule_list", [ref("snowflake_network_rule", r, "fully_qualified_name")
                                             for r in p["allowed_rules"]])
        if p["account_default"]:
            a = m.resource("network.tf", "snowflake_account_parameter", "network_policy")
            a.attr("key", "NETWORK_POLICY").attr("value", ref("snowflake_network_policy", p["name"]))


def _governance(m: Module, lz: LandingZone) -> None:
    gov = lz["governance"]
    for t in gov["tags"]:
        b = m.resource("governance.tf", "snowflake_tag", t["name"])
        b.attr("name", t["name"]).attr("database", ref("snowflake_database", gov["database"]))
        b.attr("schema", ref("snowflake_schema", f"{gov['database']}_{gov['tag_schema']}"))
        if t.get("allowed_values"):
            b.attr("allowed_values", t["allowed_values"])
    for mp in gov["masking"]:
        roles = " OR ".join(f"IS_ROLE_IN_SESSION('{r}')" for r in mp["unmasked_roles"])
        masked = "'" + mp["masked_value"].replace("'", "''") + "'" if mp["data_type"] == "VARCHAR" else "NULL"
        b = m.resource("governance.tf", "snowflake_masking_policy", mp["name"])
        b.attr("name", mp["name"]).attr("database", ref("snowflake_database", gov["database"]))
        b.attr("schema", ref("snowflake_schema", f"{gov['database']}_{gov['policy_schema']}"))
        arg = b.block("argument")
        arg.attr("name", "VAL").attr("type", mp["data_type"])
        b.attr("return_data_type", mp["data_type"])
        b.attr("body", f"CASE WHEN {roles} THEN VAL ELSE {masked} END")
        b.attr("comment", f"Tag-based masking: every column tagged {mp['tag']} is masked mechanically")
        a = m.resource("governance.tf", "snowflake_tag_masking_policy_association", f"{mp['tag']}_{mp['name']}")
        a.attr("tag_id", ref("snowflake_tag", mp["tag"], "fully_qualified_name"))
        a.attr("masking_policy_id", ref("snowflake_masking_policy", mp["name"], "fully_qualified_name"))
    for fr in [gov["admin_role"]]:
        for kind, obj in (("SCHEMA", f"{gov['database']}_{gov['tag_schema']}"),
                          ("SCHEMA", f"{gov['database']}_{gov['policy_schema']}")):
            g = m.resource("grants.tf", "snowflake_grant_privileges_to_account_role", f"{fr}_{obj}", "admin")
            g.attr("account_role_name", ref("snowflake_account_role", fr))
            g.attr("privileges", ["USAGE", "CREATE TAG", "CREATE MASKING POLICY", "CREATE ROW ACCESS POLICY"])
            g.block("on_schema").attr("schema_name", ref("snowflake_schema", obj, "fully_qualified_name"))
    for db in lz.databases:
        t = m.resource("governance.tf", "snowflake_tag_association", f"{db.name}_owner")
        t.attr("object_identifiers", [ref("snowflake_database", db.name, "fully_qualified_name")])
        t.attr("object_type", "DATABASE")
        t.attr("tag_id", ref("snowflake_tag", "DATA_OWNER", "fully_qualified_name"))
        t.attr("tag_value", db.owner)


def _users(m: Module, lz: LandingZone) -> None:
    for u in lz["users"]:
        b = m.resource("users.tf", "snowflake_service_user" if u["type"] == "SERVICE" else "snowflake_user", u["name"])
        b.attr("name", u["name"])
        b.attr("default_role", ref("snowflake_account_role", u["functional_roles"][0]))
        if u.get("default_warehouse"):
            b.attr("default_warehouse", ref("snowflake_warehouse", u["default_warehouse"]))
        if u.get("network_policy"):
            b.attr("network_policy", ref("snowflake_network_policy", u["network_policy"]))
        if u["type"] == "SERVICE":
            b.attr("rsa_public_key", Expr(f'lookup(var.service_user_public_keys, "{u["name"]}", null)'))
        b.attr("comment", "Managed by the ALTITUDE landing zone")
        rtype = "snowflake_service_user" if u["type"] == "SERVICE" else "snowflake_user"
        for fr in u["functional_roles"]:
            g = m.resource("users.tf", "snowflake_grant_account_role", f"{fr}_to_{u['name']}")
            g.attr("role_name", ref("snowflake_account_role", fr)).attr("user_name", ref(rtype, u["name"]))


def _budgets(m: Module, lz: LandingZone) -> None:
    gov = lz["governance"]
    for b in lz["budgets"]:
        x = m.resource("budgets.tf", "snowflake_execute", b["name"])
        if b["scope"] == "ACCOUNT":
            x.attr("execute", f"CALL SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET!ACTIVATE(); "
                              f"CALL SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET!SET_SPENDING_LIMIT({b['monthly_limit_credits']})")
            x.attr("revert", "CALL SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET!DEACTIVATE()")
        else:
            fq = f"{gov['database']}.{gov['policy_schema']}.{b['name']}"
            stmts = [f"CREATE SNOWFLAKE.CORE.BUDGET IF NOT EXISTS {fq}()",
                     f"CALL {fq}!SET_SPENDING_LIMIT({b['monthly_limit_credits']})"]
            stmts += [f"CALL {fq}!ADD_RESOURCE(SYSTEM$REFERENCE('WAREHOUSE', '{o}', 'SESSION', 'APPLYBUDGET'))"
                      for o in b.get("objects", [])]
            x.attr("execute", "; ".join(stmts))
            x.attr("revert", f"DROP SNOWFLAKE.CORE.BUDGET IF EXISTS {fq}")
            x.attr("depends_on", [Expr(f"snowflake_schema.{tf_name(gov['database'] + '_' + gov['policy_schema'])}")]
                   + [Expr(f"snowflake_warehouse.{tf_name(o)}") for o in b.get("objects", [])])


def _agents(m: Module, lz: LandingZone) -> None:
    np = next((p["name"] for p in lz["network"]["policies"] if not p["account_default"]), None)
    for a in lz.agent_identities:
        r = m.resource("agents.tf", "snowflake_account_role", a["role"])
        r.attr("name", a["role"]).attr("comment", f"Agent role ({a['agent_id']}): distinct machine identity")
        u = m.resource("agents.tf", "snowflake_service_user", a["user"])
        u.attr("name", a["user"]).attr("default_role", ref("snowflake_account_role", a["role"]))
        u.attr("default_warehouse", ref("snowflake_warehouse", a["warehouse"]))
        if np:
            u.attr("network_policy", ref("snowflake_network_policy", np))
        u.attr("rsa_public_key", Expr(f'lookup(var.service_user_public_keys, "{a["user"]}", null)'))
        u.attr("comment", f"ALTITUDE agent identity: {a['name']}")
        g = m.resource("agents.tf", "snowflake_grant_account_role", f"{a['role']}_to_{a['user']}")
        g.attr("role_name", ref("snowflake_account_role", a["role"])).attr("user_name", ref("snowflake_service_user", a["user"]))
        w = m.resource("agents.tf", "snowflake_grant_privileges_to_account_role", f"{a['role']}_{a['warehouse']}", "usage")
        w.attr("account_role_name", ref("snowflake_account_role", a["role"]))
        w.attr("privileges", ["USAGE"])
        w.block("on_account_object").attr("object_type", "WAREHOUSE").attr("object_name", ref("snowflake_warehouse", a["warehouse"]))


def build(lz: LandingZone) -> dict[str, str]:
    m = Module()
    _providers(m, lz)
    _databases(m, lz)
    _roles(m, lz)
    _warehouses(m, lz)
    _network(m, lz)
    _governance(m, lz)
    _users(m, lz)
    _budgets(m, lz)
    _agents(m, lz)
    return m.rendered()
