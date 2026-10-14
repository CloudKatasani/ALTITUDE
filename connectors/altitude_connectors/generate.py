"""Renderings of the published permission manifests (principle 8).

``generate()`` follows the ``altitude.<module>.generate`` contract and returns
``{"connectors/<source>_permissions.md": ..., "connectors/<source>_grants.sql": ...}``.
It is not yet listed in ``altitude.core.generated.GENERATOR_MODULES`` (core
change requested); until then it is used by ``altitude connectors manifest
--format grants`` and tests.
"""

from __future__ import annotations

from altitude.core.generated import stamp

from .manifest import Manifest, available_sources, load_manifest

_COMMENT = {"tsql": "--", "oracle": "--", "teradata": "--"}


def grant_script(m: Manifest) -> str:
    c = _COMMENT.get(m.dialect, "--")
    lines = [f"{c} Read-only grants for the extraction agent ({m.id} v{m.version}, {m.source}).",
             f"{c} Principal: {m.doc['principal']['name']} ({m.doc['principal']['kind']}). No write privilege is requested."]
    for g in m.grants:
        lines.append("")
        lines.append(f"{c} {g['privilege']} ON {g['on']}{' (optional)' if g.get('optional') else ''}: {g['why']}")
        lines.append(g.get("grant_sql") or f"{c} (granted by the platform administrator; no SQL form)")
    return "\n".join(lines) + "\n"


def permissions_markdown(m: Manifest) -> str:
    out = [f"# Permission manifest — {m.source} ({m.id} v{m.version})", "", m.doc.get("description", "").strip(), "",
           f"Principal: `{m.doc['principal']['name']}` ({m.doc['principal']['kind']}). Row data read: **never**.", "",
           "## Required grants", "", "| Privilege | On | Why | Optional |", "|---|---|---|---|"]
    for g in m.grants:
        out.append(f"| {g['privilege']} | {g['on']} | {g['why']} | {'yes' if g.get('optional') else 'no'} |")
    out += ["", "## Objects read", "", "| Object | Contains | Why |", "|---|---|---|"]
    for o in m.doc["objects_read"]:
        out.append(f"| `{o['name']}` | {o['contains']} | {o['why']} |")
    if m.doc.get("files_read"):
        out += ["", "## Files read", ""] + [f"- `{f['glob']}` — {f['why']}" for f in m.doc["files_read"]]
    if m.doc.get("never_shipped"):
        out += ["", "## Never shipped", ""] + [f"- {x}" for x in m.doc["never_shipped"]]
    return "\n".join(out) + "\n"


def generate() -> dict[str, str]:
    out = {}
    for source in available_sources():
        m = load_manifest(source)
        src = f"knowledge/connectors/{source}.yaml"
        out[f"connectors/{source}_permissions.md"] = stamp(permissions_markdown(m), ".md", src)
        out[f"connectors/{source}_grants.sql"] = stamp(grant_script(m), ".sql", src)
    return out
