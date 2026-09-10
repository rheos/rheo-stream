"""Alembic environment for the ``control`` chain.

Runs only under the orchestrator's connection and refuses otherwise; the rule and
its reasons are stated once, in ``rheo_core.migrations``. The version table lives
inside the chain's own schema, ``control.alembic_version_control``.
"""

from alembic import context
from rheo_core.storage.control_tables import (
    CONTROL_SCHEMA,
    CONTROL_VERSION_TABLE,
    control_metadata,
)

connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError(
        "the control migration chain runs only through "
        "rheo_core.migrations.orchestrator: no connection was provided, so nothing "
        "will be upgraded (alembic invoked by hand has no URL and no connection)"
    )

context.configure(
    connection=connection,
    target_metadata=control_metadata,
    version_table=CONTROL_VERSION_TABLE,
    version_table_schema=CONTROL_SCHEMA,
)

with context.begin_transaction():
    context.run_migrations()
