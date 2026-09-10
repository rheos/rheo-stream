"""Harness registrations under ``profile = test`` with origin ``test_harness``: the
``harness.note`` record type (a resolver over the table ``tests/harness/records.py``
creates through the storage backend, never a shipped migration), the operations
``harness.note.get(ref)``, ``harness.note.write(body)`` and
``harness.note.explode(body, message)`` (a handler that raises after writing, for the
dispatcher's rollback and failure envelope), and the scaffolding B2 needs to drive
the reserved-field refusal.

Also two pieces of control-plane scaffolding the C4 tests share: ``add_member``
(an account plus its ``control.membership`` row through C3's repositories, because
``rheo member add`` is 0b2's) and ``enable_harness_module`` (a ``core.module_state``
row for ``harness`` in state ``enabled``, so a context built over that workspace
carries ``harness`` in ``enabled_modules`` — module install is phase 2, and this row
is the only way a 0b1 test can exercise the ``module_disabled`` branch both ways).

Registration is explicit (:func:`register_harness`), idempotent, and never an import
side effect. Nothing under ``rheo_core`` knows any of this exists.
"""

import warnings
from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, create_model
from rheo_contracts import (
    AuditSpec,
    Idempotency,
    OperationDeclaration,
    RecordRef,
    Role,
    SafetyClass,
    WorkspaceContext,
)
from rheo_core.operations import (
    HARNESS_MODULE_ID,
    REGISTRY,
    OperationRefused,
    OperationRegistry,
)
from rheo_core.refs.resolver import (
    LIVE,
    NOT_FOUND,
    RESOLVERS,
    RecordHead,
    ResolverRegistry,
    Unavailable,
    resolve_in,
)
from rheo_core.settings import TEST_HARNESS_ORIGIN
from rheo_core.storage import core_tables
from rheo_core.storage.backend import UnitOfWork
from rheo_core.storage.control_plane import insert_account, insert_membership_if_absent
from rheo_core.storage.postgres import PostgresBackend
from sqlalchemy import Connection, inspect
from sqlalchemy.dialects.postgresql import insert as pg_insert

from harness.records import HARNESS_SCHEMA, ensure_note_table, get_note, write_note

NOTE_RECORD_TYPE: Final = "note"
NOTE_GET: Final = "harness.note.get"
NOTE_WRITE: Final = "harness.note.write"
NOTE_EXPLODE: Final = "harness.note.explode"

_ALL_THREE_ROLES: Final = frozenset({Role.OWNER, Role.MEMBER, Role.OPERATOR})
# See ``rheo_core.operations.core_ops`` for why ``ignore`` (the default) is stated.
_IGNORE_EXTRA: Final = ConfigDict(extra="ignore")


def note_ref(note_id: UUID) -> str:
    return RecordRef(
        module=HARNESS_MODULE_ID, record_type=NOTE_RECORD_TYPE, id=note_id
    ).format()


# --- the record type ------------------------------------------------------------------


def resolve_note(
    ctx: WorkspaceContext, uow: UnitOfWork, ref: RecordRef
) -> RecordHead | Unavailable:
    """The ``harness.note`` resolver: a lookup in the caller's own database.

    A workspace that never had the table, or has no such row, is ``not_found`` —
    which is exactly what a reference minted in another workspace gets.
    """
    connection = uow.connection
    if not inspect(connection).has_table(NOTE_RECORD_TYPE, schema=HARNESS_SCHEMA):
        return Unavailable(ref.format(), NOT_FOUND)
    row = get_note(connection, ref.id)
    if row is None:
        return Unavailable(ref.format(), NOT_FOUND)
    return RecordHead(
        ref=ref, display=row.body[:40], readable=True, state=LIVE, revision=1
    )


# --- the operations -------------------------------------------------------------------


class NoteRefInput(BaseModel):
    model_config = _IGNORE_EXTRA

    ref: str


class NoteHead(BaseModel):
    model_config = ConfigDict(frozen=True)

    ref: str
    display: str
    readable: bool
    state: str
    revision: int | None


class NoteWriteInput(BaseModel):
    model_config = _IGNORE_EXTRA

    body: str


class NoteWritten(BaseModel):
    model_config = ConfigDict(frozen=True)

    ref: str
    body: str


def _get_note(
    ctx: WorkspaceContext, uow: UnitOfWork, model_input: NoteRefInput
) -> NoteHead:
    head = resolve_in(model_input.ref, ctx, uow)
    if isinstance(head, Unavailable):
        raise OperationRefused(NOT_FOUND, f"{head.reference} is not available here")
    return NoteHead(
        ref=head.ref.format(),
        display=head.display,
        readable=head.readable,
        state=head.state,
        revision=head.revision,
    )


def _write_note(
    ctx: WorkspaceContext, uow: UnitOfWork, model_input: NoteWriteInput
) -> NoteWritten:
    ensure_note_table(uow.connection)
    row = write_note(uow.connection, body=model_input.body)
    return NoteWritten(ref=note_ref(row.id), body=row.body)


