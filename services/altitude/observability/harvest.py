"""Config-driven, multi-account harvest into the immutable RAW archive.

For each source in ``knowledge/observability/sources.yaml``:

- ``incremental`` / ``merge``: read rows at/after ``watermark - rubric.obs.harvest.incremental_overlap_hours``
  (the first harvest reads the whole native retention window) and append them; the row hash makes
  re-reading the overlap idempotent.
- ``full_snapshot``: read the current state, append rows not yet archived, and record the harvest's
  membership so CURATED can reconstruct the snapshot of any harvest day.

Every step is logged to ``RAW.HARVEST_LOG`` (append-only). One failing source never stops the others.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Iterable

from altitude.core.ids import stable_id
from altitude.core.rubric import RubricSet, default_rubrics

from .config import SourceConfig, load_registry, load_sources
from .db import ObsDatabase
from .sources import HarvestSource, SnowflakeSource, SyntheticSource, _as_dt

OVERLAP_REF = "rubric.obs.harvest.incremental_overlap_hours"


@dataclass
class HarvestResult:
    harvest_id: str
    account_name: str
    as_of: datetime
    steps: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(s["STATUS"] in {"ok", "skipped"} for s in self.steps)

    @property
    def inserted(self) -> int:
        return sum(s["ROWS_INSERTED"] or 0 for s in self.steps)

    def summary(self) -> dict:
        return {"harvest_id": self.harvest_id, "account": self.account_name, "as_of": self.as_of.isoformat(),
                "ok": self.ok, "rows_inserted": self.inserted,
                "failed": [s["SOURCE_TABLE"] for s in self.steps if s["STATUS"] == "failed"]}


def _as_of(v: date | datetime) -> datetime:
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    return datetime.combine(v, time(23, 59, 59))


def harvest_account(db: ObsDatabase, source: HarvestSource, as_of: date | datetime, *,
                    sources: Iterable[SourceConfig] | None = None, rubrics: RubricSet | None = None) -> HarvestResult:
    rubrics = rubrics or default_rubrics()
    as_of_dt = _as_of(as_of)
    account = source.account_name
    harvest_id = stable_id("HRV", account, as_of_dt.isoformat())
    overlap = timedelta(hours=float(rubrics.get(OVERLAP_REF)))
    result = HarvestResult(harvest_id, account, as_of_dt)
    for cfg in sources or load_sources():
        since = None
        if not cfg.is_snapshot and cfg.watermark:
            wm = _as_dt(db.watermark(cfg.table, cfg.watermark, account))
            since = (wm - overlap) if wm else None
        step = {"HARVEST_ID": harvest_id, "ACCOUNT_NAME": account, "SOURCE_TABLE": cfg.table,
                "STRATEGY": cfg.strategy, "AS_OF": as_of_dt, "SINCE": since, "ROWS_READ": 0, "ROWS_INSERTED": 0,
                "ROWS_DUPLICATE": 0, "STATUS": "ok", "ERROR": None}
        try:
            rows = source.read(cfg, since=since, as_of=as_of_dt)
            if rows is None:
                step["STATUS"] = "skipped"
            else:
                ins, dup, hashes = db.append_raw(cfg.table, rows, account=account, harvest_id=harvest_id,
                                                 loaded_at=as_of_dt)
                if cfg.is_snapshot:
                    db.record_membership(cfg.table, account, harvest_id, as_of_dt, hashes)
                step.update(ROWS_READ=len(rows), ROWS_INSERTED=ins, ROWS_DUPLICATE=len(rows) - ins)
        except Exception as e:  # one failing source must not stop the harvest; the failure is logged
            step.update(STATUS="failed", ERROR=f"{type(e).__name__}: {e}"[:500])
        db.log_harvest(step)
        result.steps.append(step)
    return result


# --------------------------------------------------------------------------- multi-account


def source_for(account: dict, as_of: date | datetime, *, days: int | None = None,
               native_retention_days: int | None = None,
               connect: Callable[[str], Any] | None = None, anomalies: list[dict] | None = None) -> HarvestSource:
    """Build the harvest source for one registry account entry."""
    kind = account.get("source", "synthetic")
    if kind == "synthetic":
        from altitude.synthetic import AccountSpec

        syn = account.get("synthetic") or {}
        end = _as_of(as_of).date()
        retention = native_retention_days or max(
            (c.native_retention_days or 0) for c in load_sources())
        spec = AccountSpec(account_name=account["account_name"], organization=syn.get("organization", "ACME"),
                           profile=syn.get("profile", "seeded"), seed=int(syn.get("seed", 7)), end_date=end,
                           days=days or retention, anomalies=list(anomalies or syn.get("anomalies") or []),
                           disabled_issues=set(syn.get("disabled_issues") or []))
        return SyntheticSource(spec, native_retention_days=native_retention_days)
    if kind == "snowflake":
        if connect is None:
            raise ValueError(f"account {account['account_name']}: live harvest needs a connection provider")
        return SnowflakeSource(connect(account["connection_ref"]), account["account_name"])
    raise ValueError(f"unknown source kind {kind!r}")


def harvest_registry(db: ObsDatabase, registry: dict | str | None, as_of: date | datetime, *,
                     days: int | None = None, native_retention_days: int | None = None,
                     connect: Callable[[str], Any] | None = None,
                     rubrics: RubricSet | None = None) -> list[HarvestResult]:
    reg = registry if isinstance(registry, dict) else load_registry(registry)
    sources = load_sources()
    out = []
    for acct in reg.get("accounts", []):
        src = source_for(acct, as_of, days=days, native_retention_days=native_retention_days, connect=connect)
        out.append(harvest_account(db, src, as_of, sources=sources, rubrics=rubrics))
    return out


def freshness(db: ObsDatabase, as_of: date | datetime, rubrics: RubricSet | None = None) -> list[dict]:
    """Hours since the last successful harvest per account and source vs the source's freshness SLA."""
    rubrics = rubrics or default_rubrics()
    as_of_dt = _as_of(as_of)
    last = {(r["ACCOUNT_NAME"], r["SOURCE_TABLE"]): r["LAST_OK"] for r in db.query(
        "SELECT ACCOUNT_NAME, SOURCE_TABLE, max(AS_OF) AS LAST_OK FROM RAW.HARVEST_LOG "
        "WHERE STATUS = 'ok' AND AS_OF <= ? GROUP BY 1, 2", [as_of_dt])}
    accounts = sorted({a for a, _ in last})
    out = []
    for cfg in load_sources():
        sla = float(rubrics.get(cfg.freshness_sla_ref))
        for a in accounts:
            ts = last.get((a, cfg.table))
            lag = None if ts is None else (as_of_dt - ts).total_seconds() / 3600.0
            out.append({"account": a, "source": cfg.table, "domain": cfg.domain, "last_ok": ts,
                        "lag_hours": lag, "sla_hours": sla, "met": lag is not None and lag <= sla})
    return out
