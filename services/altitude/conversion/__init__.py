"""M5 Conversion orchestrator.

- ``snowconvert``   SnowConvert AI CLI wrapper (binary discovery, version, invocation) + report parser
- ``fallback``      sqlglot transpile converter used when the CLI is not installed
- ``orchestrator``  conversion runs -> ``conversion_run`` / ``converted_artifact`` / ``conversion_issue``
- ``remediation``   AI remediation agent -> ``ai_change`` records and PR packs (never production)
- ``review``        review workflow, convert_exit gate and promotion
- ``factory``       factory state machine transitions (Section 9.2)
"""

from altitude.core.store import register_append_only

register_append_only("conversion_lane_transition")

from .models import ConversionOutput, ConvertedFile, Issue  # noqa: E402

__all__ = ["ConversionOutput", "ConvertedFile", "Issue"]
