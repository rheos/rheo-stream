"""``PostgresOverrideSource``: C2's ``OverrideSource`` protocol over the
``core.workspace_setting`` and ``core.member_setting`` rows.

The resolver hands it a workspace id (and an account id for member rows); this class
routes exactly as the storage layer does — the registry row is read on every call and
the workspace must be ``active`` — and reads the rows through the workspace
repositories inside a ``UnitOfWork``, so the test-profile ``current_database()``
assertion covers the settings read too. The protocol is C2's contract and is not
changed here.

Deliberately not re-exported from ``rheo_core.settings``: that package must not
import the storage layer at module level (the storage layer imports it).
"""

from collections.abc import Mapping
from types import MappingProxyType
from uuid import UUID

from rheo_core.settings.resolver import OverrideSource
from rheo_core.storage.backend import UnitOfWork
from rheo_core.storage.postgres import PostgresBackend, get_backend
from rheo_core.storage.repositories import member_settings, workspace_settings
from rheo_core.storage.routing import active_workspace


class PostgresOverrideSource:
    """Override rows from the workspace's own database."""

    def __init__(self, backend: PostgresBackend | None = None) -> None:
        self._backend = backend

    def _open(self, workspace_id: UUID) -> UnitOfWork:
        backend = self._backend if self._backend is not None else get_backend()
        row = active_workspace(workspace_id)
        return UnitOfWork(
            backend.pools.engine_for(row.database_name), row.database_name
        )

    def workspace_overrides(self, workspace_id: UUID) -> Mapping[str, str]:
        with self._open(workspace_id) as uow:
            return MappingProxyType(workspace_settings(uow.connection))

    def member_overrides(
        self, workspace_id: UUID, account_id: UUID
    ) -> Mapping[str, str]:
        with self._open(workspace_id) as uow:
            return MappingProxyType(member_settings(uow.connection, account_id))


_PROTOCOL_CHECK: type[OverrideSource] = PostgresOverrideSource
