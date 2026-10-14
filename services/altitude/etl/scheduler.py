"""Scheduler conversion (Section 11.2): dependency DAG -> Snowflake task graphs + Airflow DAGs.

Parsers (``controlm``, ``sqlagent``) produce a :class:`SchedulerDAG`. :func:`plan` turns it into Snowflake
task graphs (one root per connected component - a synthetic root when a component has several, the
failure-path step as the graph's finalizer), :func:`render_snowflake` writes ``CREATE TASK ... AFTER ...``
SQL (plus SLA alerts on ``TASK_HISTORY``) and :func:`render_airflow` writes an Airflow DAG per graph.
Retry, timeout and SLA policies come from the source definition, defaulting to
``knowledge/schedulers/policies.yaml``; command bodies come from ``command_mappings.yaml``.
:func:`validate_task_sql` and :func:`validate_airflow` re-read the generated artifacts and check them
(acyclic, every predecessor defined, valid Python).
"""

from __future__ import annotations

import ast
import keyword
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field

from . import kb
from .graph import GraphIssue
from .naming import ident

TASK_PREFIX = "CREATE OR REPLACE TASK"


@dataclass
class SchedJob:
    id: str
    name: str
    command: str = ""
    kind: str = "job"                      # job|dummy|filewatch|sync
    description: str = ""
    schedule: str | None = None            # 5-field cron
    calendar: str | None = None
    retries: int | None = None
    retry_delay_minutes: int | None = None
    timeout_minutes: int | None = None
    sla_minutes: int | None = None         # max duration
    sla_time: str | None = None            # HH:MM deadline
    alert_to: str | None = None
    predecessors: list[str] = field(default_factory=list)
    trigger: str = "all_success"           # all_success|one_failed
    failure_sources: list[str] = field(default_factory=list)  # steps that route here on failure
    external_conditions: list[str] = field(default_factory=list)
    source_ref: str = ""


@dataclass
class SchedulerDAG:
    tool: str
    name: str
    source_file: str
    jobs: dict[str, SchedJob] = field(default_factory=dict)
    issues: list[GraphIssue] = field(default_factory=list)
    timezone: str | None = None

    def issue(self, kid: str, message: str, node: str | None = None) -> None:
        sev = kb.known_issues().get(kid, {}).get("severity", "S3")
        gi = GraphIssue(kid, sev, node, message)
        if gi not in self.issues:
            self.issues.append(gi)

    def edges(self) -> list[tuple[str, str]]:
        return [(p, j.id) for j in self.jobs.values() for p in j.predecessors]

    def validate(self) -> list[str]:
        problems = [f"{j.id}: predecessor {p!r} is not defined" for j in self.jobs.values()
                    for p in j.predecessors if p not in self.jobs]
        problems += [f"cycle among {sorted(c)}" for c in _cycles(set(self.jobs), self.edges())]
        return problems


def _cycles(nodes: set[str], edges: list[tuple[str, str]]) -> list[set[str]]:
    indeg = {n: 0 for n in nodes}
    adj = defaultdict(list)
    for a, b in edges:
        if a in indeg and b in indeg:
            adj[a].append(b)
            indeg[b] += 1
    q = deque(n for n, d in indeg.items() if d == 0)
    seen = set()
    while q:
        n = q.popleft()
        seen.add(n)
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                q.append(m)
    rest = nodes - seen
    return [rest] if rest else []


def _topo(nodes: list[str], edges: list[tuple[str, str]]) -> list[str]:
    indeg = {n: 0 for n in nodes}
    adj = defaultdict(list)
    for a, b in edges:
        if a in indeg and b in indeg:
            adj[a].append(b)
            indeg[b] += 1
    q = deque(sorted(n for n, d in indeg.items() if d == 0))
    out = []
    while q:
        n = q.popleft()
        out.append(n)
        for m in sorted(adj[n]):
            indeg[m] -= 1
            if indeg[m] == 0:
                q.append(m)
    if len(out) != len(nodes):
        raise ValueError(f"scheduler DAG has a cycle among {sorted(set(nodes) - set(out))}")
    return out


