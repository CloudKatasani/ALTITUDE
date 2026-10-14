"""Synthetic Snowflake estates with seeded issues and ground truth.

Used by tests and demos in place of a live account. The table layouts in
:mod:`altitude.synthetic.schema` are the *harvest contract*: the live harvester
selects exactly these columns from ``SNOWFLAKE.ACCOUNT_USAGE`` (and client
inputs / BI metadata), so every detector runs unchanged on real or synthetic
snapshots.
"""

from .schema import HARVEST_SCHEMA  # noqa: F401
from .snowflake_account import AccountSpec, SyntheticAccount, build_snapshot, generate  # noqa: F401
