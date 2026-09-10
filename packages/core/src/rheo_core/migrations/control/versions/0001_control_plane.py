"""The control plane, whole: all ten ratified tables (A1).

Revision ID: 0001_control_plane
Revises: (base)

Creates ``account``, ``identity``, ``workspace``, ``membership``, ``session``,
``session_secret``, ``session_grant``, ``access_token``, ``access_token_operation`` and
``identity_provider`` from the ``Table`` objects in
``rheo_core.storage.control_tables``. This revision is never edited after run 0b1;
later control-plane changes append revisions. Downgrade is not supported in release
one.
"""

from collections.abc import Sequence

from alembic import op
from rheo_core.storage.control_tables import control_metadata

revision: str = "0001_control_plane"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ``checkfirst=False``: a table already present means this chain is running
    # against a database it does not own, which must fail loudly, never skip.
    control_metadata.create_all(op.get_bind(), checkfirst=False)


def downgrade() -> None:
    raise NotImplementedError("downgrade is not supported in release one")