# --------------------------------------------------------------------------- planning


@dataclass
class TaskGraph:
    name: str
    root: str
    schedule: str | None
    members: list[str]                 # topological order, root first
    finalizer: str | None = None
    synthetic_root: bool = False


def cron_ranges(nums: list[int]) -> str:
    """[1, 2, 3, 5] -> "1-3,5" (cron list syntax)."""
    if not nums:
        return "*"
    out, start, prev = [], nums[0], nums[0]
    for n in nums[1:] + [None]:
        if n is not None and n == prev + 1:
            prev = n
            continue
        out.append(f"{start}-{prev}" if prev != start else str(start))
        if n is not None:
            start = prev = n
    return ",".join(out)


def _cron_key(cron: str | None) -> tuple[int, int]:
    if not cron:
        return (99, 99)
    parts = cron.split()
    try:
        return (int(parts[1]), int(parts[0]))
    except (ValueError, IndexError):
        return (99, 99)


def plan(dag: SchedulerDAG) -> list[TaskGraph]:
    problems = dag.validate()
    if problems:
        raise ValueError("; ".join(problems))
    # weakly connected components
    parent = {j: j for j in dag.jobs}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in dag.edges() + [(f, j.id) for j in dag.jobs.values() for f in j.failure_sources if f in dag.jobs]:
        parent[find(a)] = find(b)
    comps: dict[str, list[str]] = defaultdict(list)
    for j in sorted(dag.jobs):
        comps[find(j)].append(j)
    graphs = []
    for members in sorted(comps.values(), key=lambda m: min(m)):
        finalizers = [m for m in members if dag.jobs[m].trigger == "one_failed"]
        finalizer = finalizers[0] if len(finalizers) == 1 else None
        if len(finalizers) > 1:
            dag.issue("SCH-06", f"{len(finalizers)} failure handlers in one graph; only one finalizer is allowed - "
                                f"kept as ordinary children", None)
            for f in finalizers:
                dag.jobs[f].trigger = "all_success"
        core = [m for m in members if m != finalizer]
        roots = [m for m in core if not dag.jobs[m].predecessors]
        for m in core:
            if dag.jobs[m].predecessors and dag.jobs[m].schedule:
                dag.issue("SCH-05", f"{dag.jobs[m].name} is both scheduled and triggered; schedule dropped", m)
                dag.jobs[m].schedule = None
        synthetic = False
        if len(roots) == 1:
            root = roots[0]
            schedule = dag.jobs[root].schedule
        else:
            schedules = sorted({dag.jobs[r].schedule for r in roots if dag.jobs[r].schedule}, key=_cron_key)
            if len(schedules) > 1:
                dag.issue("SCH-08", f"roots {sorted(roots)} have different schedules {schedules}; "
                                    f"synthetic root uses {schedules[0]}", None)
            root = ident(f"{dag.name}_{min(roots)}_start")
            dag.jobs[root] = SchedJob(root, f"{dag.name} start", kind="sync", schedule=schedules[0] if schedules else None,
                                      description=f"Synthetic root for {', '.join(sorted(roots))}")
            for r in roots:
                dag.jobs[r].predecessors = [root]
                dag.jobs[r].schedule = None
            schedule = dag.jobs[root].schedule
            core = [root] + core
            synthetic = True
        if finalizer:
            dag.jobs[finalizer].predecessors = []
        order = _topo(core, [(a, b) for a, b in dag.edges() if a in core and b in core])
        graphs.append(TaskGraph(name=root, root=root, schedule=schedule, members=order, finalizer=finalizer,
                                synthetic_root=synthetic))
    return graphs


# --------------------------------------------------------------------------- commands


