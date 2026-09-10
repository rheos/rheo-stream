"""The storage backend protocol, the unit of work, and the storage refusals.

``UnitOfWork`` is one SQLAlchemy ``Connection`` in one transaction against one
workspace database, with ``commit()`` and ``rollback()`` and nothing else. It has no
outbox slot and no audit writer, typed or ``None``-typed: that is the hard 0c boundary
in concrete form. 0c0 adds whatever it needs, and adding attributes here later never
changes the ``(ctx, uow, input)`` handler signature, so there is nothing to pre-shape.

The unit of work takes an **engine and the expected database name**, not a context.
``routing.open_unit_of_work(ctx)`` composes ``route(ctx)`` with it; the split is what
lets the storage tests drive the unit of work from an engine, because no test may
hand-build a ``WorkspaceContext``. Under ``profile = test`` ``__enter__`` asserts
``SELECT current_database()`` equals the expected name once per unit of work (the
profile is resolved once, by the backend: see ``UnitOfWork.verify_database``); that
assertion plus the registry read in ``route()`` are the backstop for the run's worst
silent failure, a write landing in the wrong workspace database.
"""

from collections.abc import Callable, Sequence
from types import TracebackType
from typing import TYPE_CHECKING, ClassVar, Final, Protocol, Self
from uuid import UUID

from rheo_contracts import WorkspaceContext
from sqlalchemy import Connection, Engine, text
from sqlalchemy.engine import Transaction

if TYPE_CHECKING:
    from rheo_core.migrations.orchestrator import MigrationResult

WORKSPACE_UNAVAILABLE: Final = "workspace_unavailable"
WORKSPACE_MISSING: Final = "workspace_missing"
WORKSPACE_EXISTS: Final = "workspace_exists"
WORKSPACE_STATE: Final = "workspace_state"
ACCOUNT_MISSING: Final = "account_missing"
IDENTITY_EXISTS: Final = "identity_exists"
SLUG_TAKEN: Final = "slug_taken"
DATABASE_MISMATCH: Final = "database_mismatch"
SCHEMA_AHEAD: Final = "schema_ahead"
UNIT_OF_WORK_CLOSED: Final = "unit_of_work_closed"


class StorageRefusal(Exception):
    """A storage refusal. ``state`` names it; ``detail`` never carries a secret.

    ``workspace_state`` is set for ``workspace_unavailable`` and names the registry
    state that caused the refusal (``provisioning``, ``unavailable``, ...).
    """

    def __init__(
        self, state: str, detail: str, *, workspace_state: str | None = None
    ) -> None:
        super().__init__(f"{state}: {detail}")
        self.state = state
        self.detail = detail
        self.workspace_state = workspace_state


class UnitOfWork:
    """One connection, one transaction, one workspace database."""

    __slots__ = ("_connection", "_engine", "_expected_database", "_transaction")

    verify_database: ClassVar[bool] = False
    """Whether ``__enter__`` probes ``current_database()`` against the expected name.

    ``PostgresBackend`` sets this once at construction from the resolved profile: on
    under ``test``, off otherwise. A class-level flag rather than a per-transaction
    ``current_profile()`` call, because that helper re-reads ``deployment.toml`` and
    the environment on every call, which would be a file read per database
    transaction in production.
    """

    def __init__(self, engine: Engine, expected_database: str) -> None:
        if not isinstance(expected_database, str) or not expected_database:
            raise TypeError("UnitOfWork needs the expected database name")
        self._engine = engine
        self._expected_database = expected_database
        self._connection: Connection | None = None
        self._transaction: Transaction | None = None

    def __enter__(self) -> Self:
        if self._connection is not None:
            raise StorageRefusal(UNIT_OF_WORK_CLOSED, "a unit of work is entered once")
        connection = self._engine.connect()
        transaction = connection.begin()
        if UnitOfWork.verify_database:
            actual = str(
                connection.execute(text("SELECT current_database()")).scalar_one()
            )
            if actual != self._expected_database:
                transaction.rollback()
                connection.close()
                raise StorageRefusal(
                    DATABASE_MISMATCH,
                    f"unit of work expected database {self._expected_database!r} "
                    f"but the connection is to {actual!r}",
                )
        self._connection = connection
        self._transaction = transaction
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        connection = self._connection
        transaction = self._transaction
        self._transaction = None
        if connection is None:
            return
        try:
            if transaction is not None and transaction.is_active:
                transaction.rollback()
        finally:
            connection.close()

    @property
    def connection(self) -> Connection:
        """The one connection, inside the one transaction."""
        if self._connection is None or self._transaction is None:
            raise StorageRefusal(
                UNIT_OF_WORK_CLOSED,
                "the unit of work is not open: enter it, and use it before commit "
                "or rollback",
            )
        return self._connection

    def commit(self) -> None:
        transaction = self._transaction
        if transaction is None:
            raise StorageRefusal(UNIT_OF_WORK_CLOSED, "nothing to commit")
        self._transaction = None
        transaction.commit()

    def rollback(self) -> None:
        transaction = self._transaction
        if transaction is None:
            raise StorageRefusal(UNIT_OF_WORK_CLOSED, "nothing to roll back")
        self._transaction = None
        transaction.rollback()


class StorageBackend(Protocol):
    """What every storage backend provides. Postgres is release one's only one."""

    supports_vector: bool
    supports_lexical: bool
    supports_skip_locked: bool

    def open_unit_of_work(self, ctx: WorkspaceContext) -> UnitOfWork: ...

    def provision(
        self,
        workspace_id: UUID,
        *,
        owner_account_id: UUID,
        slug: str | None = None,
        after_step: Callable[[str], None] | None = None,
    ) -> None: ...

    def migrate(
        self, workspace_id: UUID, chains: Sequence[str]
    ) -> "MigrationResult": ...

    def advisory_lock(self, conn: Connection, key: int) -> None: ...
