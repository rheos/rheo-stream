"""C8: tokens that can never mint or approve, both issuance paths, both
presentation surfaces, and the row-count-snapshot proof of "no partial
effect" (B6, B7).

Seams under test: ``core.token.issue``/``rheo_core.boundary.factories.
context_from_token`` (the full mint -> snapshot -> present -> refuse path),
the operator-role authorization on ``core.token.issue``/``revoke`` (a ``rheo
token issue`` regression -- proved by driving the real,
``context_for_operator`` -> ``registry.authorize`` -> ``dispatch`` path, not a
bypassing handler call), ``sets.py``'s ``agent_default`` against its own
``REGISTERED_TOOLS``, and the presentation refusal chain's exact order.
"""

import hashlib
from datetime import UTC, datetime
from uuid import UUID

import pytest
from conftest import ClusterSession
from harness.registry import NOTE_GET, register_harness
from rheo_contracts import WorkspaceContext
from rheo_core.boundary import context_for_operator
from rheo_core.boundary.context import (
    MEMBERSHIP_MISSING,
    TOKEN_EXPIRED,
    TOKEN_MALFORMED,
    TOKEN_REVOKED,
    TOKEN_SCOPE_INVALID,
    TOKEN_WRONG_KIND,
    WORKSPACE_UNAVAILABLE,
    Refusal,
)
from rheo_core.boundary.factories import context_from_session, context_from_token
from rheo_core.operations import (
    OPERATION_NOT_PERMITTED,
    SETTINGS_SET,
    dispatch,
    register_core_operations,
)
from rheo_core.operations.core_ops import TOKEN_ISSUE
from rheo_core.sessions import create_session, mint_host_secret, switch_workspace
from rheo_core.storage import control_tables as t
from rheo_core.storage import core_tables
from rheo_core.storage.backend import UnitOfWork
from rheo_core.storage.control_plane import (
    WorkspaceRow,
    insert_access_token,
    insert_access_token_operations,
    list_access_token_operations,
    set_workspace_state,
)
from rheo_core.storage.control_tables import WorkspaceState
from rheo_core.tokens.format import mint
from rheo_core.tokens.issue import SET_NOT_ISSUABLE
from rheo_core.tokens.sets import agent_default
from sqlalchemy import func, select, update

pytestmark = pytest.mark.postgres