def command_body(job: SchedJob, dag: SchedulerDAG, policies: dict | None = None) -> tuple[str, str | None]:
    """(Snowflake SQL body, mapping id) for a job's command."""
    policies = policies or kb.scheduler_policies()
    sf = policies["snowflake"]
    if job.kind == "sync":
        return "SELECT CURRENT_TIMESTAMP() AS graph_started_at", "SYNC"
    if job.kind == "dummy":
        return "SELECT 1 AS dummy_job", "DUMMY"
    for m in kb.command_mappings():
        hit = re.search(m["pattern"], job.command or "", re.I | re.S)
        if hit:
            groups = {k: (v or "") for k, v in hit.groupdict().items()}
            if "proc" in groups:
                groups["proc"] = groups["proc"].replace("[", "").replace("]", "")
            ctx = {"dbt_project": sf["dbt_project"], "script_stage": sf["script_stage"],
                   "notification_integration": sf.get("notification_integration", ""),
                   "tag": ident(groups.get("name", "")), **groups}
            return m["snowflake"].format(**ctx), m["id"]
    dag.issue("SCH-07", f"{job.name}: no mapping for command {job.command!r}; placeholder task keeps the graph intact", job.id)
    safe = re.sub(r"[^\w .:/\\-]", " ", job.command or job.name)[:120]
    return f"SELECT 'MANUAL CONVERSION REQUIRED: {safe}' AS pending_step", None


def _q(text: str) -> str:
    return (text or "").replace("'", "''")


def _cron(schedule: str, tz: str) -> str:
    return f"USING CRON {schedule} {tz}"


# --------------------------------------------------------------------------- Snowflake


def render_snowflake(dag: SchedulerDAG, graphs: list[TaskGraph], policies: dict | None = None) -> str:
    policies = policies or kb.scheduler_policies()
    sf, d = policies["snowflake"], policies["defaults"]
    tz = dag.timezone or d["timezone"]
    prefix = f"{sf['database']}.{sf['schema']}"
    out = [f"-- Snowflake task graphs converted from {dag.tool} definition {dag.source_file} ({dag.name})",
           f"-- {len(graphs)} graph(s), {sum(len(g.members) + bool(g.finalizer) for g in graphs)} task(s)", ""]
    for g in graphs:
        jobs = [dag.jobs[m] for m in g.members] + ([dag.jobs[g.finalizer]] if g.finalizer else [])
        retries = max([j.retries for j in jobs if j.retries is not None], default=d["retries"])
        out.append(f"-- graph {g.root}: {' -> '.join(g.members)}" + (f" (finalizer {g.finalizer})" if g.finalizer else ""))
        for j in jobs:
            body, mapping = command_body(j, dag, policies)
            timeout = (j.timeout_minutes or d["timeout_minutes"]) * 60 * 1000
            lines = [f"{TASK_PREFIX} {prefix}.{j.id}", f"  WAREHOUSE = {sf['warehouse']}"]
            if j.id == g.root:
                if g.schedule:
                    lines.append(f"  SCHEDULE = '{_cron(g.schedule, tz)}'")
                lines.append(f"  SUSPEND_TASK_AFTER_NUM_FAILURES = {d['suspend_after_failures']}")
                lines.append(f"  TASK_AUTO_RETRY_ATTEMPTS = {retries}")
            lines.append(f"  USER_TASK_TIMEOUT_MS = {timeout}")
            note = f"{dag.tool} {j.source_ref or j.name}" + (f": {j.description}" if j.description else "")
            if mapping is None:
                note += " [MANUAL]"
            lines.append(f"  COMMENT = '{_q(note)[:250]}'")
            if j.id == g.finalizer:
                lines.append(f"  FINALIZE = {prefix}.{g.root}")
            elif j.predecessors:
                lines.append(f"  AFTER {', '.join(f'{prefix}.{p}' for p in j.predecessors)}")
            lines.append("AS")
            lines.append(f"  {body};")
            out.append("\n".join(lines))
            out.append("")
        out.append(f"SELECT SYSTEM$TASK_DEPENDENTS_ENABLE('{prefix}.{g.root}');")
        out.append("")
    alerts = _sla_alerts(dag, graphs, policies, prefix, tz)
    if alerts:
        out.append("-- SLA alerts (Snowflake tasks have no native SLA): evaluated against TASK_HISTORY")
        out += alerts
    return "\n".join(out).rstrip() + "\n"


