"""AI remediation agent (Section 16 "Convert", M5).

For each open conversion issue the agent finds a rule in ``knowledge/conversion/remediation_rules.yaml``
(EWI code / issue pattern -> fix template), locates the region the issue marker points at (the marker run
plus the statement it annotates), and proposes a change. Rule fixes are rendered through the offline,
deterministic ``TemplateProvider``; issues no rule covers can be sent to a tenant-approved LLM provider
(``altitude.core.ai.provider_for``) with the code fenced as untrusted data.

Every change becomes an ``ai_change`` row (diff, confidence, rationale, model id, prompt template
id@version, linked issue ids, generated unit tests) plus an ``ai_inference`` record; changes below
``rubric.ai.review_confidence_min`` are queued for human review. Changes land as a **PR pack** directory
(changed files, original, per-change diffs, unit tests, review checklist, manifest) - never in production.
"""

from __future__ import annotations

import difflib
import importlib.util
import json
import os
import re
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from altitude.core import audit
from altitude.core.ai import Inference, ReviewQueue, TemplateProvider, fence_untrusted
from altitude.core.errors import ReadOnlyViolation
from altitude.core.generated import stamp
from altitude.core.ids import content_hash, stable_id
from altitude.core.rubric import RubricSet, default_rubrics

from . import factory, kb
from .splitter import split_statements

AGENT_ID = "altitude.conversion.remediator"
PRODUCTION_MARKER = ".altitude-production"
PRODUCTION_ENV = "ALTITUDE_PRODUCTION_PATHS"
_MARKER = re.compile(r"!!!RESOLVE EWI!!!|--\s*\*\*\s*(?:SSC|MSC|ALT)-")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------- text helpers


def is_marker_line(line: str) -> bool:
    s = line.strip()
    return bool(_MARKER.search(s)) and (s.startswith("--") or s.startswith("!!!RESOLVE EWI!!!") and s.endswith("!!!"))


def find_region(content: str, line: int, scope: str = "statement", end_hint: int | None = None) -> tuple[int, int]:
    """Line span (1-based, inclusive) a marker on ``line`` refers to: the marker run plus its statement.

    ``end_hint`` is the statement's last output line when the converter recorded it.
    """
    lines = content.splitlines()
    n = len(lines)
    line = max(1, min(line, n))
    s = e = line
    if not is_marker_line(lines[line - 1]):
        # inline marker inside code: the statement containing the line
        for u in split_statements(content):
            if u.kind != "comment" and u.start_line <= line <= u.end_line:
                return u.start_line, u.end_line
        return line, line
    while s > 1 and is_marker_line(lines[s - 2]):
        s -= 1
    if end_hint is not None and line <= end_hint <= n and scope == "statement":
        return s, end_hint
    while e < n and is_marker_line(lines[e]):
        e += 1
    nxt = e + 1
    if nxt > n:
        return s, e
    if lines[nxt - 1].lstrip().startswith("--"):
        e = nxt  # commented-out source (e.g. BTEQ dot-command): the comment run
        while e < n and lines[e].lstrip().startswith("--") and not is_marker_line(lines[e]):
            e += 1
        return s, e
    if scope == "line":
        return s, nxt
    for u in split_statements(content):
        if u.kind != "comment" and u.start_line <= nxt <= u.end_line:
            return s, max(nxt, u.end_line)
    return s, nxt


def strip_markers(text: str, codes: set[str]) -> str:
    """Remove the markers of the given issue codes (whole marker lines and inline markers)."""
    out = []
    for line in text.splitlines():
        if is_marker_line(line) and any(c in line for c in codes):
            continue
        for c in codes:
            line = re.sub(r"!!!RESOLVE EWI!!!\s*/\*\*\*\s*" + re.escape(c) + r"\b.*?\*\*\*/!!!\s*", "", line)
            line = re.sub(r"--\s*\*\*\s*" + re.escape(c) + r"\b.*?\*\*", "", line)
        out.append(line)
    return "\n".join(out)


