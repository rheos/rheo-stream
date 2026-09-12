"""The only place a ``WorkspaceContext`` is constructed.

Every factory returns ``WorkspaceContext | Refusal``. The repository-wide AST scan in
``tests/test_boundary.py`` asserts that the class is constructed in no file outside
this package, tests included, so the two functions here (and the session and token
factories 0b2 adds beside them) are the only way to obtain a context.

Both factories share one tail: the ``control.workspace`` row must be ``active``
(otherwise ``workspace_unavailable`` with the row's state as the detail), and
``enabled_modules`` is loaded from that workspace's ``core.module_state`` rows. That
tail is B16's factory clause for this run.
"""

from uuid import UUID

from rheo_contracts import (
    ALL_OPERATIONS,
    Actor,
    ActorKind,
    Audience,
    AudienceKind,
    Entry,
    Role,
    WorkspaceContext,
)

from rheo_core.boundary.context import (
    MEMBERSHIP_MISSING,
    PROFILE_REQUIRED,
    WORKSPACE_MISSING_DETAIL,
    WORKSPACE_UNAVAILABLE,
    Refusal,
)
from rheo_core.refs import uuid7
from rheo_core.settings import current_profile
from rheo_core.storage.backend import UnitOfWork
from rheo_core.storage.control_plane import get_membership, get_workspace
from rheo_core.storage.control_tables import WorkspaceState
from rheo_core.storage.postgres import PostgresBackend, get_backend
from rheo_core.storage.repositories import list_module_states

# The ``core.module_state.state`` value that makes a module enabled; one of
# ``rheo_core.storage.core_tables.MODULE_STATES``.
_MODULE_ENABLED = "enabled"


def _active_workspace_modules(
    backend: PostgresBackend, workspace_id: UUID
) -> frozenset[str] | Refusal:
    """The shared factory tail: the row must be ``active``, then the enabled set.

    The registry row is read now, on every call, exactly as ``storage.routing``
    reads it: a context is only ever built over a workspace that is servable at
    that moment.
    """
    with backend.control_engine.connect() as connection:
        row = get_workspace(connection, workspace_id)
    if row is None:
        return Refusal(WORKSPACE_UNAVAILABLE, WORKSPACE_MISSING_DETAIL)
    if row.state is not WorkspaceState.ACTIVE:
        return Refusal(WORKSPACE_UNAVAILABLE, row.state.value)
    engine = backend.pools.engine_for(row.database_name)
    with UnitOfWork(engine, row.database_name) as uow:
        states = list_module_states(uow.connection)
    return frozenset(
        state.module_id for state in states if state.state == _MODULE_ENABLED
    )


def context_for_operator(
    workspace_id: UUID, entry: Entry | str = Entry.CLI
) -> WorkspaceContext | Refusal:
    """The operator's context over ``workspace_id`` (the ``rheo`` command, C4).

    Actor ``operator`` with no id, role ``operator``, the full operation set, and
    **no audience**. ``docs/architecture/overview.md:74`` (the ``audience`` row of the
    context table) enumerates exactly four audience kinds, none of them an operator,
    and records that a context may carry no audience at all: of the ``job`` kind it
    says "a scheduled job has none". So every consumer already handles
    ``audience is None``, and that is the value here. It is deliberately not
    ``Audience(session, None)``: 0b2's ``context_from_session`` sets
    ``Audience(session, account_id)``, so a session-kind audience with a null id
    would leave an operator context and a real web-session context differing only by
    that null, and any later code branching on ``audience.kind == session`` would
    treat operator output as session output. Widening the ratified enum was the other
    option and is refused for the same reason ``Entry`` was not widened for tests.
    """
    if not isinstance(workspace_id, UUID):
        raise TypeError("workspace_id must be a UUID")
    enabled = _active_workspace_modules(get_backend(), workspace_id)
    if isinstance(enabled, Refusal):
        return enabled
    return WorkspaceContext(
        workspace_id=workspace_id,
        actor=Actor(kind=ActorKind.OPERATOR, id=None),
        role=Role.OPERATOR,
        entry=Entry(entry),
        audience=None,
        operation_set=ALL_OPERATIONS,
        enabled_modules=enabled,
        request_id=uuid7(),
    )


def context_for_harness(
    workspace_id: UUID,
    account_id: UUID,
    role: Role | str,
    entry: Entry | str = Entry.CLI,
) -> WorkspaceContext | Refusal:
    """Test scaffolding: an account's context, ``profile = test``-gated, boundary-owned.

    Refuses ``profile_required`` under any profile other than ``test``, before any
    database read. Then reads ``control.membership`` for ``(account_id,
    workspace_id)`` and refuses ``membership_missing`` unless a row exists **with
    exactly that role**. The context carries the ratified values for an account actor
    (``overview.md`` § The workspace context): ``Actor(account, account_id)``,
    ``Audience(session, account_id)``, the full operation set, and ``entry``
    defaulting to ``cli`` because the closed ``Entry`` enum has no test value and C1
    added none. The session audience is correct here and stays: unlike
    :func:`context_for_operator`, this factory stands in for a session context, so it
    carries a session audience with a real account id.

    Why it exists: the core-operation table (``module-contract.md:96-101``) gives
    ``core.settings.set`` the role ``owner`` only and ``core.settings.set_member``
    ``owner, member``, and enumerates ``operator`` where it applies, so ``operator``
    is not an implicit superset; without this factory the settings operations and
    criterion 69 could not be driven end-to-end in 0b1.

    It does not build, stub, or pre-shape C7's ``context_from_session``: it reads no
    session table and takes no secret, host, or cookie.
    """
    if not isinstance(workspace_id, UUID) or not isinstance(account_id, UUID):
        raise TypeError("workspace_id and account_id must be UUIDs")
    wanted = Role(role)
    profile = current_profile()
    if profile != "test":
        return Refusal(
            PROFILE_REQUIRED,
            f"context_for_harness runs under profile = test only (resolved profile "
            f"is {profile!r})",
        )
    backend = get_backend()
    with backend.control_engine.connect() as connection:
        membership = get_membership(
            connection, account_id=account_id, workspace_id=workspace_id
        )
    if membership is None or membership.role is not wanted:
        return Refusal(
            MEMBERSHIP_MISSING,
            f"no control.membership row for account {account_id} in workspace "
            f"{workspace_id} with role {wanted.value!r}",
        )
    enabled = _active_workspace_modules(backend, workspace_id)
    if isinstance(enabled, Refusal):
        return enabled
    return WorkspaceContext(
        workspace_id=workspace_id,
        actor=Actor(kind=ActorKind.ACCOUNT, id=account_id),
        role=wanted,
        entry=Entry(entry),
        audience=Audience(kind=AudienceKind.SESSION, id=account_id),
        operation_set=ALL_OPERATIONS,
        enabled_modules=enabled,
        request_id=uuid7(),
    )
