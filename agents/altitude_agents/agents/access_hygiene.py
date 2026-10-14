"""Access Hygiene Agent (Section 18.2 #7, max L2): dormant users and grants, orphan roles, ACCOUNTADMIN
holders/usage beyond break-glass, MFA gaps and password-based service users. Every revocation is an L2
draft that needs the owner's recorded approval."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from ..actions import ProposedAction
from ..runtime import AgentContext, AgentResult, BaseAgent, Finding

PRIVILEGED_ROLE = "ACCOUNTADMIN"


class AccessHygiene(BaseAgent):
    agent_id = "AG-ACCESS-HYGIENE"
    version = "1.0.0"

    def run(self, ctx: AgentContext) -> AgentResult:
        dormant_days = int(ctx.r("access_hygiene.dormant_days"))
        users = ctx.call("users")
        ugrants = ctx.call("user_role_grants")
        rgrants = ctx.call("role_grants")
        roles = ctx.call("roles")
        usage = {r["USER_NAME"]: r for r in ctx.call("privileged_usage", role=PRIVILEGED_ROLE, days=dormant_days)}
        break_glass = {u.upper() for u in ctx.policy.break_glass_users}
        system_roles = {r.upper() for r in ctx.policy.system_roles}
        user_roles: dict[str, list[str]] = defaultdict(list)
        for g in ugrants:
            user_roles[g["GRANTEE_NAME"]].append(g["ROLE"])
        findings: list[Finding] = []
        actions: list[ProposedAction] = []
        cutoff = ctx.as_of - timedelta(days=dormant_days)

        for u in users:
            name = u["NAME"]
            if u["DISABLED"]:
                continue
            ev = [f"USERS:{name}"]
            # ---- dormant users and their grants
            last = u["LAST_SUCCESS_LOGIN"]
            if last is None or last < cutoff:
                idle = (ctx.as_of - last).days if last else None
                conf = float(ctx.r("access_hygiene.confidence_dormant"))
                f = Finding(kind="dormant_user", subject=name,
                            title=f"{name}: no successful login for {idle if idle is not None else 'ever'} day(s)",
                            confidence=conf,
                            rationale=f"Last successful login {last} is older than the {dormant_days}-day dormancy window",
                            detail={"last_login": last, "idle_days": idle, "roles": sorted(user_roles.get(name, []))},
                            evidence=ev + [f"GRANTS_TO_USERS:{name}"])
                findings.append(f)
                actions.append(ProposedAction("user.disable", name, {}, "L2", conf, f.rationale, f.evidence,
                                              f"Disable dormant user {name}", f.key))
                for role in sorted(user_roles.get(name, [])):
                    if role.upper() != "PUBLIC":
                        actions.append(ProposedAction("grant.revoke_role_from_user", name, {"role": role}, "L2", conf,
                                                      f"Dormant grant: {f.rationale}", f.evidence,
                                                      f"Revoke {role} from dormant user {name}", f.key))
            # ---- ACCOUNTADMIN outside break-glass
            if PRIVILEGED_ROLE in user_roles.get(name, []) and name.upper() not in break_glass:
                used = usage.get(name)
                conf = float(ctx.r("access_hygiene.confidence_accountadmin"))
                f = Finding(kind="accountadmin_holder", subject=name,
                            title=(f"{name}: holds ACCOUNTADMIN outside break-glass"
                                   + (f"; used it {used['STATEMENTS']} time(s), last {used['LAST_USED']}" if used else "")),
                            confidence=conf,
                            rationale=(f"ACCOUNTADMIN is limited to break-glass users {sorted(break_glass)}; "
                                       f"{len([x for x in user_roles if PRIVILEGED_ROLE in user_roles[x]])} holder(s) vs "
                                       f"rubric maximum {ctx.r('access_hygiene.accountadmin_max_holders')}"),
                            detail={"statements": used["STATEMENTS"] if used else 0,
                                    "last_used": used["LAST_USED"] if used else None},
                            evidence=ev + [f"GRANTS_TO_USERS:{name}:{PRIVILEGED_ROLE}"]
                            + ([f"QUERY_HISTORY:role={PRIVILEGED_ROLE}:user={name}"] if used else []))
                findings.append(f)
                actions.append(ProposedAction("grant.revoke_role_from_user", name, {"role": PRIVILEGED_ROLE}, "L2",
                                              conf, f.rationale, f.evidence, f"Revoke ACCOUNTADMIN from {name}", f.key))
            # ---- MFA gaps (humans) and password service users
            if u["TYPE"] == "PERSON" and u["HAS_PASSWORD"] and not u["HAS_MFA"] and not u["EXT_AUTHN_UID"]:
                conf = float(ctx.r("access_hygiene.confidence_mfa"))
                f = Finding(kind="mfa_gap", subject=name, title=f"{name}: password sign-in without MFA",
                            confidence=conf, rationale="Human user authenticates with a password and has no MFA or SSO",
                            detail={"has_password": True, "has_mfa": False}, evidence=ev)
                findings.append(f)
                actions.append(ProposedAction("user.set_authentication_policy", name,
                                              {"policy": ctx.policy.mfa_authentication_policy}, "L2", conf,
                                              f.rationale, ev, f"Require MFA for {name}", f.key))
            if u["TYPE"] in ("SERVICE", "LEGACY_SERVICE") and u["HAS_PASSWORD"]:
                conf = float(ctx.r("access_hygiene.confidence_service_password"))
                findings.append(Finding(
                    kind="service_password", subject=name, title=f"{name}: service user authenticates with a password",
                    confidence=conf, rationale=f"{u['TYPE']} user has a password; services must use key-pair or OAuth",
                    detail={"type": u["TYPE"]}, evidence=ev,
                    recommendation=(f"Rotate {name} to key-pair authentication, then ALTER USER {name} UNSET PASSWORD "
                                    "(not reversible: done by the owner through change management)")))

        # ---- orphan roles: no user and no parent role, not a system role
        granted_roles = {g["ROLE"] for g in ugrants}
        parented = {g["NAME"] for g in rgrants if g["GRANTED_ON"] == "ROLE"}
        for r in roles:
            role = r["NAME"]
            if role.upper() in system_roles or role in granted_roles or role in parented:
                continue
            privs = [g for g in rgrants if g["GRANTEE_NAME"] == role and g["GRANTED_ON"] != "ROLE"]
            conf = float(ctx.r("access_hygiene.confidence_orphan_role"))
            f = Finding(kind="orphan_role", subject=role,
                        title=f"{role}: orphan role (no users, no parent role) holding {len(privs)} privilege(s)",
                        confidence=conf,
                        rationale="Role is not granted to any user or role, so its privileges are unreachable or unmanaged",
                        detail={"privileges": [f"{g['PRIVILEGE']} ON {g['GRANTED_ON']} "
                                               f"{'.'.join(x for x in (g['TABLE_CATALOG'], g['TABLE_SCHEMA'], g['NAME']) if x)}"
                                               for g in privs]},
                        evidence=[f"ROLES:{role}", f"GRANTS_TO_ROLES:{role}"],
                        recommendation=f"After the revocations are approved, drop {role} via IaC")
            findings.append(f)
            for g in privs:
                obj = ".".join(x for x in (g["TABLE_CATALOG"], g["TABLE_SCHEMA"], g["NAME"]) if x)
                actions.append(ProposedAction(
                    "grant.revoke_privilege_from_role", role,
                    {"privilege": g["PRIVILEGE"], "object_type": g["GRANTED_ON"], "object_name": obj}, "L2", conf,
                    f.rationale, f.evidence, f"Revoke {g['PRIVILEGE']} on {obj} from orphan role {role}", f.key))
        return AgentResult(findings=findings, actions=actions,
                           summary=f"{len(findings)} access issue(s); {len(actions)} revocation draft(s) awaiting owner approval")
