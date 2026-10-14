"""Minimal dbt compile + run + test harness (dbt itself is not a dependency).

- **compile**: renders every model with jinja2, implementing ``ref()``, ``source()``, ``config()``,
  ``var()``, ``is_incremental()`` and ``this``; resolves model dependencies (unknown refs/sources fail);
  validates ``doc()`` references in YAML descriptions and parses macros. Output is Snowflake SQL.
- **run**: executes models in dependency order in DuckDB (Snowflake SQL transpiled with sqlglot),
  materialised as views or tables per ``config()`` / ``dbt_project.yml``.
- **test**: runs the generic tests declared in YAML (``unique``, ``not_null``, ``accepted_values``,
  ``relationships``) on models and returns failing-row counts.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import jinja2
import sqlglot
import yaml

from altitude.core.errors import AltitudeError

from . import kb


class CompileError(AltitudeError):
    """A model or YAML file failed to render or references something undefined."""


@dataclass
class TestResult:
    name: str
    model: str
    column: str
    test: str
    failures: int
    sql: str

    @property
    def passed(self) -> bool:
        return self.failures == 0


@dataclass
class RunResult:
    compiled: dict[str, str]
    order: list[str]
    built: list[str] = field(default_factory=list)
    tests: list[TestResult] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors and all(t.passed for t in self.tests)

    @property
    def failed_tests(self) -> list[TestResult]:
        return [t for t in self.tests if not t.passed]


class DbtHarness:
    def __init__(self, files: dict[str, str] | None = None, project_dir: Path | None = None):
        if files is None:
            if project_dir is None:
                raise ValueError("files or project_dir required")
            files = {p.relative_to(project_dir).as_posix(): p.read_text()
                     for p in Path(project_dir).rglob("*") if p.is_file()}
        self.files = files
        self.project = yaml.safe_load(files["dbt_project.yml"]) or {}
        self.schema = kb.conventions()["project"]["model_schema"]
        self.models = {Path(p).stem: (p, sql) for p, sql in files.items()
                       if p.startswith("models/") and p.endswith(".sql")}
        self.yml = {p: yaml.safe_load(c) or {} for p, c in files.items() if p.endswith((".yml", ".yaml"))
                    and p.startswith("models/")}
        self.sources: dict[tuple[str, str], dict] = {}
        self.model_meta: dict[str, dict] = {}
        for doc in self.yml.values():
            for src in doc.get("sources", []) or []:
                for t in src.get("tables", []) or []:
                    self.sources[(src["name"], t["name"])] = {"schema": src.get("schema", src["name"]),
                                                              "identifier": t.get("identifier", t["name"]), **t}
            for m in doc.get("models", []) or []:
                self.model_meta[m["name"]] = m
        self.docs = {}
        for p, content in files.items():
            if p.endswith(".md"):
                for name, body in re.findall(r"{%\s*docs\s+(\w+)\s*%}(.*?){%\s*enddocs\s*%}", content, re.S):
                    self.docs[name] = body.strip()
        self.env = jinja2.Environment(undefined=jinja2.StrictUndefined, extensions=["jinja2.ext.do"],
                                      keep_trailing_newline=True)

    # ------------------------------------------------------------------ compile
    def _render(self, name: str, sql: str) -> tuple[str, set[str], dict]:
        deps: set[str] = set()
        cfg: dict[str, Any] = {}
        variables = self.project.get("vars") or {}

        def ref(model: str) -> str:
            if model not in self.models:
                raise CompileError(f"{name}: ref('{model}') does not exist")
            deps.add(model)
            return f"{self.schema}.{model}"

        def source(src: str, table: str) -> str:
            meta = self.sources.get((src, table))
            if meta is None:
                raise CompileError(f"{name}: source('{src}', '{table}') is not declared")
            return f"{meta['schema']}.{meta['identifier']}"

        def config(**kw: Any) -> str:
            cfg.update(kw)
            return ""

        def var(key: str, default: Any = None) -> Any:
            if key in variables and variables[key] is not None:
                return variables[key]
            if default is None:
                raise CompileError(f"{name}: var('{key}') has no value")
            return default

        try:
            rendered = self.env.from_string(sql).render(
                ref=ref, source=source, config=config, var=var, is_incremental=lambda: False,
                this=f"{self.schema}.{name}")
        except jinja2.TemplateError as e:
            raise CompileError(f"{name}: {e}") from e
        return rendered, deps, cfg

    def compile(self) -> tuple[dict[str, str], list[str], dict[str, dict]]:
        compiled, deps, cfgs = {}, {}, {}
        for name, (_, sql) in self.models.items():
            compiled[name], deps[name], cfgs[name] = self._render(name, sql)
        for path, content in self.files.items():
            if path.startswith("macros/") and path.endswith(".sql"):
                try:
                    self.env.parse(content)
                except jinja2.TemplateSyntaxError as e:
                    raise CompileError(f"{path}: {e}") from e
        for meta in self.model_meta.values():
            self._check_docs(meta.get("description", ""))
            for col in meta.get("columns", []) or []:
                self._check_docs(col.get("description", ""))
            if meta["name"] not in self.models:
                raise CompileError(f"YAML documents model {meta['name']} which has no SQL file")
        return compiled, self._toposort(deps), cfgs

    def _check_docs(self, text: str) -> None:
        for name in re.findall(r"doc\(\s*['\"](\w+)['\"]\s*\)", text or ""):
            if name not in self.docs:
                raise CompileError(f"doc('{name}') is not defined in any docs block")

    @staticmethod
    def _toposort(deps: dict[str, set[str]]) -> list[str]:
        indeg = {m: len(d) for m, d in deps.items()}
        users: dict[str, list[str]] = {m: [] for m in deps}
        for m, ds in deps.items():
            for d in ds:
                users[d].append(m)
        queue = deque(sorted(m for m, n in indeg.items() if n == 0))
        order = []
        while queue:
            m = queue.popleft()
            order.append(m)
            for u in sorted(users[m]):
                indeg[u] -= 1
                if indeg[u] == 0:
                    queue.append(u)
        if len(order) != len(deps):
            raise CompileError(f"dependency cycle among models {sorted(set(deps) - set(order))}")
        return order

    def _materialization(self, name: str, cfg: dict) -> str:
        if cfg.get("materialized"):
            return cfg["materialized"]
        path = self.models[name][0]
        conf = (self.project.get("models") or {}).get(self.project.get("name"), {}) or {}
        for folder, settings in conf.items():
            if isinstance(settings, dict) and f"models/{folder}/" in path:
                return settings.get("+materialized", "view")
        return "view"

    # ------------------------------------------------------------------ run + test
    def run(self, con: duckdb.DuckDBPyConnection) -> RunResult:
        compiled, order, cfgs = self.compile()
        result = RunResult(compiled, order)
        con.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
        for name in order:
            try:
                body = sqlglot.transpile(compiled[name], read="snowflake", write="duckdb")
                if len(body) != 1:
                    raise CompileError(f"{name}: expected one SELECT, got {len(body)} statements")
                kind = "TABLE" if self._materialization(name, cfgs[name]) in ("table", "incremental") else "VIEW"
                con.execute(f"CREATE OR REPLACE {kind} {self.schema}.{name} AS {body[0]}")
                result.built.append(name)
            except (duckdb.Error, sqlglot.errors.SqlglotError, CompileError) as e:
                result.errors[name] = str(e).splitlines()[0]
        for name in result.built:
            for test in self._tests_for(name):
                try:
                    failures = con.execute(f"SELECT count(*) FROM ({test.sql})").fetchone()[0]
                except duckdb.Error as e:
                    result.errors[test.name] = str(e).splitlines()[0]
                    continue
                test.failures = int(failures)
                result.tests.append(test)
        return result

    def _tests_for(self, model: str) -> list[TestResult]:
        meta = self.model_meta.get(model) or {}
        rel = f"{self.schema}.{model}"
        out = []
        for col in meta.get("columns", []) or []:
            c = col["name"]
            for t in (col.get("data_tests") or col.get("tests") or []):
                kind, args = (t, {}) if isinstance(t, str) else next(iter(t.items()))
                args = args or {}
                if kind == "unique":
                    sql = f"SELECT {c} FROM {rel} WHERE {c} IS NOT NULL GROUP BY {c} HAVING count(*) > 1"
                elif kind == "not_null":
                    sql = f"SELECT {c} FROM {rel} WHERE {c} IS NULL"
                elif kind == "accepted_values":
                    vals = ", ".join("'" + str(v).replace("'", "''") + "'" for v in args.get("values", []))
                    sql = f"SELECT {c} FROM {rel} WHERE {c} IS NOT NULL AND CAST({c} AS VARCHAR) NOT IN ({vals})"
                elif kind == "relationships":
                    m = re.match(r"ref\(\s*['\"](\w+)['\"]\s*\)", args.get("to", ""))
                    if not m:
                        raise CompileError(f"{model}.{c}: relationships 'to' must be ref('model')")
                    parent, fld = f"{self.schema}.{m.group(1)}", args["field"]
                    sql = (f"SELECT child.{c} FROM {rel} AS child LEFT JOIN {parent} AS parent "
                           f"ON child.{c} = parent.{fld} WHERE child.{c} IS NOT NULL AND parent.{fld} IS NULL")
                else:
                    raise CompileError(f"{model}.{c}: unsupported test {kind!r}")
                out.append(TestResult(f"{kind}_{model}_{c}", model, c, kind, -1, sql))
        return out