def apply_rule(rule: dict, region: str) -> str:
    """Deterministic rendering of a remediation rule's fix template over a region."""
    fix = rule["fix"]
    kind = fix["type"]
    if kind == "ack":
        return region
    if kind == "drop_region":
        return fix["comment"]
    if kind == "drop_lines":
        rx = re.compile(fix["pattern"], re.I)
        return "\n".join(ln for ln in region.splitlines() if not rx.search(ln))
    if kind == "regex":
        out = region
        for step in fix["steps"]:
            pattern = step["pattern"]
            flags = 0 if pattern.startswith("(?") else re.I
            out = re.sub(pattern, step["replacement"], out, flags=flags)
        return out
    raise ValueError(f"unknown fix type {kind!r}")


def _rule_matches(rule: dict, code: str, region: str) -> bool:
    if not any(re.fullmatch(c, code, re.I) for c in rule["codes"]):
        return False
    if rule.get("when") and not re.search(rule["when"], region, re.I | re.M):
        return False
    if rule.get("unless") and re.search(rule["unless"], region, re.I | re.M):
        return False
    return True


def splice(content: str, patches: list[tuple[int, int, str]]) -> str:
    """Replace inclusive 1-based line spans with new text (spans must not overlap)."""
    lines = content.splitlines()
    for s, e, text in sorted(patches, key=lambda p: p[0], reverse=True):
        lines[s - 1:e] = text.splitlines() if text else []
    return "\n".join(lines) + ("\n" if content.endswith("\n") else "")


def assert_not_production(path: Path) -> None:
    """PR packs are drafts: refuse to write into anything marked as a production location."""
    path = Path(path).resolve()
    protected = [Path(p).resolve() for p in os.environ.get(PRODUCTION_ENV, "").split(os.pathsep) if p]
    for parent in [path, *path.parents]:
        if (parent / PRODUCTION_MARKER).exists() or parent in protected:
            raise ReadOnlyViolation(f"refusing to write AI changes into production location {parent}")


