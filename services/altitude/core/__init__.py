"""Core primitives shared by every ALTITUDE module.

- ``paths``      repository/knowledge locations
- ``rubric``     rubric values resolved by reference (no thresholds in code)
- ``knowledge``  knowledge-as-data loader and schema validator
- ``store``      canonical data model (control plane) with append-only guards
- ``snapshot``   immutable, content-addressed snapshots
- ``ai``         AI inference records, providers and the review queue
- ``generated``  header-stamped generated artifacts
- ``theme``      white-label tokens
- ``audit``      audit events
"""
