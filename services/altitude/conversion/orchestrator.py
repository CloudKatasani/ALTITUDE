"""Conversion orchestrator: runs a converter and records the canonical conversion entities.

One ``conversion_run`` per invocation; one ``converted_artifact`` per source file, linked to the
``source_object`` and its ``object_version`` (code hash); one ``conversion_issue`` (+ detail) per EWI/FDM/PRF.
SnowConvert AI is used when its CLI is installed; otherwise the sqlglot fallback converter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from altitude.core import audit
from altitude.core.ids import content_hash, stable_id
from altitude.core.rubric import RubricSet, default_rubrics

from . import factory
from .fallback import SqlglotConverter, normalise_dialect
from .models import ConversionOutput, ConvertedFile
from .snowconvert import SnowConvertCLI

AGENT_ID = "altitude.conversion.orchestrator"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class RunResult:
    run_id: str
    tool: str
    tool_version: str
    output_dir: Path
    artifact_ids: list[str] = field(default_factory=list)
    issue_count: int = 0


def select_converter(snowconvert: SnowConvertCLI | None = None) -> SnowConvertCLI | SqlglotConverter:
    """SnowConvert AI when installed, otherwise the sqlglot fallback."""
    cli = snowconvert if snowconvert is not None else SnowConvertCLI()
    return cli if cli.available else SqlglotConverter()


class ConversionOrchestrator:
    def __init__(self, store: Any, engagement_id: str, *, rubrics: RubricSet | None = None,
                 converter: SnowConvertCLI | SqlglotConverter | None = None, source_system_id: str = "source"):
        self.store = store
        self.engagement_id = engagement_id
        self.rubrics = rubrics or default_rubrics()
        self.converter = converter or select_converter()
        self.source_system_id = source_system_id

    # ------------------------------------------------------------------ run
    def run(self, source_dir: Path, dialect: str, output_dir: Path) -> RunResult:
        dialect = normalise_dialect(dialect)
        source_dir, output_dir = Path(source_dir), Path(output_dir)
        files = sorted(p for p in source_dir.rglob("*") if p.is_file())
        input_hash = content_hash([[p.relative_to(source_dir).as_posix(), p.read_text(errors="replace")] for p in files])
        n_runs = self.store.scalar("SELECT count(*) FROM conversion_run WHERE engagement_id=?", [self.engagement_id])
        tool = self.converter.name
        run_id = stable_id("CRUN", self.engagement_id, tool, dialect, input_hash, int(n_runs or 0), length=10)
        run_dir = output_dir / run_id
        self.store.insert("conversion_run", {
            "run_id": run_id, "engagement_id": self.engagement_id, "tool": tool, "tool_version": None,
            "started_at": _now(), "status": "running",
        })
        try:
            if isinstance(self.converter, SnowConvertCLI):
                out = self.converter.convert(source_dir, dialect, run_dir / "_snowconvert")
            else:
                out = self.converter.convert(source_dir, dialect)
        except Exception:
            self.store.update("conversion_run", {"run_id": run_id}, {"status": "failed", "completed_at": _now()})
            raise
        result = RunResult(run_id, out.tool, out.tool_version, run_dir)
        self._record(out, run_id, run_dir, result)
        self.store.update("conversion_run", {"run_id": run_id},
                          {"status": "completed", "completed_at": _now(), "tool_version": out.tool_version})
        audit.record(self.store, AGENT_ID, "conversion.run", actor_type="agent", subject_type="conversion_run",
                     subject_id=run_id, details={"tool": out.tool, "version": out.tool_version, "dialect": dialect,
                                                 "artifacts": len(result.artifact_ids), "issues": result.issue_count})
        return result

    # ------------------------------------------------------------------ persistence
    def _object_for(self, cf: ConvertedFile) -> tuple[str, str]:
        code_hash = content_hash(cf.source_text)
        stem = PurePosixPath(cf.source_rel).stem
        found = self.store.query(
            "SELECT object_id FROM source_object WHERE engagement_id=? AND (fq_name=? OR lower(fq_name)=lower(?)) "
            "ORDER BY object_id LIMIT 1",
            [self.engagement_id, cf.source_rel, stem],
        )
        if found:
            object_id = found[0]["object_id"]
        else:
            object_id = stable_id("OBJ", self.engagement_id, self.source_system_id, cf.source_rel)
            if not self.store.get("source_object", object_id=object_id):
                self.store.insert("source_object", {
                    "object_id": object_id, "engagement_id": self.engagement_id,
                    "source_system_id": self.source_system_id, "object_type": "script",
                    "fq_name": cf.source_rel, "code_hash": code_hash,
                    "loc": len(cf.source_text.splitlines()), "harvested_at": _now(),
                })
        if not self.store.get("object_version", object_id=object_id, code_hash=code_hash):
            self.store.insert("object_version", {"object_id": object_id, "code_hash": code_hash,
                                                 "source_text": cf.source_text, "harvested_at": _now()})
        return object_id, code_hash

    def _record(self, out: ConversionOutput, run_id: str, run_dir: Path, result: RunResult) -> None:
        tool_conf = float(self.rubrics.get(f"rubric.conversion.tool_confidence.{out.tool}"))
        for cf in out.files:
            object_id, code_hash = self._object_for(cf)
            target = PurePosixPath(cf.source_rel).with_suffix(".sql").as_posix()
            artifact_id = stable_id("ART", run_id, cf.source_rel)
            path = run_dir / "converted" / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(cf.output_text)
            chash = content_hash(cf.output_text)
            self.store.insert("converted_artifact", {
                "artifact_id": artifact_id, "run_id": run_id, "object_id": object_id,
                "object_code_hash": code_hash, "target_path": target, "content_hash": chash,
                "status": "converted",
            })
            self.store.insert("artifact_content", {"artifact_id": artifact_id, "kind": "converted",
                                                   "content_hash": chash, "content": cf.output_text,
                                                   "created_at": _now()})
            issue_rows, detail_rows = [], []
            for n, issue in enumerate(cf.issues):
                issue_id = stable_id("ISS", artifact_id, n, issue.code, issue.source_line, length=10)
                issue_rows.append({"issue_id": issue_id, "artifact_id": artifact_id, "code": issue.code,
                                   "severity": issue.severity, "message": issue.message, "line": issue.line,
                                   "status": "open"})
                detail_rows.append({"issue_id": issue_id, "run_id": run_id, "category": issue.category,
                                    "tool_severity": issue.tool_severity, "source_file": issue.file,
                                    "source_line": issue.source_line, "source_column": issue.column,
                                    "snippet": issue.snippet, "region_end_line": issue.region_end,
                                    "known_issue_id": issue.known_issue,
                                    "detector_id": issue.detector_id})
            self.store.insert("conversion_issue", issue_rows)
            self.store.insert("conversion_issue_detail", detail_rows)
            factory.transition(self.store, engagement_id=self.engagement_id, object_id=object_id,
                               to_state="Converted", actor=AGENT_ID, actor_type="agent",
                               evidence_ref=f"conversion_run:{run_id}/artifact:{artifact_id}",
                               confidence=tool_conf, artifact_id=artifact_id)
            result.artifact_ids.append(artifact_id)
            result.issue_count += len(cf.issues)
        if out.assessment:
            rows = []
            for rec in out.assessment:
                rows.append({"run_id": run_id, **{k: rec.get(k) for k in (
                    "code_unit_id", "file_name", "category", "code_unit", "lines_of_code", "ewi_count",
                    "fdm_count", "prf_count", "highest_ewi_severity", "conversion_status")}})
            self.store.insert("conversion_assessment", rows)
