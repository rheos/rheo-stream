"""Alembic environment for the per-workspace ``core`` chain.

Runs only under the orchestrator's connection (to one workspace database, after its
``current_database()`` assertion) and refuses otherwise; the rule and its reasons are
stated once, in ``rheo_core.migrations``. The version table lives inside the chain's
own schema, ``core.alembic_version_core``.
"""

from alembic import context
from rheo_core.storage.core_tables import (
    CORE_SCHEMA,
    CORE_VERSION_TABLE,
    core_metadata,
)

connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError(
        "the core migration chain runs only through "
        "rheo_core.migrations.orchestrator: no connection was provided, so nothing "
        "will be upgraded (alembic invoked by hand has no URL and no connection)"
    )

context.configure(
    connection=connection,
    target_metadata=core_metadata,
    version_table=CORE_VERSION_TABLE,
    version_table_schema=CORE_SCHEMA,
)

with context.begin_transaction():
    context.run_migrations()
