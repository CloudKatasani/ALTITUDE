"""M7 Foundation accelerators (Section 15.2): landing-zone model -> Terraform, and the Well-Architected checker.

- ``landing_zone``  load/expand/validate ``knowledge/foundation/landing_zone.yaml``
- ``terraform``     deterministic Snowflake-provider HCL renderer
- ``tflint``        structural linter for the generated Terraform (no terraform binary required)
- ``wa``            WA-* checks (Section 14.9 format) over a sealed snapshot, with remediation playbooks
"""