def _sla_alerts(dag: SchedulerDAG, graphs: list[TaskGraph], policies: dict, prefix: str, tz: str) -> list[str]:
    sf = policies["snowflake"]
    if not sf.get("sla_alerts"):
        return []
    out = []
    for g in graphs:
        days = (g.schedule.split()[4] if g.schedule else "*")
        for m in g.members:
            j = dag.jobs[m]
            to = j.alert_to if j.alert_to and "@" in j.alert_to else sf.get("default_alert_recipient", "")
            history = (f"TABLE({sf['database']}.INFORMATION_SCHEMA.TASK_HISTORY(TASK_NAME => '{j.id.upper()}', "
                       f"SCHEDULED_TIME_RANGE_START => DATEADD('day', -1, CURRENT_TIMESTAMP())))")
            if j.sla_time:
                hh, mm = j.sla_time.split(":")
                cond = (f"NOT EXISTS (SELECT 1 FROM {history} WHERE STATE = 'SUCCEEDED' "
                        f"AND COMPLETED_TIME >= DATE_TRUNC('DAY', CURRENT_TIMESTAMP()))")
                schedule = _cron(f"{int(mm)} {int(hh)} * * {days}", tz)
                msg = f"{j.name} not completed by {j.sla_time}"
            elif j.sla_minutes:
                cond = (f"EXISTS (SELECT 1 FROM {history} WHERE STATE IN ('EXECUTING', 'SUCCEEDED') AND "
                        f"DATEDIFF('minute', QUERY_START_TIME, COALESCE(COMPLETED_TIME, CURRENT_TIMESTAMP())) > {j.sla_minutes})")
                schedule = _cron(f"*/15 * * * {days}", tz)
                msg = f"{j.name} running longer than {j.sla_minutes} minutes"
            else:
                continue
            name = f"{prefix}.sla_{j.id}"
            out.append("\n".join([
                f"CREATE OR REPLACE ALERT {name}",
                f"  WAREHOUSE = {sf.get('alert_warehouse', sf['warehouse'])}",
                f"  SCHEDULE = '{schedule}'",
                f"  IF ({cond})",
                f"  THEN CALL SYSTEM$SEND_EMAIL('{sf.get('notification_integration', '')}', '{_q(to)}', "
                f"'SLA missed: {_q(j.name)}', '{_q(msg)}');",
                f"ALTER ALERT {name} RESUME;",
                ""]))
    return out


# --------------------------------------------------------------------------- Airflow


def _pyname(name: str) -> str:
    n = ident(name)
    return n + "_" if keyword.iskeyword(n) else n


