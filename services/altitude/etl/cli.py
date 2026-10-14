"""``altitude etl`` - ETL & scheduler converters (M9)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_DB = ".altitude/altitude.duckdb"


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _store(path: str):
    from altitude.core.store import Store

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return Store(path)


def _usage(path: str | None) -> dict[str, int] | None:
    return json.loads(Path(path).read_text()) if path else None


def _cmd_parse(args: argparse.Namespace) -> int:
    from .loader import load_packages

    for pkg in load_packages(args.files):
        for g in pkg.graphs:
            _print(g.to_dict() if args.json else {
                "job": g.job, "nodes": {n.id: n.kind for n in g.nodes.values()},
                "edges": [f"{e.src}{'[' + e.src_port + ']' if e.src_port else ''} -> {e.dst}" for e in g.edges],
                "issues": [f"{i.id} {i.severity}: {i.message}" for i in g.issues]})
        for t in pkg.control_tasks:
            _print({"control_task": t.name, "kind": t.kind, "hint": t.recommendation_hint,
                    "issues": [i.id for i in t.issues]})
    return 0


def _cmd_assess(args: argparse.Namespace) -> int:
    from .classify import assess
    from .loader import load_packages, record_assessments

    result = assess(load_packages(args.files), _usage(args.usage))
    if args.db:
        record_assessments(_store(args.db), args.engagement, result)
    _print([{"job": a.job, "kind": a.kind, "classification": a.classification,
             "recommendation": a.recommendation, "complexity": a.complexity_score,
             "confidence": a.confidence, "rationale": a.rationale} for a in result])
    return 0


def _cmd_dbt(args: argparse.Namespace) -> int:
    from .dbt import generate_dbt_project
    from .loader import load_packages, record_assessments

    project = generate_dbt_project(load_packages(args.files), args.name, _usage(args.usage))
    out = Path(args.out)
    for rel, content in sorted(project.files.items()):
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text(content)
    if args.db:
        record_assessments(_store(args.db), args.engagement, project.assessments)
    summary = {"project": str(out), "models": sorted(project.models), "skipped": project.skipped}
    code = 0
    if args.run:
        import duckdb

        from . import synthetic
        from .harness import DbtHarness

        con = duckdb.connect()
        synthetic.load(con, project.sources, project.domains)
        res = DbtHarness(project.files).run(con)
        summary["run"] = {"built": res.built, "errors": res.errors, "tests": len(res.tests),
                          "failed": [f"{t.name} ({t.failures} rows)" for t in res.failed_tests]}
        code = 0 if res.ok else 1
    _print(summary)
    return code


def _cmd_schedule(args: argparse.Namespace) -> int:
    from .loader import load_schedules, record_scheduler
    from .scheduler import convert, validate_airflow, validate_task_sql

    out = Path(args.out)
    (out / "dags").mkdir(parents=True, exist_ok=True)
    report, code = [], 0
    store = _store(args.db) if args.db else None
    from altitude.core.generated import stamp

    for dag in load_schedules(args.file):
        conv = convert(dag)
        sql_name = f"{dag.name.lower()}_tasks.sql"
        (out / sql_name).write_text(stamp(conv.task_sql, ".sql", f"scheduler:{dag.source_file}"))
        problems = validate_task_sql(conv.task_sql)
        for fname, src in conv.airflow.items():
            (out / "dags" / fname).write_text(stamp(src, ".py", f"scheduler:{dag.source_file}"))
            problems += [f"{fname}: {p}" for p in validate_airflow(src)]
        if store is not None:
            record_scheduler(store, args.engagement, conv)
        code |= 1 if problems else 0
        report.append({"dag": dag.name, "tool": dag.tool, "jobs": len(dag.jobs), "graphs": [g.root for g in conv.graphs],
                       "task_sql": str(out / sql_name), "airflow": sorted(conv.airflow), "problems": problems,
                       "issues": [f"{i.id} {i.severity}: {i.message}" for i in dag.issues]})
    _print(report)
    return code


def _cmd_bi(args: argparse.Namespace) -> int:
    from . import kb

    data = kb.bi_approaches()
    rows = [a for a in data["approaches"] if not args.tool or args.tool.lower() in a["tool"].lower()]
    if not rows:
        print(f"no BI approach for {args.tool!r}", file=sys.stderr)
        return 1
    _print({"approaches": rows, "best_practices": data.get("best_practices", [])})
    return 0


def register(subparsers) -> None:
    p = subparsers.add_parser("etl", help="ETL (SSIS, Informatica) and scheduler (Control-M, SQL Agent) converters")
    sub = p.add_subparsers(dest="etl_cmd", required=True)

    pa = sub.add_parser("parse", help="parse ETL exports into mapping graphs")
    pa.add_argument("files", nargs="+")
    pa.add_argument("--json", action="store_true", help="full graph JSON")
    pa.set_defaults(func=_cmd_parse)

    asx = sub.add_parser("assess", help="classify jobs: passthrough/transform/complex -> retire/lift/re-engineer")
    asx.add_argument("files", nargs="+")
    asx.add_argument("--usage", help="JSON {job: runs_in_last_90_days}")
    asx.add_argument("--db", help=f"persist to a control-plane store (e.g. {DEFAULT_DB})")
    asx.add_argument("--engagement", default="ENG-LOCAL")
    asx.set_defaults(func=_cmd_assess)

    d = sub.add_parser("dbt", help="generate a dbt project (optionally compile + run + test on synthetic data)")
    d.add_argument("files", nargs="+")
    d.add_argument("--out", required=True)
    d.add_argument("--name", default="altitude_migration")
    d.add_argument("--usage", help="JSON {job: runs_in_last_90_days}")
    d.add_argument("--run", action="store_true", help="compile, run in DuckDB on synthetic data and run tests")
    d.add_argument("--db")
    d.add_argument("--engagement", default="ENG-LOCAL")
    d.set_defaults(func=_cmd_dbt)

    s = sub.add_parser("schedule", help="convert Control-M / SQL Agent definitions to task graphs + Airflow DAGs")
    s.add_argument("file")
    s.add_argument("--out", required=True)
    s.add_argument("--db")
    s.add_argument("--engagement", default="ENG-LOCAL")
    s.set_defaults(func=_cmd_schedule)

    b = sub.add_parser("bi", help="BI & semantic-layer migration approach (Section 11.3)")
    b.add_argument("tool", nargs="?")
    b.set_defaults(func=_cmd_bi)
