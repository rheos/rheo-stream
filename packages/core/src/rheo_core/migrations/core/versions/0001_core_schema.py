"""The six core-owned tables of a workspace database.

Revision ID: 0001_core_schema
Revises: (base)

Creates exactly ``workspace_composition``, ``module_state``, ``module_schema_version``,
``workspace_setting``, ``member_setting`` and ``member_credential`` from the ``Table``
objects in ``rheo_core.storage.core_tables``, and no seventh: the outbox, event,
job, schedule, operation, audit and approval tables are later chain steps owned by
run 0c (the hard 0c boundary). This revision is never edited after run 0b1. Downgrade
is not supported in release one.
"""

from collections.abc import Sequence

from alembic import op
from rheo_core.storage.core_tables import core_metadata

revision: str = "0001_core_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ``checkfirst=False``: a table already present means this chain is running
    # against a database it does not own, which must fail loudly, never skip.
    core_metadata.create_all(op.get_bind(), checkfirst=False)


def downgrade() -> None:
    raise NotImplementedError("downgrade is not supported in release one")