def render_airflow(dag: SchedulerDAG, g: TaskGraph, policies: dict | None = None) -> str:
    policies = policies or kb.scheduler_policies()
    d, af = policies["defaults"], policies["airflow"]
    tz = dag.timezone or d["timezone"]
    y, mo, da = (int(x) for x in d["start_date"].split("-"))
    jobs = [dag.jobs[m] for m in g.members] + ([dag.jobs[g.finalizer]] if g.finalizer else [])
    dag_id = ident(f"{dag.name}__{g.root}")
    lines = [
        f'"""Airflow DAG converted from {dag.tool} definition {dag.source_file} ({dag.name}).',
        "",
        f"Graph root: {g.root}. Retry / SLA / timeout policies come from the source definition with",
        "defaults from knowledge/schedulers/policies.yaml. Task bodies run on Snowflake.",
        '"""',
        "",
        "from datetime import timedelta",
        "",
        "import pendulum",
        "from airflow import DAG",
        "from airflow.operators.empty import EmptyOperator",
        "from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator",
        "",
        "DEFAULT_ARGS = {",
        f'    "owner": {af["owner"]!r},',
        f'    "retries": {d["retries"]},',
        f'    "retry_delay": timedelta(minutes={d["retry_delay_minutes"]}),',
        f'    "execution_timeout": timedelta(minutes={d["timeout_minutes"]}),',
        "}",
        "",
        "with DAG(",
        f"    dag_id={dag_id!r},",
        f"    schedule={g.schedule!r},",
        f"    start_date=pendulum.datetime({y}, {mo}, {da}, tz={tz!r}),",
        f"    catchup={bool(af.get('catchup', False))!r},",
        f"    max_active_runs={int(af.get('max_active_runs', 1))},",
        "    default_args=DEFAULT_ARGS,",
        f"    tags={[dag.tool, ident(dag.name)]!r},",
        ") as dag:",
    ]
    for j in jobs:
        var = _pyname(j.id)
        args = [f"task_id={j.id!r}"]
        if j.kind == "sync":
            op = "EmptyOperator"
        else:
            op = "SQLExecuteQueryOperator"
            body, _ = command_body(j, dag, policies)
            args += [f"conn_id={af['conn_id']!r}", f"sql={body!r}"]
        if j.retries is not None:
            args.append(f"retries={j.retries}")
        if j.retry_delay_minutes is not None:
            args.append(f"retry_delay=timedelta(minutes={j.retry_delay_minutes})")
        if j.timeout_minutes is not None:
            args.append(f"execution_timeout=timedelta(minutes={j.timeout_minutes})")
        if j.sla_minutes:
            args.append(f"sla=timedelta(minutes={j.sla_minutes})")
        if j.trigger == "one_failed":
            args.append('trigger_rule="one_failed"')
        if j.description:
            args.append(f"doc_md={j.description!r}")
        lines.append(f"    {var} = {op}(")
        lines += [f"        {a}," for a in args]
        lines.append("    )")
    lines.append("")
    for j in jobs:
        preds = j.predecessors
        if j.id == g.finalizer:
            preds = [p for p in j.failure_sources if p in g.members] or list(g.members)
        if not preds:
            continue
        left = _pyname(preds[0]) if len(preds) == 1 else "[" + ", ".join(_pyname(p) for p in preds) + "]"
        lines.append(f"    {left} >> {_pyname(j.id)}")
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------- validation of generated artifacts


def parse_task_sql(sql: str) -> dict[str, dict]:
    """Re-read generated task SQL: {task: {"after": [...], "schedule": str|None, "finalize": str|None}}."""
    tasks = {}
    for block in re.split(rf"(?m)^(?={re.escape(TASK_PREFIX)}\s)", sql):
        m = re.match(rf"{re.escape(TASK_PREFIX)}\s+(\S+)", block)
        if not m:
            continue
        head = block.split("\nAS\n", 1)[0]
        after = re.search(r"(?m)^\s*AFTER\s+(.+)$", head)
        sched = re.search(r"(?m)^\s*SCHEDULE\s*=\s*'([^']+)'", head)
        fin = re.search(r"(?m)^\s*FINALIZE\s*=\s*(\S+)", head)
        tasks[m.group(1)] = {
            "after": [a.strip() for a in after.group(1).split(",")] if after else [],
            "schedule": sched.group(1) if sched else None,
            "finalize": fin.group(1) if fin else None,
            "has_body": "\nAS\n" in block,
        }
    return tasks


