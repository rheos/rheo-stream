"""The bootstrap every ``rheo`` subcommand shares: settings, the data root, the
storage backend, the operation registry.

Called from inside a subcommand's handler and never from the parser or the
no-subcommand path: ``rheo`` with no arguments prints usage and returns without
resolving settings, creating a data root, or touching a database
(``tests/test_git_clean.py`` diffs the working tree around exactly that call).
"""

from dataclasses import dataclass
from pathlib import Path

from rheo_core.operations import register_core_operations
from rheo_core.secrets import check_env_references
from rheo_core.settings import ResolvedSettings, resolve
from rheo_core.storage.data_root import (
    find_checkout_root,
    resolve_data_root,
    validate_data_root,
)
from rheo_core.storage.postgres import PostgresBackend, get_backend


@dataclass(frozen=True, slots=True)
class Bootstrap:
    settings: ResolvedSettings
    data_root: Path
    backend: PostgresBackend


def data_root() -> Path:
    """Resolve and validate the data root (creating it if absent)."""
    resolution = resolve_data_root()
    return validate_data_root(
        resolution.path,
        find_checkout_root(),
        explicitly_named=resolution.explicitly_named,
    )


def bootstrap() -> Bootstrap:
    """Settings, then the data root, then the env-reference check, then the backend
    and the registry — the same order as the ``core`` process's startup."""
    settings = resolve()
    root = data_root()
    check_env_references(settings)
    backend = get_backend()
    register_core_operations()
    return Bootstrap(settings, root, backend)
