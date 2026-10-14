"""SQL Server Agent job export (SSMS "Script Job as CREATE") -> :class:`SchedulerDAG`.

Reads ``msdb.dbo.sp_add_job`` / ``sp_add_jobstep`` / ``sp_update_job`` / ``sp_add_jobschedule`` calls.
Steps become jobs; the success path (on_success_action 3 = next step, 4 = go to step) becomes dependencies;
steps reached only through on_fail_action become failure handlers (finalizer / one_failed, SCH-06).
A step that only runs ``sp_start_job`` is replaced by a dependency on the started job's first step
(SCH-02 when that job is not in the export). Schedules (freq_type/freq_interval/active_start_time) become cron.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import kb
from .naming import ident
from .scheduler import SchedJob, SchedulerDAG, cron_ranges

_CALL = re.compile(r"EXEC\s+(?:@\w+\s*=\s*)?msdb\.dbo\.(sp_\w+)\s+(.*?)(?=\n\s*(?:IF\s*\(|EXEC\s|COMMIT|GO\b|QuitWithRollback|EndSave|BEGIN\s|DECLARE\s|/\*)|\Z)",
                   re.I | re.S)
_PARAM = re.compile(r"@(\w+)\s*=\s*(N?'(?:[^']|'')*'|-?\d+|@\w+(?:\s+OUTPUT)?|NULL)", re.I | re.S)


def _params(text: str) -> dict[str, str]:
    out = {}
    for name, raw in _PARAM.findall(text):
        v = raw.strip()
        if v.upper().startswith("N'") or v.startswith("'"):
            v = v[v.index("'") + 1:-1].replace("''", "'")
        out[name.lower()] = v
    return out


def _cron(p: dict[str, str], dag: SchedulerDAG, job_name: str, jid: str) -> str | None:
    cfg = kb.scheduler_sources()["sqlagent"]
    ftype = cfg["freq_types"].get(p.get("freq_type", ""), "unknown")
    t = int(p.get("active_start_time", "0") or 0)
    hour, minute = t // 10000, (t // 100) % 100
    sub = cfg["subday_types"].get(p.get("freq_subday_type", "1"), "once")
    every = int(p.get("freq_subday_interval", "0") or 0)
    if sub == "minutes" and every:
        mh = f"*/{every} *"
    elif sub == "hours" and every:
        mh = f"{minute} */{every}"
    else:
        mh = f"{minute} {hour}"
    interval = int(p.get("freq_interval", "0") or 0)
    if ftype == "daily":
        return f"{mh} {'*' if interval in (0, 1) else f'*/{interval}'} * *"
    if ftype == "weekly":
        days = sorted(d for bit, d in cfg["weekday_bits"].items() if interval & int(bit))
        return f"{mh} * * {cron_ranges(days)}"
    if ftype == "monthly":
        return f"{mh} {interval or 1} * *"
    if ftype == "monthly_relative":
        dag.issue("SCH-01", f"{job_name}: relative monthly schedule (e.g. first Monday) approximated", jid)
        return f"{mh} 1-7 * *"
    dag.issue("SCH-01", f"{job_name}: schedule type {ftype} has no cron equivalent", jid)
    return None


def parse_sqlagent(path: str | Path) -> SchedulerDAG:
    path = Path(path)
    cfg = kb.scheduler_sources()["sqlagent"]
    text = path.read_text(encoding="utf-8-sig")
    dag = SchedulerDAG(tool="sqlagent", name=ident(path.stem), source_file=path.name)
    jobs: dict[str, dict] = {}
    current = None
    for proc, args in _CALL.findall(text):
        p = _params(args)
        proc = proc.lower()
        if proc == "sp_add_job":
            current = p.get("job_name")
            jobs[current] = {"steps": {}, "start": 1, "schedule": None, "description": p.get("description", "")}
        elif proc in ("sp_add_jobstep", "sp_update_job", "sp_add_jobschedule"):
            name = p.get("job_name") or current
            if name not in jobs:
                continue
            if proc == "sp_add_jobstep":
                jobs[name]["steps"][int(p.get("step_id", len(jobs[name]["steps"]) + 1))] = p
            elif proc == "sp_update_job" and p.get("start_step_id"):
                jobs[name]["start"] = int(p["start_step_id"])
            elif proc == "sp_add_jobschedule" and p.get("enabled", "1") != "0":
                jobs[name]["schedule"] = p
    actions = cfg["step_actions"]
    step_id = {}  # (job, step) -> node id
    for jname, j in jobs.items():
        for sid, sp in j["steps"].items():
            step_id[(jname, sid)] = ident(f"{jname}__{sp.get('step_name', sid)}")
    starts = {jname: step_id.get((jname, j["start"])) for jname, j in jobs.items()}
    triggers: dict[str, str] = {}   # node id of a sp_start_job step -> started job
    for jname, j in jobs.items():
        for sid, sp in sorted(j["steps"].items()):
            nid = step_id[(jname, sid)]
            cmd = sp.get("command", "")
            m = re.match(r"^\s*EXEC(?:UTE)?\s+msdb\.dbo\.sp_start_job\s+(?:@job_name\s*=\s*)?N?'([^']+)'\s*;?\s*$", cmd, re.I)
            if m:
                triggers[nid] = m.group(1)
            dag.jobs[nid] = SchedJob(
                id=nid, name=f"{jname} / {sp.get('step_name', sid)}", command=cmd,
                description=f"{sp.get('subsystem', 'TSQL')} step {sid} of '{jname}'" + (f": {j['description']}" if j["description"] and sid == j["start"] else ""),
                retries=int(sp.get("retry_attempts", "0") or 0),
                retry_delay_minutes=int(sp.get("retry_interval", "0") or 0) or None,
                source_ref=f"{jname}/step {sid}")
            if sp.get("subsystem", "").upper() in ("POWERSHELL", "CMDEXEC") and not re.search(r"dtexec|dbt|sqlcmd", cmd, re.I):
                dag.issue("SCH-07", f"{jname} step {sid}: {sp.get('subsystem')} command touches the file system / OS", nid)
            if int(sp.get("retry_attempts", "0") or 0):
                dag.issue("SCH-03", f"{jname} step {sid}: retry_attempts={sp['retry_attempts']} becomes retry policy", nid)
        if j["schedule"] and starts[jname]:
            dag.jobs[starts[jname]].schedule = _cron(j["schedule"], dag, jname, starts[jname])
    # success / failure flow
    success_reach: set[str] = set()
    for jname, j in jobs.items():
        stack = [j["start"]]
        seen = set()
        while stack:
            sid = stack.pop()
            if sid in seen or sid not in j["steps"]:
                continue
            seen.add(sid)
            success_reach.add(step_id[(jname, sid)])
            sp = j["steps"][sid]
            act = actions.get(sp.get("on_success_action", "1"), "quit_success")
            nxt = sid + 1 if act == "next_step" else (int(sp.get("on_success_step_id", "0")) if act == "goto_step" else None)
            if nxt and nxt in j["steps"]:
                dag.jobs[step_id[(jname, nxt)]].predecessors.append(step_id[(jname, sid)])
                stack.append(nxt)
        for sid, sp in j["steps"].items():
            if actions.get(sp.get("on_fail_action", "2")) == "goto_step":
                target = step_id.get((jname, int(sp.get("on_fail_step_id", "0"))))
                if target and target not in success_reach:
                    tj = dag.jobs[target]
                    tj.trigger = "one_failed"
                    tj.failure_sources.append(step_id[(jname, sid)])
    for jname in jobs:
        for sid in jobs[jname]["steps"]:
            nid = step_id[(jname, sid)]
            if nid not in success_reach and dag.jobs[nid].trigger != "one_failed":
                dag.issue("SCH-07", f"{dag.jobs[nid].name} is unreachable from the job's start step; dropped", nid)
                del dag.jobs[nid]
    for nid, j in dag.jobs.items():
        if j.trigger == "one_failed":
            dag.issue("SCH-06", f"{j.name} runs on failure of {', '.join(j.failure_sources)}", nid)
    # sp_start_job steps -> dependency on the started job's first step
    for nid, started in triggers.items():
        if nid not in dag.jobs:
            continue
        preds = dag.jobs[nid].predecessors
        target = starts.get(started)
        for other in dag.jobs.values():
            if nid in other.predecessors:
                other.predecessors = [p for p in other.predecessors if p != nid] + preds
        if target:
            dag.jobs[target].predecessors += [p for p in preds if p not in dag.jobs[target].predecessors]
        else:
            dag.issue("SCH-02", f"{dag.jobs[nid].name} starts job '{started}' which is not in the export", nid)
        for other in dag.jobs.values():
            other.failure_sources = [p for p in other.failure_sources if p != nid]
        del dag.jobs[nid]
    return dag