def validate_task_sql(sql: str) -> list[str]:
    tasks = parse_task_sql(sql)
    problems = []
    if not tasks:
        return ["no CREATE TASK statements"]
    for name, t in tasks.items():
        if not t["has_body"]:
            problems.append(f"{name}: missing AS <body>")
        roles = sum(bool(x) for x in (t["after"], t["finalize"]))
        if roles > 1:
            problems.append(f"{name}: a task cannot have both AFTER and FINALIZE")
        if t["after"] and t["schedule"]:
            problems.append(f"{name}: child task with a SCHEDULE")
        for p in t["after"]:
            if p not in tasks:
                problems.append(f"{name}: predecessor {p} is not defined")
        if t["finalize"]:
            root = tasks.get(t["finalize"])
            if root is None:
                problems.append(f"{name}: finalizer of undefined root {t['finalize']}")
            elif root["after"] or root["finalize"]:
                problems.append(f"{name}: finalizer must reference a root task")
    edges = [(p, n) for n, t in tasks.items() for p in t["after"] if p in tasks]
    problems += [f"cycle among {sorted(c)}" for c in _cycles(set(tasks), edges)]
    # each graph has exactly one root
    parent = {n: n for n in tasks}

    def find(x: str) -> str:
        while parent[x] != x:
            x = parent[x]
        return x

    for a, b in edges:
        parent[find(a)] = find(b)
    roots = defaultdict(list)
    for n, t in tasks.items():
        if not t["after"] and not t["finalize"]:
            roots[find(n)].append(n)
    for comp, rs in roots.items():
        if len(rs) > 1:
            problems.append(f"graph has several roots {sorted(rs)}")
    return problems


def validate_airflow(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
        compile(source, "<airflow-dag>", "exec")
    except SyntaxError as e:
        return [f"invalid Python: {e}"]
    tasks: dict[str, str] = {}
    edges: list[tuple[str, str]] = []
    problems = []

    def names(node: ast.AST) -> list[str]:
        if isinstance(node, ast.Name):
            return [node.id]
        if isinstance(node, (ast.List, ast.Tuple)):
            return [n for e in node.elts for n in names(e)]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.RShift):
            return names(node.right)
        return []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            tid = next((k.value.value for k in node.value.keywords
                        if k.arg == "task_id" and isinstance(k.value, ast.Constant)), None)
            if tid is not None:
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        tasks[t.id] = tid
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.BinOp) and isinstance(node.value.op, ast.RShift):
            for a in names(node.value.left):
                for b in names(node.value.right):
                    edges.append((a, b))
    if not tasks:
        problems.append("no tasks defined")
    for a, b in edges:
        for n in (a, b):
            if n not in tasks:
                problems.append(f"dependency references undefined task variable {n}")
    if len(set(tasks.values())) != len(tasks):
        problems.append("duplicate task_id")
    problems += [f"cycle among {sorted(c)}" for c in _cycles(set(tasks), edges)]
    return problems


def airflow_edges(source: str) -> set[tuple[str, str]]:
    """(upstream task_id, downstream task_id) pairs declared in a generated DAG file."""
    tree = ast.parse(source)
    var_to_id = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            for k in node.value.keywords:
                if k.arg == "task_id" and isinstance(k.value, ast.Constant):
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            var_to_id[t.id] = k.value.value
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.BinOp) and isinstance(node.value.op, ast.RShift):
            lefts = node.value.left.elts if isinstance(node.value.left, ast.List) else [node.value.left]
            for left in lefts:
                out.add((var_to_id[left.id], var_to_id[node.value.right.id]))
    return out


@dataclass
class SchedulerConversion:
    dag: SchedulerDAG
    graphs: list[TaskGraph]
    task_sql: str
    airflow: dict[str, str]           # file name -> python source


def convert(dag: SchedulerDAG, policies: dict | None = None) -> SchedulerConversion:
    graphs = plan(dag)
    sql = render_snowflake(dag, graphs, policies)
    airflow = {f"{ident(dag.name)}__{g.root}.py": render_airflow(dag, g, policies) for g in graphs}
    return SchedulerConversion(dag, graphs, sql, airflow)
