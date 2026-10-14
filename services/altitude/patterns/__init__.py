"""Pattern Library v0 (M1) and the open-source semantic-drift checker (Section 10.13).

- ``scan_sql(sql, dialect) -> list[DriftHit]``     static detectors over source code
- ``scan_profile(profile, dialect) -> list[DriftHit]``  profile detectors over metadata/stats
- ``PatternLibrary`` / ``default_library()``       knowledge loaded from ``knowledge/dialects``
- ``run_golden_tests()``                          golden + detector test runner (``altitude patterns test``)
"""

from .library import DIALECTS, PatternLibrary, default_library, normalise_dialect
from .model import CHECKLIST, DriftHit, KnownIssue
from .scan import Scanner, scan_profile, scan_sql

__all__ = [
    "CHECKLIST",
    "DIALECTS",
    "DriftHit",
    "KnownIssue",
    "PatternLibrary",
    "Scanner",
    "default_library",
    "normalise_dialect",
    "scan_profile",
    "scan_sql",
]
