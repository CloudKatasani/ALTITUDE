"""Control-M XML (DEFTABLE export) -> :class:`SchedulerDAG`.

Dependencies come from condition names: a job's IN condition is satisfied by the job(s) whose OUT condition
adds (+) that name. Conditions nobody in the export produces are external (file arrivals, other folders) and
raise SCH-02. TIMEFROM / WEEKDAYS / DAYS become cron; calendars (DAYSCAL, WEEKSCAL, CONFCAL) raise SCH-01;
MAXRERUN / INTERVAL become retry policy (SCH-03); SHOUT LATETIME / EXECTIME become SLAs (SCH-04).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from . import kb
from .naming import ident
from .scheduler import SchedJob, SchedulerDAG, cron_ranges


def _interval_minutes(value: str | None, units: dict[str, int]) -> int | None:
    m = re.match(r"^0*(\d+)([MHD])$", (value or "").strip().upper())
    return int(m.group(1)) * units[m.group(2)] if m else None


def _cron(job: ET.Element) -> str | None:
    tf = (job.get("TIMEFROM") or "").strip()
    if not re.fullmatch(r"\d{4}", tf):
        return None
    hour, minute = int(tf[:2]), int(tf[2:])
    weekdays = (job.get("WEEKDAYS") or "").strip()
    days = (job.get("DAYS") or "").strip()
    dow = "*"
    if weekdays and weekdays.upper() != "ALL":
        nums = sorted({int(d) for d in re.findall(r"\d", weekdays)})
        dow = cron_ranges(nums)
    dom = "*"
    if days and days.upper() not in ("ALL", ""):
        nums = sorted({int(d) for d in re.findall(r"\d+", days)})
        dom = ",".join(str(n) for n in nums) if nums else "*"
    return f"{minute} {hour} {dom} * {dow}"


def parse_controlm(path: str | Path) -> list[SchedulerDAG]:
    """One :class:`SchedulerDAG` per FOLDER / SMART_FOLDER / TABLE."""
    path = Path(path)
    cfg = kb.scheduler_sources()["controlm"]
    root = ET.parse(path).getroot()
    dags = []
    folders = [el for el in root.iter() if el.tag in cfg["folder_elements"]]
    for folder in folders:
        name = next((folder.get(a) for a in cfg["folder_name_attrs"] if folder.get(a)), path.stem)
        dag = SchedulerDAG(tool="controlm", name=name, source_file=path.name)
        producers: dict[str, list[str]] = {}
        incond: dict[str, list[str]] = {}
        for job in folder.findall("JOB"):
            jname = job.get("JOBNAME")
            jid = ident(jname)
            tasktype = job.get("TASKTYPE") or "Job"
            command = job.get("CMDLINE") or ""
            if not command and job.get("MEMNAME"):
                command = f"{(job.get('MEMLIB') or '').rstrip('/')}/{job.get('MEMNAME')}".lstrip("/")
                command = ("/" + command) if job.get("MEMLIB", "").startswith("/") else command
            kind = "dummy" if tasktype.lower() == "dummy" else (
                "filewatch" if tasktype in cfg.get("file_watch_tasktypes", []) else "job")
            sj = SchedJob(id=jid, name=jname, command=command, kind=kind, description=job.get("DESCRIPTION") or "",
                          schedule=_cron(job), source_ref=f"{name}/{jname}")
            reruns = job.get("MAXRERUN")
            if reruns and reruns.isdigit():
                sj.retries = int(reruns)
                if int(reruns):
                    dag.issue("SCH-03", f"{jname}: MAXRERUN={reruns} becomes retry policy", jid)
            sj.retry_delay_minutes = _interval_minutes(job.get("INTERVAL"), cfg["interval_units"])
            if job.get("CYCLIC") == "1":
                dag.issue("SCH-03", f"{jname}: cyclic job (every {job.get('INTERVAL')}) - schedule as a separate frequent graph", jid)
            for cal in cfg["calendar_attrs"]:
                if job.get(cal):
                    sj.calendar = job.get(cal)
                    dag.issue("SCH-01", f"{jname}: calendar {cal}={job.get(cal)} approximated by cron", jid)
            if kind == "filewatch":
                dag.issue("SCH-02", f"{jname}: file watcher becomes a stage/directory-table sensor", jid)
            for sh in job.findall("SHOUT"):
                when = (sh.get("WHEN") or "").upper()
                if when == "LATETIME" and re.fullmatch(r"\d{4}", sh.get("TIME") or ""):
                    sj.sla_time = f"{sh.get('TIME')[:2]}:{sh.get('TIME')[2:]}"
                elif when == "EXECTIME":
                    m = re.search(r"(\d+)", sh.get("TIME") or "")
                    sj.sla_minutes = int(m.group(1)) if m else None
                else:
                    sj.alert_to = sj.alert_to or sh.get("DEST")
                    continue
                sj.alert_to = sh.get("DEST") or sj.alert_to
                dag.issue("SCH-04", f"{jname}: SHOUT {when} becomes an SLA alert", jid)
            for oc in job.findall("OUTCOND"):
                if (oc.get("SIGN") or "+").upper() in cfg["add_condition_signs"]:
                    producers.setdefault(oc.get("NAME"), []).append(jid)
            incond[jid] = [ic.get("NAME") for ic in job.findall("INCOND")]
            dag.jobs[jid] = sj
        for jid, conds in incond.items():
            for cond in conds:
                srcs = [p for p in producers.get(cond, []) if p != jid]
                if srcs:
                    dag.jobs[jid].predecessors += [s for s in srcs if s not in dag.jobs[jid].predecessors]
                else:
                    dag.jobs[jid].external_conditions.append(cond)
                    dag.issue("SCH-02", f"{dag.jobs[jid].name}: waits for external condition {cond!r}", jid)
        dags.append(dag)
    return dags