HOST = "example.test"
_FAR_FUTURE = datetime(2999, 1, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def registrations() -> None:
    register_core_operations()
    register_harness()


@pytest.fixture
def session_ctx(
    cluster: ClusterSession, workspace: UUID, owner_account_id: UUID
) -> WorkspaceContext:
    """A real, session-issued context (``context_from_session``): the owner,
    with ``workspace`` as the active workspace."""
    session_row = create_session(owner_account_id)
    secret = mint_host_secret(session_row.id, HOST)
    assert switch_workspace(session_row.id, workspace) is None
    ctx = context_from_session(secret, HOST)
    assert isinstance(ctx, WorkspaceContext), ctx
    return ctx


def _operator_ctx(workspace_id: UUID) -> WorkspaceContext:
    ctx = context_for_operator(workspace_id)
    assert isinstance(ctx, WorkspaceContext), ctx
    return ctx


def _issue(
    ctx: WorkspaceContext,
    *,
    kind: str = "cli",
    set_name: str | None = None,
    operations: list[str] | None = None,
    account_id: UUID | None = None,
) -> tuple[str, UUID, frozenset[str]]:
    """Dispatch ``core.token.issue``, asserting success; returns ``(value,
    token_id, operations)``."""
    payload: dict[str, object] = {"kind": kind}
    if set_name is not None:
        payload["set_name"] = set_name
    if operations is not None:
        payload["operations"] = operations
    if account_id is not None:
        payload["account_id"] = str(account_id)
    outcome = dispatch(ctx, TOKEN_ISSUE, payload)
    assert outcome.ok, outcome
    result = outcome.result
    assert result is not None
    return result.value, result.token_id, frozenset(result.operations)  # type: ignore[attr-defined]


def _snapshot(cluster: ClusterSession, workspace_row: WorkspaceRow) -> dict[str, int]:
    """Row counts for every control-plane and workspace (core) table."""
    counts: dict[str, int] = {}
    with cluster.backend.control_engine.connect() as connection:
        for table in t.CONTROL_TABLES:
            counts[f"control.{table.name}"] = connection.execute(
                select(func.count()).select_from(table)
            ).scalar_one()
    engine = cluster.backend.pools.engine_for(workspace_row.database_name)
    with UnitOfWork(engine, workspace_row.database_name) as uow:
        for table in core_tables.CORE_TABLES:
            counts[f"core.{table.name}"] = uow.connection.execute(
                select(func.count()).select_from(table)
            ).scalar_one()
    return counts


def _force_row(
    cluster: ClusterSession,
    token_id: UUID,
    *,
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> None:
    values: dict[str, object] = {}
    if expires_at is not None:
        values["expires_at"] = expires_at
    if revoked_at is not None:
        values["revoked_at"] = revoked_at
    with cluster.backend.control_engine.begin() as connection:
        statement = update(t.access_token).where(t.access_token.c.id == token_id)
        connection.execute(statement.values(**values))


# --- B6: issuance, both paths -----------------------------------------------


def test_session_issued_token_row_shapes(
    cluster: ClusterSession, session_ctx: WorkspaceContext
) -> None:
    """A session-issued token (B6, row 11): one ``access_token`` row and N
    ``access_token_operation`` rows equal to the expanded set."""
    value, token_id, operations = _issue(session_ctx, kind="cli", set_name="read_only")
    assert value.startswith("rheo_cli_")
    assert operations == frozenset({"core.workspace.status", NOTE_GET})
    with cluster.backend.control_engine.connect() as connection:
        token_row_count = connection.execute(
            select(func.count())
            .select_from(t.access_token)
            .where(t.access_token.c.id == token_id)
        ).scalar_one()
        stored_operations = list_access_token_operations(connection, token_id)
    assert token_row_count == 1
    assert stored_operations == operations


def test_operator_issued_token_via_real_dispatch_path(
    cluster: ClusterSession, workspace: UUID, owner_account_id: UUID
) -> None:
    """A ``rheo token issue``-driven token (B6, row 12): the actual
    ``context_for_operator`` -> ``registry.authorize`` -> ``dispatch`` path a
    CLI invocation takes, not a handler call that bypasses ``authorize()``.
    This is also the test a dropped ``Role.OPERATOR`` from
    ``core.token.issue``'s declared roles would fail: without it, ``dispatch``
    refuses ``role_not_permitted`` before the handler ever runs and
    ``outcome.ok`` is false.
    """
    ctx = _operator_ctx(workspace)
    value, token_id, operations = _issue(
        ctx, kind="cli", set_name="read_only", account_id=owner_account_id
    )
    assert value.startswith("rheo_cli_")
    assert operations == frozenset({"core.workspace.status", NOTE_GET})
    with cluster.backend.control_engine.connect() as connection:
        stored = list_access_token_operations(connection, token_id)
    assert stored == operations


def test_agent_default_evaluates_to_registered_tools(
    session_ctx: WorkspaceContext,
) -> None:
    """B7's own set claim, commissioned explicitly rather than left untested:
    ``agent_default`` is exactly the two tools this run registers."""
    assert agent_default() == frozenset({"core.workspace.status", NOTE_GET})
    # And an issued agent_default token carries exactly that snapshot.
    _, _, operations = _issue(session_ctx, kind="mcp", set_name="agent_default")
    assert operations == frozenset({"core.workspace.status", NOTE_GET})


def test_cli_full_excludes_the_six_names(session_ctx: WorkspaceContext) -> None:
    """B7, row 18: ``cli_full`` for an owner contains every registered
    operation except the six ``NON_TOKEN_ISSUABLE`` names."""
    _, _, operations = _issue(session_ctx, kind="cli", set_name="cli_full")
    assert "core.token.issue" not in operations
    assert "core.token.revoke" not in operations
    assert "core.approval.approve" not in operations
    assert "core.approval.refuse" not in operations
    assert "core.standing_grant.create" not in operations
    assert "core.standing_grant.revoke" not in operations
    assert "core.workspace.status" in operations
    assert NOTE_GET in operations


# --- B7: the non-token-issuable rule, both ends -----------------------------


def test_explicit_list_naming_token_issue_refused(
    session_ctx: WorkspaceContext,
) -> None:
    """B7, row 19: an explicit list naming ``core.token.issue`` is refused
    ``set_not_issuable``, naming the operation -- distinct from a named
    package set, which never contains it in the first place."""
    outcome = dispatch(
        session_ctx,
        TOKEN_ISSUE,
        {"kind": "cli", "operations": ["core.workspace.status", "core.token.issue"]},
    )
    assert outcome.state == SET_NOT_ISSUABLE
    assert outcome.error is not None and "core.token.issue" in outcome.error.error_text


def test_valid_cli_full_token_cannot_dispatch_token_issue(
    session_ctx: WorkspaceContext,
) -> None:
    """B7, row 20: a legitimately issued ``cli_full`` token (which never
    contains ``core.token.issue``) presented at the ``api`` surface and
    dispatched against it is refused ``operation_not_permitted`` -- the
    normal per-request scope check, distinct from the directly-inserted-row
    case below (which only an illegitimate row can reach). This is also the
    test a mutant letting a ``cli_full`` token dispatch ``core.token.issue``
    must fail.
    """
    value, _, _ = _issue(session_ctx, kind="cli", set_name="cli_full")
    ctx = context_from_token(value, "api")
    assert isinstance(ctx, WorkspaceContext), ctx
    outcome = dispatch(ctx, TOKEN_ISSUE, {"kind": "cli", "set_name": "read_only"})
    assert outcome.state == OPERATION_NOT_PERMITTED


def test_directly_inserted_row_with_approval_operation_refused_scope_invalid(
    cluster: ClusterSession, workspace: UUID, owner_account_id: UUID
) -> None:
    """B7, row 21: a snapshot row inserted directly with
    ``core.approval.approve`` (a row that cannot arise from ``issue()``, since
    ``sets.py`` never yields that name and an explicit list naming it is
    refused before any row is written) makes presentation refuse
    ``token_scope_invalid``."""
    value, raw = mint("cli")
    token_hash = hashlib.sha256(raw).digest()
    with cluster.backend.control_engine.begin() as connection:
        row = insert_access_token(
            connection,
            account_id=owner_account_id,
            workspace_id=workspace,
            kind="cli",
            issued_from="operator",
            token_hash=token_hash,
            set_name=None,
            purpose=None,
            expires_at=_FAR_FUTURE,
        )
        insert_access_token_operations(
            connection, token_id=row.id, operation_names=["core.approval.approve"]
        )
    ctx = context_from_token(value, "api")
    assert ctx == Refusal(TOKEN_SCOPE_INVALID)


# --- B6/B7: kind-for-surface -------------------------------------------------


def test_cli_token_wrong_kind_on_mcp_and_mcp_token_ok_on_api(
    session_ctx: WorkspaceContext,
) -> None:
    """B7, rows 22-23: a ``cli`` token on the MCP seam is ``token_wrong_kind``;
    a ``mcp`` token on the ``api`` surface succeeds."""
    cli_value, _, _ = _issue(session_ctx, kind="cli", set_name="read_only")
    mcp_value, _, _ = _issue(session_ctx, kind="mcp", set_name="read_only")
    wrong = context_from_token(cli_value, "mcp")
    assert wrong == Refusal(TOKEN_WRONG_KIND)
    ok = context_from_token(mcp_value, "api")
    assert isinstance(ok, WorkspaceContext)


# --- B6: malformed / expired / out-of-scope, with row-count snapshots ------


def test_malformed_presentation_refused_with_unchanged_snapshot(
    cluster: ClusterSession, workspace: UUID
) -> None:
    row = cluster.registry_row(workspace)
    before = _snapshot(cluster, row)
    refusal = context_from_token("not-a-real-token", "api")
    assert refusal == Refusal(TOKEN_MALFORMED)
    assert _snapshot(cluster, row) == before


def test_expired_presentation_refused_with_unchanged_snapshot(
    cluster: ClusterSession, workspace: UUID, session_ctx: WorkspaceContext
) -> None:
    value, token_id, _ = _issue(session_ctx, kind="cli", set_name="read_only")
    _force_row(cluster, token_id, expires_at=datetime(2000, 1, 1, tzinfo=UTC))
    row = cluster.registry_row(workspace)
    before = _snapshot(cluster, row)
    refusal = context_from_token(value, "api")
    assert refusal == Refusal(TOKEN_EXPIRED)
    assert _snapshot(cluster, row) == before


def test_out_of_scope_presentation_refused_with_unchanged_snapshot(
    cluster: ClusterSession, workspace: UUID, session_ctx: WorkspaceContext
) -> None:
    """B6, row 15: a valid ``read_only`` token against ``core.settings.set``
    refused ``operation_not_permitted`` -- the presentation itself succeeds
    (it legitimately touches ``last_used_at``); the snapshot brackets only
    the refused dispatch that follows."""
    value, _, _ = _issue(session_ctx, kind="cli", set_name="read_only")
    ctx = context_from_token(value, "api")
    assert isinstance(ctx, WorkspaceContext), ctx
    row = cluster.registry_row(workspace)
    before = _snapshot(cluster, row)
    payload = {"key": "identity.token_max_days.cli", "value": 5}
    outcome = dispatch(ctx, SETTINGS_SET, payload)
    assert outcome.state == OPERATION_NOT_PERMITTED
    assert _snapshot(cluster, row) == before


def test_expired_is_checked_before_revoked(
    cluster: ClusterSession, session_ctx: WorkspaceContext
) -> None:
    """The refusal chain's pinned order: a token both expired and revoked
    refuses ``token_expired``, never ``token_revoked`` -- the mutant a
    reordered chain must fail."""
    value, token_id, _ = _issue(session_ctx, kind="cli", set_name="read_only")
    _force_row(
        cluster,
        token_id,
        expires_at=datetime(2000, 1, 1, tzinfo=UTC),
        revoked_at=datetime(2000, 1, 1, tzinfo=UTC),
    )
    refusal = context_from_token(value, "api")
    assert refusal == Refusal(TOKEN_EXPIRED)


def test_revoked_alone_refuses_token_revoked(
    cluster: ClusterSession, session_ctx: WorkspaceContext
) -> None:
    value, token_id, _ = _issue(session_ctx, kind="cli", set_name="read_only")
    _force_row(cluster, token_id, revoked_at=datetime.now(UTC))
    refusal = context_from_token(value, "api")
    assert refusal == Refusal(TOKEN_REVOKED)


# --- B16 (0b2 factory clause): context_from_token over an unavailable workspace


def test_context_from_token_refuses_an_unavailable_workspace(
    cluster: ClusterSession, workspace: UUID, session_ctx: WorkspaceContext
) -> None:
    """B16's 0b2 factory clause for the token factory (mirrors
    ``tests/test_boundary.py``'s ``test_both_factories_refuse_an_unavailable_
    workspace``; that file is denied to this prompt, so this is its own
    equivalent case)."""
    value, _, _ = _issue(session_ctx, kind="cli", set_name="read_only")
    with cluster.backend.control_engine.begin() as connection:
        set_workspace_state(
            connection,
            workspace,
            state=WorkspaceState.UNAVAILABLE,
            state_detail="marked unavailable by the test",
        )
    refusal = context_from_token(value, "api")
    assert refusal == Refusal(WORKSPACE_UNAVAILABLE, "unavailable")


# --- membership-at-presentation ----------------------------------------------


def test_context_from_token_refuses_membership_missing_at_presentation(
    cluster: ClusterSession,
    workspace: UUID,
    owner_account_id: UUID,
    session_ctx: WorkspaceContext,
) -> None:
    """The token's account no longer a member at presentation time (read
    fresh, never cached in the snapshot) refuses ``membership_missing``."""
    value, _, _ = _issue(session_ctx, kind="cli", set_name="read_only")
    with cluster.backend.control_engine.begin() as connection:
        connection.execute(
            t.membership.delete().where(
                t.membership.c.account_id == owner_account_id,
                t.membership.c.workspace_id == workspace,
            )
        )
    refusal = context_from_token(value, "api")
    assert isinstance(refusal, Refusal) and refusal.state == MEMBERSHIP_MISSING
