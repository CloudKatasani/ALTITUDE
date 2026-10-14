"""Generated renderings for M7: landing-zone Terraform and the Well-Architected check SQL."""

from __future__ import annotations

from altitude.core.generated import stamp

from . import landing_zone, terraform, wa

LZ_SOURCE = "knowledge/foundation/landing_zone.yaml"


def terraform_files() -> dict[str, str]:
    """Unstamped Terraform files ({filename: hcl}) for the default landing zone."""
    return terraform.build(landing_zone.load())


def generate() -> dict[str, str]:
    out = {f"foundation/terraform/{name}": stamp(body, ".tf", LZ_SOURCE) for name, body in terraform_files().items()}
    for c in wa.load_checks():
        rel = wa.query_ref(c["id"]).removeprefix("generated/")
        header = (f"-- {c['id']} ({c['section']} {c['pillar']}, {c['severity']}): {c['title']}\n"
                  f"-- threshold: {c.get('threshold_ref', 'n/a')}; playbook: {c['remediation']['playbook']}; "
                  f"autonomy: {c['remediation']['autonomy']}\n")
        out[rel] = stamp(header + c["query"].rstrip() + ";\n", ".sql", f"knowledge/{c['_source']}")
    return out
