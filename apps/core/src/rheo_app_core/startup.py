"""The ``core`` process's startup sequence, run once from the FastAPI ``lifespan``.

In order: settings → data root → the ``secret://env/*`` reference check → ensure the
control database and run the ``control`` chain → migrate active workspaces serially
→ build the operation registry. "Ensure the control database" treats psycopg's
``DuplicateDatabase`` as success (``PostgresBackend.ensure_database``), mirroring
provisioning's "already exists is a retry": the advisory lock covers the migration
chain, not the ``CREATE DATABASE`` before it, and at ``make demo`` this lifespan and
the host-side ``rheo migrate`` start within seconds of each other against one
cluster. A workspace whose chain fails is marked ``unavailable`` by the orchestrator
and startup completes; a control-chain failure raises, because without the control
plane nothing is routable.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from rheo_core.migrations.orchestrator import (
    MigrationResult,
    migrate_active_workspaces,
    migrate_control,
)
from rheo_core.operations import register_core_operations
from rheo_core.secrets import check_env_references
from rheo_core.settings import PROFILE_KEY, resolve
from rheo_core.storage.data_root import (
    find_checkout_root,
    resolve_data_root,
    validate_data_root,
)
from rheo_core.storage.postgres import get_backend

logger = logging.getLogger("rheo_app_core.startup")


@dataclass(frozen=True, slots=True)
class StartupReport:
    """What startup did, kept on ``app.state.startup`` for diagnostics."""

    profile: str
    data_root: Path
    env_references: tuple[str, ...]
    control_database: str
    workspaces: tuple[MigrationResult, ...]
    operations: tuple[str, ...]


def run_startup() -> StartupReport:
    """The sequence in the module docstring; blocking, run off the event loop."""
    settings = resolve()
    resolution = resolve_data_root()
    root = validate_data_root(
        resolution.path,
        find_checkout_root(),
        explicitly_named=resolution.explicitly_named,
    )
    env_references = check_env_references(settings)
    backend = get_backend()
    control = migrate_control(backend)
    workspaces = migrate_active_workspaces(backend)
    operations = tuple(sorted(op.name for op in register_core_operations()))
    report = StartupReport(
        profile=settings.get_str(PROFILE_KEY),
        data_root=root,
        env_references=env_references,
        control_database=control.database_name,
        workspaces=workspaces,
        operations=operations,
    )
    logger.info(
        "core_startup_complete",
        extra={
            "profile": report.profile,
            "data_root": str(root),
            "control_database": report.control_database,
            "workspaces_migrated": sum(1 for w in workspaces if w.ok),
            "workspaces_unavailable": sum(1 for w in workspaces if not w.ok),
            "operations": len(operations),
        },
    )
    return report