def _clean_llm_output(text: str) -> str:
    m = re.search(r"```(?:sql)?\s*\n(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip("\n")


# --------------------------------------------------------------------------- records


@dataclass
class ChangeRecord:
    change_id: str
    line_start: int
    line_end: int
    before_text: str
    after_text: str
    rule_ids: list[str]
    issue_ids: list[str]
    issue_codes: list[str]
    confidence: float
    rationale: str
    model_id: str
    prompt_template: str
    below_floor: bool = False
    inference_id: str = ""
    diff: str = ""
    tests: list[str] = field(default_factory=list)
    test_specs: dict = field(default_factory=dict)


@dataclass
class RemediationResult:
    artifact_id: str
    pack_id: str
    pack_dir: Path
    changes: list[ChangeRecord]
    unresolved_issue_ids: list[str]


# --------------------------------------------------------------------------- agent


class RemediationAgent:
    agent_id = AGENT_ID

    def __init__(self, store: Any, *, packs_root: Path, rubrics: RubricSet | None = None,
                 provider: Any = None, rules: list[dict] | None = None):
        self.store = store
        self.packs_root = Path(packs_root)
        self.rubrics = rubrics or default_rubrics()
        self.provider = provider or TemplateProvider()
        self.rules = rules if rules is not None else kb.remediation_rules()
        self.queue = ReviewQueue(store, self.rubrics)

    # ------------------------------------------------------------------ public
    def remediate(self, artifact_id: str) -> RemediationResult:
        art = self.store.get("converted_artifact", artifact_id=artifact_id)
        if art is None:
            raise KeyError(artifact_id)
        existing = self.store.get("pr_pack", artifact_id=artifact_id)
        if existing:
            return self._existing(art, existing)
        content = self.store.get("artifact_content", artifact_id=artifact_id, kind="converted")["content"]
        issues = self.store.query(
            "SELECT i.*, d.region_end_line FROM conversion_issue i LEFT JOIN conversion_issue_detail d "
            "USING (issue_id) WHERE i.artifact_id=? AND i.status='open' ORDER BY i.line, i.issue_id",
            [artifact_id])
        planned, unresolved = self._plan(content, issues)
        changes = [self._build_change(art, content, group) for group in planned]
        remediated = splice(content, [(c.line_start, c.line_end, c.after_text) for c in changes])
        pack_id = stable_id("PRP", artifact_id, content_hash(remediated), length=10)
        pack_dir = self.packs_root / pack_id
        self._persist(art, changes, remediated, pack_id)
        self._write_pack(pack_dir, art, content, remediated, changes, unresolved, pack_id)
        manifest_hash = content_hash((pack_dir / "manifest.json").read_text())
        self.store.insert("pr_pack", {"pack_id": pack_id, "artifact_id": artifact_id, "run_id": art["run_id"],
                                      "path": str(pack_dir), "manifest_hash": manifest_hash,
                                      "created_at": _now()})
        conf = min([c.confidence for c in changes], default=1.0)
        engagement = self.store.scalar("SELECT engagement_id FROM conversion_run WHERE run_id=?", [art["run_id"]])
        factory.transition(self.store, engagement_id=engagement, object_id=art["object_id"],
                           to_state="AI-remediated", actor=self.agent_id, actor_type="agent",
                           evidence_ref=f"pr_pack:{pack_id}", confidence=conf, artifact_id=artifact_id)
        audit.record(self.store, self.agent_id, "conversion.remediate", actor_type="agent",
                     subject_type="converted_artifact", subject_id=artifact_id,
                     details={"pack_id": pack_id, "changes": [c.change_id for c in changes],
                              "unresolved": [i["issue_id"] for i in unresolved]})
        return RemediationResult(artifact_id, pack_id, pack_dir, changes, [i["issue_id"] for i in unresolved])

    # ------------------------------------------------------------------ planning
    def _plan(self, content: str, issues: list[dict]) -> tuple[list[dict], list[dict]]:
        """Match issues to rules and merge overlapping regions into change groups."""
        items: list[dict] = []
        unresolved: list[dict] = []
        llm_enabled = getattr(self.provider, "name", "template") != "template"
        for issue in issues:
            if issue["line"] is None:
                unresolved.append(issue)
                continue
            matched = None
            for rule in self.rules:
                s, e = find_region(content, issue["line"], rule.get("scope", "statement"),
                                   issue.get("region_end_line"))
                region = "\n".join(content.splitlines()[s - 1:e])
                if _rule_matches(rule, issue["code"], region):
                    matched = (rule, s, e)
                    break
            if matched:
                rule, s, e = matched
                items.append({"issue": issue, "rule": rule, "start": s, "end": e})
            elif llm_enabled:
                s, e = find_region(content, issue["line"], "statement", issue.get("region_end_line"))
                items.append({"issue": issue, "rule": None, "start": s, "end": e})
            else:
                unresolved.append(issue)
        groups: list[dict] = []
        for it in sorted(items, key=lambda x: (x["start"], x["end"])):
            if groups and it["start"] <= groups[-1]["end"]:
                groups[-1]["end"] = max(groups[-1]["end"], it["end"])
                groups[-1]["items"].append(it)
            else:
                groups.append({"start": it["start"], "end": it["end"], "items": [it]})
        return groups, unresolved

    # ------------------------------------------------------------------ building a change
    def _build_change(self, art: dict, content: str, group: dict) -> ChangeRecord:
        lines = content.splitlines()
        before = "\n".join(lines[group["start"] - 1:group["end"]])
        text = before
        rule_ids, issue_ids, codes, confs, rationales, prompts = [], [], [], [], [], []
        specs = {"absent": [], "present": [], "parses": None}
        model_id = TemplateProvider.model_id
        llm_issues = [it for it in group["items"] if it["rule"] is None]
        for it in group["items"]:
            rule = it["rule"]
            if rule is None:
                continue
            prompt = kb.prompts()[rule["prompt"]]
            data = fence_untrusted(text, "sql") + "\n" + json.dumps({"rule": {k: rule[k] for k in ("id", "fix")}})
            text = TemplateProvider(renderer=lambda _s, _d, r=rule, t=text: apply_rule(r, t)).complete(
                prompt["system"], data)
            rule_ids.append(rule["id"])
            confs.append(float(self.rubrics.get(rule["confidence_ref"])))
            rationales.append(f"[{rule['id']}] {rule['rationale']}")
            prompts.append(kb.prompt_ref(rule["prompt"]))
            tests = rule.get("tests", {})
            specs["absent"] += [p for p in tests.get("absent", []) if p not in specs["absent"]]
            specs["present"] += [p for p in tests.get("present", []) if p not in specs["present"]]
            specs["parses"] = specs["parses"] or tests.get("parses")
        if llm_issues:
            prompt = kb.prompts()["conversion.remediate.freeform"]
            data = fence_untrusted(text, "sql") + "\n" + json.dumps(
                {"issues": [{"code": it["issue"]["code"], "message": it["issue"]["message"]} for it in llm_issues]})
            proposal = _clean_llm_output(self.provider.complete(prompt["system"], data))
            if proposal.strip() and proposal.strip() != text.strip():
                text = proposal
            model_id = getattr(self.provider, "model_id", "unknown")
            confs.append(float(self.rubrics.get("rubric.conversion.remediation_confidence.llm")))
            rationales.append(f"[{self.provider.name}] proposal for issues without a remediation rule "
                              f"({', '.join(it['issue']['code'] for it in llm_issues)}); requires review")
            prompts.append(kb.prompt_ref("conversion.remediate.freeform"))
        for it in group["items"]:
            issue_ids.append(it["issue"]["issue_id"])
            codes.append(it["issue"]["code"])
        text = strip_markers(text, set(codes))
        specs["absent"] += [re.escape(c) for c in sorted(set(codes))]
        change_id = stable_id("CHG", art["artifact_id"], group["start"], group["end"], sorted(issue_ids), length=10)
        rationale = " ".join(rationales) + f" Resolves {', '.join(sorted(set(codes)))}."
        rec = ChangeRecord(
            change_id=change_id, line_start=group["start"], line_end=group["end"], before_text=before,
            after_text=text, rule_ids=rule_ids, issue_ids=issue_ids, issue_codes=sorted(set(codes)),
            confidence=min(confs), rationale=rationale, model_id=model_id,
            prompt_template=",".join(sorted(set(prompts))), test_specs=specs,
        )
        single = splice(content, [(rec.line_start, rec.line_end, rec.after_text)])
        rec.diff = "\n".join(difflib.unified_diff(
            content.splitlines(), single.splitlines(), fromfile=f"a/{art['target_path']}",
            tofile=f"b/{art['target_path']}", lineterm="", n=2)) + "\n"
        rec.tests = _test_names(rec)
        return rec

    # ------------------------------------------------------------------ persistence
    def _persist(self, art: dict, changes: list[ChangeRecord], remediated: str, pack_id: str) -> None:
        tenant = None
        for c in changes:
            inf = Inference(kind="remediation", subject_type="ai_change", subject_id=c.change_id,
                            output=c.diff, confidence=c.confidence, rationale=c.rationale, model_id=c.model_id,
                            prompt_template=c.prompt_template, provider=getattr(self.provider, "name", "template")
                            if c.model_id != TemplateProvider.model_id else "template",
                            inputs_ref=f"artifact_content:{art['artifact_id']}/converted#L{c.line_start}-L{c.line_end}",
                            tenant_id=tenant)
            self.queue.record(inf)
            c.inference_id = inf.inference_id
            c.below_floor = inf.needs_review
            self.store.insert("ai_change", {
                "change_id": c.change_id, "artifact_id": art["artifact_id"], "agent_id": self.agent_id,
                "model_id": c.model_id, "prompt_template": c.prompt_template, "diff": c.diff,
                "confidence": round(c.confidence, 3), "rationale": c.rationale,
                "linked_issue_ids": c.issue_ids,
                "tests_generated": [f"tests/{_test_module(art)}::{t}" for t in c.tests],
            })
            self.store.insert("ai_change_patch", {
                "change_id": c.change_id, "artifact_id": art["artifact_id"], "rule_ids": c.rule_ids or None,
                "line_start": c.line_start, "line_end": c.line_end, "before_text": c.before_text,
                "after_text": c.after_text, "below_floor": c.below_floor, "inference_id": c.inference_id,
            })
        self.store.insert("artifact_content", {"artifact_id": art["artifact_id"], "kind": "remediated",
                                               "content_hash": content_hash(remediated), "content": remediated,
                                               "created_at": _now()})

    def _existing(self, art: dict, pack: dict) -> RemediationResult:
        rows = self.store.query(
            "SELECT c.*, p.line_start, p.line_end, p.before_text, p.after_text, p.rule_ids, p.below_floor, "
            "p.inference_id FROM ai_change c JOIN ai_change_patch p USING (change_id) WHERE c.artifact_id=? "
            "ORDER BY p.line_start", [art["artifact_id"]])
        changes = [ChangeRecord(
            change_id=r["change_id"], line_start=r["line_start"], line_end=r["line_end"],
            before_text=r["before_text"], after_text=r["after_text"], rule_ids=list(r["rule_ids"] or []),
            issue_ids=list(r["linked_issue_ids"] or []), issue_codes=[], confidence=float(r["confidence"]),
            rationale=r["rationale"], model_id=r["model_id"], prompt_template=r["prompt_template"],
            below_floor=bool(r["below_floor"]), inference_id=r["inference_id"], diff=r["diff"],
            tests=[t.split("::")[-1] for t in (r["tests_generated"] or [])]) for r in rows]
        linked = {i for c in changes for i in c.issue_ids}
        open_ids = [r["issue_id"] for r in self.store.query(
            "SELECT issue_id FROM conversion_issue WHERE artifact_id=? AND status='open'", [art["artifact_id"]])]
        return RemediationResult(art["artifact_id"], pack["pack_id"], Path(pack["path"]), changes,
                                 [i for i in open_ids if i not in linked])

    # ------------------------------------------------------------------ PR pack
    def _write_pack(self, pack_dir: Path, art: dict, content: str, remediated: str, changes: list[ChangeRecord],
                    unresolved: list[dict], pack_id: str) -> None:
        assert_not_production(pack_dir)
        target = art["target_path"]
        source = f"conversion_run:{art['run_id']}/artifact:{art['artifact_id']}"
        (pack_dir / "files" / target).parent.mkdir(parents=True, exist_ok=True)
        (pack_dir / "original" / target).parent.mkdir(parents=True, exist_ok=True)
        (pack_dir / "changes").mkdir(parents=True, exist_ok=True)
        (pack_dir / "tests").mkdir(parents=True, exist_ok=True)
        (pack_dir / "files" / target).write_text(stamp(remediated, ".sql", source))
        (pack_dir / "original" / target).write_text(content)
        for c in changes:
            (pack_dir / "changes" / f"{c.change_id}.diff").write_text(c.diff)
        (pack_dir / "tests" / _test_module(art)).write_text(stamp(render_tests(art, changes), ".py", source))
        write_manifest(pack_dir, build_manifest(self.store, art, pack_id, changes, unresolved))
        (pack_dir / "REVIEW_CHECKLIST.md").write_text(stamp(render_checklist(art, pack_id, changes, unresolved),
                                                            ".md", source))


# --------------------------------------------------------------------------- pack rendering


def _test_module(art: dict) -> str:
    return f"test_{art['artifact_id'].replace('-', '_').lower()}.py"


def _fn(change_id: str) -> str:
    return change_id.replace("-", "_").lower()


def _test_names(c: ChangeRecord) -> list[str]:
    names = [f"test_{_fn(c.change_id)}_applied"]
    names += [f"test_{_fn(c.change_id)}_absent_{i}" for i in range(len(c.test_specs.get("absent", [])))]
    names += [f"test_{_fn(c.change_id)}_present_{i}" for i in range(len(c.test_specs.get("present", [])))]
    if c.test_specs.get("parses"):
        names.append(f"test_{_fn(c.change_id)}_parses")
    return names


def render_tests(art: dict, changes: list[ChangeRecord]) -> str:
    out = [
        f'"""Generated unit tests for {art["artifact_id"]} ({art["target_path"]}).',
        "",
        "Each test checks one AI change against the file under test: final/<path> (approved changes only,",
        "written by the review workflow) or files/<path> (all proposed changes). Run with pytest or",
        "`altitude conversion test`.",
        '"""',
        "",
        "import json",
        "import re",
        "from pathlib import Path",
        "",
        "PACK = Path(__file__).resolve().parents[1]",
        'MANIFEST = json.loads((PACK / "manifest.json").read_text())',
        "FLAGS = re.I | re.M",
        "",
        "",
        "def _effective(change_id):",
        '    change = MANIFEST["changes"][change_id]',
        '    return change["final_text"] if change.get("final_text") is not None else change["after_text"]',
        "",
        "",
        "def _target():",
        '    final = PACK / "final" / MANIFEST["target_path"]',
        '    return (final if final.exists() else PACK / "files" / MANIFEST["target_path"]).read_text()',
        "",
        "",
        "def _code_only(text):",
        '    return "\\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("--"))',
        "",
    ]
    for c in changes:
        cid = c.change_id
        fn = _fn(cid)
        out += ["", f"def test_{fn}_applied():", f"    assert _effective({cid!r}) in _target()", ""]
        for i, pattern in enumerate(c.test_specs.get("absent", [])):
            out += ["", f"def test_{fn}_absent_{i}():",
                    f"    assert not re.search({pattern!r}, _effective({cid!r}), FLAGS)", ""]
        for i, pattern in enumerate(c.test_specs.get("present", [])):
            out += ["", f"def test_{fn}_present_{i}():",
                    f"    assert re.search({pattern!r}, _effective({cid!r}), FLAGS)", ""]
        if c.test_specs.get("parses"):
            out += ["", f"def test_{fn}_parses():", "    import sqlglot", "",
                    f"    statements = sqlglot.parse(_code_only(_effective({cid!r})), read={c.test_specs['parses']!r})",
                    "    assert [s for s in statements if s is not None]", ""]
    return "\n".join(out).rstrip() + "\n"


def build_manifest(store: Any, art: dict, pack_id: str, changes: list[ChangeRecord], unresolved: list[dict]) -> dict:
    run = store.get("conversion_run", run_id=art["run_id"])
    decisions = {r["change_id"]: r for r in store.query(
        "SELECT c.change_id, c.reviewer, c.decision, c.decided_at, p.final_text FROM ai_change c "
        "JOIN ai_change_patch p USING (change_id) WHERE c.artifact_id=?", [art["artifact_id"]])}
    return {
        "pack_id": pack_id,
        "artifact_id": art["artifact_id"],
        "run_id": art["run_id"],
        "tool": run["tool"] if run else None,
        "tool_version": run["tool_version"] if run else None,
        "object_id": art["object_id"],
        "object_code_hash": art["object_code_hash"],
        "target_path": art["target_path"],
        "converted_content_hash": art["content_hash"],
        "production": False,
        "changes": {
            c.change_id: {
                "line_start": c.line_start, "line_end": c.line_end, "rules": c.rule_ids,
                "linked_issue_ids": c.issue_ids, "confidence": round(c.confidence, 3),
                "below_review_floor": c.below_floor, "rationale": c.rationale, "model_id": c.model_id,
                "prompt_template": c.prompt_template, "inference_id": c.inference_id,
                "diff": f"changes/{c.change_id}.diff", "tests": c.tests,
                "before_text": c.before_text, "after_text": c.after_text,
                "final_text": (decisions.get(c.change_id) or {}).get("final_text"),
                "reviewer": (decisions.get(c.change_id) or {}).get("reviewer"),
                "decision": (decisions.get(c.change_id) or {}).get("decision"),
            } for c in changes
        },
        "unresolved_issues": [{"issue_id": i["issue_id"], "code": i["code"], "severity": i["severity"],
                               "line": i["line"], "message": i["message"]} for i in unresolved],
    }


def write_manifest(pack_dir: Path, manifest: dict) -> None:
    (pack_dir / "manifest.json").write_text(stamp(json.dumps(manifest, indent=2, default=str), ".json",
                                                  f"pr_pack:{manifest['pack_id']}"))


def render_checklist(art: dict, pack_id: str, changes: list[ChangeRecord], unresolved: list[dict]) -> str:
    lines = [
        f"# Review checklist - {art['target_path']}",
        "",
        f"- PR pack: `{pack_id}`  ",
        f"- Artifact: `{art['artifact_id']}` (run `{art['run_id']}`)  ",
        f"- Source object: `{art['object_id']}` @ `{art['object_code_hash']}`  ",
        "- Nothing in this pack has been applied to any environment. Promotion requires a named reviewer",
        "  decision on every change, zero open P1 issues and passing generated tests (convert_exit gate).",
        "",
        "## AI changes",
        "",
    ]
    if not changes:
        lines += ["No remediation rule applied to this artifact.", ""]
    for c in changes:
        flag = " **(below review floor - mandatory review)**" if c.below_floor else ""
        lines += [
            f"### `{c.change_id}` - lines {c.line_start}-{c.line_end}{flag}",
            "",
            f"- Rules: {', '.join(c.rule_ids) or '(none - model proposal)'}",
            f"- Issues: {', '.join(c.issue_ids)} ({', '.join(c.issue_codes)})",
            f"- Confidence: {c.confidence:.2f} - model `{c.model_id}` - prompt `{c.prompt_template}`",
            f"- Rationale: {c.rationale}",
            f"- Diff: `changes/{c.change_id}.diff`; tests: {', '.join(f'`{t}`' for t in c.tests)}",
            "",
            "- [ ] Business logic preserved (compare with `original/`)",
            "- [ ] Assumptions in the rationale confirmed",
            "- [ ] Generated tests pass",
            f"- Decide: `altitude conversion review --change {c.change_id} --reviewer <name> --decision approved|rejected|modified`",
            "",
        ]
    lines += ["## Unresolved issues (no rule; manual fix or recorded acceptance required)", ""]
    if not unresolved:
        lines.append("None.")
    for i in unresolved:
        lines.append(f"- [ ] `{i['issue_id']}` {i['severity']} {i['code']} (line {i['line']}): {i['message']}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- running pack tests


@dataclass
class TestReport:
    total: int
    passed: int
    failures: dict[str, str]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 1.0


def run_pack_tests(pack_dir: Path, change_ids: set[str] | None = None) -> TestReport:
    """Import the pack's generated tests and run them in-process (no pytest dependency)."""
    failures: dict[str, str] = {}
    total = passed = 0
    wanted = {_fn(c) for c in change_ids} if change_ids is not None else None
    for path in sorted((Path(pack_dir) / "tests").glob("test_*.py")):
        name = f"altitude_pack_{content_hash(str(path), 8)}"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        no_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(name, None)
            sys.dont_write_bytecode = no_bytecode
        for attr in sorted(dir(module)):
            if not attr.startswith("test_"):
                continue
            if wanted is not None and not any(attr.startswith(f"test_{w}_") for w in wanted):
                continue
            total += 1
            try:
                getattr(module, attr)()
                passed += 1
            except Exception:  # a failing generated test is data, not a crash
                failures[attr] = traceback.format_exc(limit=1).strip().splitlines()[-1]
    return TestReport(total, passed, failures)