class NoteExplodeInput(BaseModel):
    """``body`` is written first, then the handler raises ``RuntimeError(message)``:
    the dispatcher must roll the write back and must not echo ``message``."""

    model_config = _IGNORE_EXTRA

    body: str
    message: str


def _explode(
    ctx: WorkspaceContext, uow: UnitOfWork, model_input: NoteExplodeInput
) -> NoteWritten:
    ensure_note_table(uow.connection)
    write_note(uow.connection, body=model_input.body)
    raise RuntimeError(model_input.message)


NOTE_EXPLODE_DECLARATION: Final = OperationDeclaration(
    name=NOTE_EXPLODE,
    safety_class=SafetyClass.MUTATE,
    roles=_ALL_THREE_ROLES,
    input_model=NoteExplodeInput,
    output=NoteWritten,
    idempotency=Idempotency.NONE,
    audit=AuditSpec(subject_field=None),
)

NOTE_GET_DECLARATION: Final = OperationDeclaration(
    name=NOTE_GET,
    safety_class=SafetyClass.READ,
    roles=_ALL_THREE_ROLES,
    input_model=NoteRefInput,
    output=NoteHead,
    idempotency=Idempotency.NONE,
    audit=None,
)

NOTE_WRITE_DECLARATION: Final = OperationDeclaration(
    name=NOTE_WRITE,
    safety_class=SafetyClass.MUTATE,
    roles=_ALL_THREE_ROLES,
    input_model=NoteWriteInput,
    output=NoteWritten,
    idempotency=Idempotency.NONE,
    audit=AuditSpec(subject_field=None),
)


def register_harness(
    *, registry: OperationRegistry = REGISTRY, resolvers: ResolverRegistry = RESOLVERS
) -> None:
    """Register the note resolver and the two harness operations (idempotent)."""
    resolvers.register(
        HARNESS_MODULE_ID, NOTE_RECORD_TYPE, resolve_note, origin=TEST_HARNESS_ORIGIN
    )
    registry.register(NOTE_GET_DECLARATION, _get_note, origin=TEST_HARNESS_ORIGIN)
    registry.register(NOTE_WRITE_DECLARATION, _write_note, origin=TEST_HARNESS_ORIGIN)
    registry.register(NOTE_EXPLODE_DECLARATION, _explode, origin=TEST_HARNESS_ORIGIN)


# --- B2 scaffolding: input models a registration must refuse --------------------------


class Nothing(BaseModel):
    """An output model for probe declarations."""

    model_config = ConfigDict(frozen=True)


def reserved_field_models(name: str) -> tuple[type[BaseModel], ...]:
    """Input models a payload key ``name`` would bind to: one declaring ``name``
    directly, and one through an alias on a safe attribute name. Both are what
    registration must refuse naming ``name``.

    pydantic warns that ``schema`` shadows a ``BaseModel`` attribute (it still builds
    the model); the warning is silenced here because the shadowing is the point.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        plain = create_model(f"Plain_{name}", **{name: (str, ...)})
    aliased = create_model(
        f"Aliased_{name}", **{f"field_{name}": (str, Field(alias=name))}
    )
    return (plain, aliased)


def probe_declaration(name: str, input_model: type[BaseModel]) -> OperationDeclaration:
    return OperationDeclaration(
        name=name,
        safety_class=SafetyClass.MUTATE,
        roles=_ALL_THREE_ROLES,
        input_model=input_model,
        output=Nothing,
        idempotency=Idempotency.NONE,
        audit=AuditSpec(subject_field=None),
    )


def probe_handler(
    ctx: WorkspaceContext, uow: UnitOfWork, model_input: BaseModel
) -> Nothing:
    return Nothing()


# --- control-plane and workspace scaffolding ------------------------------------------


def add_member(
    backend: PostgresBackend, workspace_id: UUID, role: Role, *, display_name: str
) -> UUID:
    """A fresh account with a ``control.membership`` row of ``role`` (``rheo member
    add`` is 0b2's; this writes the same row through C3's repositories)."""
    with backend.control_engine.begin() as connection:
        account = insert_account(connection, display_name=display_name)
        insert_membership_if_absent(
            connection, account_id=account.id, workspace_id=workspace_id, role=role
        )
    return account.id


def enable_harness_module(conn: Connection) -> None:
    """A ``core.module_state`` row for ``harness`` in state ``enabled`` (idempotent),
    in the connection's workspace database."""
    now = datetime.now(UTC)
    conn.execute(
        pg_insert(core_tables.module_state)
        .values(
            module_id=HARNESS_MODULE_ID,
            package_version="0",
            state="enabled",
            installed_at=now,
            enabled_at=now,
            disabled_at=None,
            state_detail=None,
        )
        .on_conflict_do_nothing(index_elements=[core_tables.module_state.c.module_id])
    )
