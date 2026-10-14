"""Buying-signal intelligence for the firm's own go-to-market (Section 2, 35.2).

Signals (renewal windows, job postings, Snowflake AE referrals, ...) are scored with
rubric weights and matched to plays (``knowledge/gtm/plays.yaml``)."""

from __future__ import annotations

from datetime import date
from typing import Any

from altitude.core.expr import evaluate
from altitude.core.ids import stable_id
from altitude.core.knowledge import load_yaml
from altitude.core.rubric import RubricSet, default_rubrics


def record_signal(store: Any, account: str, kind: str, observed_on: date, source: str, detail: str = "") -> str:
    sid = stable_id("SIG", account, kind, observed_on.isoformat(), detail)
    if not store.get("gtm_signal", signal_id=sid):
        store.insert("gtm_signal", {"signal_id": sid, "account": account, "kind": kind, "detail": detail,
                                    "observed_on": observed_on, "source": source})
    return sid


def score_accounts(store: Any, as_of: date, accounts_meta: dict[str, dict] | None = None,
                   rubrics: RubricSet | None = None) -> list[dict]:
    rubrics = rubrics or default_rubrics()
    w = rubrics.get("rubric.gtm.weights")
    win = rubrics.get("rubric.gtm.renewal_window_months")
    cap = int(rubrics.get("rubric.gtm.job_posting_cap"))
    cut = rubrics.get("rubric.gtm.priority_cutoffs")
    plays = load_yaml("gtm/plays.yaml")["plays"]
    meta = accounts_meta or {}
    out = []
    for acct in sorted({r["account"] for r in store.query("SELECT DISTINCT account FROM gtm_signal")} | set(meta)):
        sigs = store.query("SELECT * FROM gtm_signal WHERE account = ? ORDER BY observed_on", [acct])
        facts = {"renewal_window": False, "ae_referral": False, "job_posting": False,
                 "snowflake_customer": bool(meta.get(acct, {}).get("snowflake_customer")),
                 "regulated_industry": bool(meta.get(acct, {}).get("regulated_industry")),
                 "cost_overrun_news": False}
        score = 0.0
        reasons, evidence = [], []
        postings = 0
        for s in sigs:
            evidence.append(s["signal_id"])
            if s["kind"] == "renewal_window":
                renew = date.fromisoformat(s["detail"])
                months = (renew.year - as_of.year) * 12 + (renew.month - as_of.month)
                if int(win["min"]) <= months <= int(win["max"]) and not facts["renewal_window"]:
                    facts["renewal_window"] = True
                    score += float(w["renewal_window"])
                    reasons.append(f"legacy renewal in {months} months")
            elif s["kind"] == "job_posting":
                postings += 1
            elif s["kind"] in ("ae_referral", "cost_overrun_news") and not facts[s["kind"]]:
                facts[s["kind"]] = True
                score += float(w[s["kind"]])
                reasons.append(s["kind"].replace("_", " "))
        if postings:
            facts["job_posting"] = True
            score += float(w["job_posting"]) * min(postings, cap)
            reasons.append(f"{postings} migration job posting(s)")
        for k in ("snowflake_customer", "regulated_industry"):
            if facts[k]:
                score += float(w[k])
                reasons.append(k.replace("_", " "))
        play = next(p for p in plays if evaluate(p["when"], facts, rubrics))
        priority = "hot" if score >= float(cut["hot"]) else ("warm" if score >= float(cut["warm"]) else "cold")
        out.append({"account": acct, "score": score, "priority": priority, "reasons": reasons, "play": play["id"],
                    "offer": play["offer"], "pitch": play["pitch"], "evidence": evidence})
    return sorted(out, key=lambda r: (-r["score"], r["account"]))
