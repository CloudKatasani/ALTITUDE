"""Skill manifest loading, validation and invocation."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import jsonschema
import yaml

from altitude.core.errors import AltitudeError
from altitude.core.paths import repo_root

MANIFEST_SCHEMA = {
    "type": "object",
    "required": ["name", "description", "permission", "entrypoint", "input_schema"],
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
        "description": {"type": "string", "minLength": 10},
        "permission": {"enum": ["read", "run", "review", "approve"]},
        "entrypoint": {"type": "string", "pattern": "^[a-zA-Z0-9_.]+:[a-zA-Z0-9_]+$"},
        "input_schema": {"type": "object"},
        "milestone": {"type": "string"},
    },
}


class SkillError(AltitudeError):
    pass


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    permission: str
    entrypoint: str
    input_schema: dict = field(hash=False, compare=False)

    def resolve(self) -> Callable[..., Any]:
        mod, fn = self.entrypoint.split(":")
        return getattr(importlib.import_module(mod), fn)

    @property
    def available(self) -> bool:
        try:
            self.resolve()
            return True
        except (ImportError, AttributeError):
            return False

    def tool_spec(self) -> dict:
        return {"name": self.name, "description": self.description, "inputSchema": self.input_schema}


def skills_dir() -> Path:
    return repo_root() / "skills"


@lru_cache(maxsize=1)
def load_skills() -> dict[str, Skill]:
    out: dict[str, Skill] = {}
    problems = []
    for path in sorted(skills_dir().glob("*.yaml")):
        doc = yaml.safe_load(path.read_text())
        errs = sorted(jsonschema.Draft202012Validator(MANIFEST_SCHEMA).iter_errors(doc), key=str)
        if errs:
            problems.extend(f"{path.name}: {e.message}" for e in errs)
            continue
        jsonschema.Draft202012Validator.check_schema(doc["input_schema"])
        if doc["name"] in out:
            problems.append(f"{path.name}: duplicate skill {doc['name']}")
        out[doc["name"]] = Skill(doc["name"], doc["description"], doc["permission"], doc["entrypoint"],
                                 doc["input_schema"])
    if problems:
        raise SkillError("invalid skill manifests:\n  " + "\n  ".join(problems))
    return out


def run_skill(name: str, arguments: dict | None, context: Any = None, principal: Any = None) -> Any:
    skills = load_skills()
    if name not in skills:
        raise SkillError(f"unknown skill {name!r}")
    skill = skills[name]
    if principal is not None and not principal.can(skill.permission):
        raise SkillError(f"role '{principal.role}' lacks permission '{skill.permission}' for skill {name}")
    args = dict(arguments or {})
    try:
        jsonschema.validate(args, skill.input_schema)
    except jsonschema.ValidationError as e:
        raise SkillError(f"invalid arguments for {name}: {e.message}") from None
    return skill.resolve()(context=context, **args)
