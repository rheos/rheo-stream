"""B11, public criterion 69 (FR 12), end-to-end through ``core.settings.set`` under
an owner context from ``context_for_harness`` — the write path, not the resolver
alone.

- One key at each source: the package default, then the deployment layer, then a
  workspace override written through the operation; the resolved value follows that
  precedence.
- A floored key (``identity.token_max_days.cli``, floor ``min``) written looser than
  the deployment value is refused ``setting_floor_violation`` naming the key, and no
  row is written.
- Tightening the deployment value beneath an existing looser row leaves the row in
  place and resolves to the deployment value.
- The other three comparators (``union``, ``subset``, ``and``) through C2's harness
  keys, each refused when looser and accepted when tighter.
- The same write under a ``member`` harness context is ``role_not_permitted``; the
  ``owner`` write succeeds. Both settings operations refuse an ``operator`` context
  too: ``operator`` is enumerated where it applies and is not an implicit superset.
  ``core.settings.set_member`` accepts owner and member for a member-scope key and
  refuses a workspace-scope key ``setting_scope``.
"""

from uuid import UUID

import pytest
from conftest import ClusterSession
from harness.registry import add_member
from harness.settings_keys import (
    HARNESS_FLOOR_AND,
    HARNESS_FLOOR_MIN,
    HARNESS_FLOOR_SUBSET,
    HARNESS_FLOOR_UNION,
    HARNESS_MEMBER,
)
from rheo_contracts import Role, WorkspaceContext
from rheo_core.boundary import context_for_harness, context_for_operator
from rheo_core.operations import (
    ROLE_NOT_PERMITTED,
    SETTINGS_SET,
    SETTINGS_SET_MEMBER,
    WORKSPACE_STATUS,
    OperationOutcome,
    dispatch,
    register_core_operations,
)
from rheo_core.operations.core_ops import (
    SETTINGS_SET_DECLARATION,
    SETTINGS_SET_MEMBER_DECLARATION,
    WORKSPACE_STATUS_DECLARATION,
)
from rheo_core.settings import SettingValue, resolve
from rheo_core.settings.storage_source import PostgresOverrideSource
from rheo_core.storage.backend import UnitOfWork
from rheo_core.storage.repositories import member_settings, workspace_settings

pytestmark = pytest.mark.postgres

TOKEN_DAYS_CLI = "identity.token_max_days.cli"
TOKEN_DAYS_CLI_VARIABLE = "RHEO__identity__token_max_days__cli"


@pytest.fixture(autouse=True)
def registrations(harness_keys: None) -> None:
    register_core_operations()


@pytest.fixture
def owner(workspace: UUID, owner_account_id: UUID) -> WorkspaceContext:
    ctx = context_for_harness(workspace, owner_account_id, Role.OWNER)
    assert isinstance(ctx, WorkspaceContext), ctx
    return ctx


@pytest.fixture
def member(cluster: ClusterSession, workspace: UUID) -> WorkspaceContext:
    account = add_member(
        cluster.backend, workspace, Role.MEMBER, display_name="member-two"
    )
    ctx = context_for_harness(workspace, account, Role.MEMBER)
    assert isinstance(ctx, WorkspaceContext), ctx
    return ctx


def _resolved(workspace: UUID, key: str) -> SettingValue:
    return resolve(workspace_id=workspace, source=PostgresOverrideSource())[key]


def _rows(cluster: ClusterSession, workspace: UUID) -> dict[str, str]:
    row = cluster.registry_row(workspace)
    engine = cluster.backend.pools.engine_for(row.database_name)
    with UnitOfWork(engine, row.database_name) as uow:
        return workspace_settings(uow.connection)


def _set(ctx: WorkspaceContext, key: str, value: SettingValue) -> OperationOutcome:
    return dispatch(ctx, SETTINGS_SET, {"key": key, "value": value})


def _assert_refused_naming_the_key(
    outcome: OperationOutcome, state: str, key: str
) -> None:
    assert outcome.state == state, outcome
    assert outcome.result is None
    assert outcome.error is not None
    assert outcome.error.error_code == state
    assert key in outcome.error.error_text


# --- precedence, the floor at write time, the clamp at read time ----------------------


def test_one_key_at_each_source_resolves_in_precedence_order(
    cluster: ClusterSession,
    workspace: UUID,
    owner: WorkspaceContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 1. Package default.
    assert TOKEN_DAYS_CLI not in _rows(cluster, workspace)
    assert _resolved(workspace, TOKEN_DAYS_CLI) == 90
    # 2. Deployment layer.
    monkeypatch.setenv(TOKEN_DAYS_CLI_VARIABLE, "60")
    assert _resolved(workspace, TOKEN_DAYS_CLI) == 60
    # 3. Workspace override, through the operation.
    outcome = _set(owner, TOKEN_DAYS_CLI, 30)
    assert outcome.ok, outcome
    assert outcome.result is not None
    assert outcome.result.model_dump() == {  # type: ignore[union-attr]
        "key": TOKEN_DAYS_CLI,
        "value": 30,
        "scope": "workspace",
    }
    assert _rows(cluster, workspace)[TOKEN_DAYS_CLI] == "30"
    assert _resolved(workspace, TOKEN_DAYS_CLI) == 30
    # The deployment layer alone (no workspace) never sees the row.
    assert resolve()[TOKEN_DAYS_CLI] == 60


def test_a_floored_write_looser_than_the_deployment_value_is_refused_naming_the_key(
    cluster: ClusterSession,
    workspace: UUID,
    owner: WorkspaceContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TOKEN_DAYS_CLI_VARIABLE, "60")
    rows_before = _rows(cluster, workspace)
    outcome = _set(owner, TOKEN_DAYS_CLI, 120)
    _assert_refused_naming_the_key(outcome, "setting_floor_violation", TOKEN_DAYS_CLI)
    # Looser than the deployment value (60) though tighter than the package default
    # (90): the floor is the deployment value, not the default.
    _assert_refused_naming_the_key(
        _set(owner, TOKEN_DAYS_CLI, 75), "setting_floor_violation", TOKEN_DAYS_CLI
    )
    assert _rows(cluster, workspace) == rows_before
    assert _resolved(workspace, TOKEN_DAYS_CLI) == 60
    # Equal to the floor is not looser.
    assert _set(owner, TOKEN_DAYS_CLI, 60).ok
    assert _resolved(workspace, TOKEN_DAYS_CLI) == 60


def test_tightening_the_deployment_value_clamps_an_existing_row_left_in_place(
    cluster: ClusterSession,
    workspace: UUID,
    owner: WorkspaceContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TOKEN_DAYS_CLI_VARIABLE, "60")
    assert _set(owner, TOKEN_DAYS_CLI, 30).ok
    assert _resolved(workspace, TOKEN_DAYS_CLI) == 30
    monkeypatch.setenv(TOKEN_DAYS_CLI_VARIABLE, "10")
    assert _resolved(workspace, TOKEN_DAYS_CLI) == 10
    assert _rows(cluster, workspace)[TOKEN_DAYS_CLI] == "30"
    # And a write at the old, now-looser value is refused from this moment on.
    _assert_refused_naming_the_key(
        _set(owner, TOKEN_DAYS_CLI, 30), "setting_floor_violation", TOKEN_DAYS_CLI
    )
    assert _rows(cluster, workspace)[TOKEN_DAYS_CLI] == "30"


def test_the_other_three_comparators_through_the_harness_keys(
    cluster: ClusterSession,
    workspace: UUID,
    owner: WorkspaceContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # union: the list can only grow past the deployment's required items.
    monkeypatch.setenv("RHEO__harness__floor_union", "harness.confirm,harness.audit")
    _assert_refused_naming_the_key(
        _set(owner, HARNESS_FLOOR_UNION, ["harness.confirm"]),
        "setting_floor_violation",
        HARNESS_FLOOR_UNION,
    )
    assert _set(
        owner, HARNESS_FLOOR_UNION, ["harness.audit", "harness.confirm", "x"]
    ).ok
    assert _resolved(workspace, HARNESS_FLOOR_UNION) == [
        "harness.confirm", "harness.audit", "x",
    ]  # fmt: skip
    # subset: the list can only shrink within the deployment's allowed items.
    monkeypatch.setenv("RHEO__harness__floor_subset", "read,draft")
    _assert_refused_naming_the_key(
        _set(owner, HARNESS_FLOOR_SUBSET, ["read", "mutate"]),
        "setting_floor_violation",
        HARNESS_FLOOR_SUBSET,
    )
    assert _set(owner, HARNESS_FLOOR_SUBSET, ["draft"]).ok
    assert _resolved(workspace, HARNESS_FLOOR_SUBSET) == ["draft"]
    # and: true only where the deployment says true.
    monkeypatch.setenv("RHEO__harness__floor_and", "false")
    _assert_refused_naming_the_key(
        _set(owner, HARNESS_FLOOR_AND, True),
        "setting_floor_violation",
        HARNESS_FLOOR_AND,
    )
    assert _set(owner, HARNESS_FLOOR_AND, False).ok
    monkeypatch.setenv("RHEO__harness__floor_and", "true")
    assert _resolved(workspace, HARNESS_FLOOR_AND) is False
    assert _set(owner, HARNESS_FLOOR_AND, True).ok
    assert _resolved(workspace, HARNESS_FLOOR_AND) is True
    # min, once more through a harness key, clamped on read after a tighten.
    assert _set(owner, HARNESS_FLOOR_MIN, 50).ok
    monkeypatch.setenv("RHEO__harness__floor_min", "20")
    assert _resolved(workspace, HARNESS_FLOOR_MIN) == 20
    assert _rows(cluster, workspace)[HARNESS_FLOOR_MIN] == "50"


def test_a_type_mismatch_is_refused_setting_type(
    cluster: ClusterSession, workspace: UUID, owner: WorkspaceContext
) -> None:
    _assert_refused_naming_the_key(
        _set(owner, TOKEN_DAYS_CLI, "ninety"), "setting_type", TOKEN_DAYS_CLI
    )
    _assert_refused_naming_the_key(
        _set(owner, TOKEN_DAYS_CLI, True), "setting_type", TOKEN_DAYS_CLI
    )
    assert TOKEN_DAYS_CLI not in _rows(cluster, workspace)


# --- roles ----------------------------------------------------------------------------


def test_the_write_is_role_not_permitted_under_a_member_context(
    cluster: ClusterSession,
    workspace: UUID,
    owner: WorkspaceContext,
    member: WorkspaceContext,
) -> None:
    rows_before = _rows(cluster, workspace)
    outcome = _set(member, TOKEN_DAYS_CLI, 30)
    assert outcome.state == ROLE_NOT_PERMITTED, outcome
    assert outcome.error is not None and outcome.error.error_code == ROLE_NOT_PERMITTED
    assert _rows(cluster, workspace) == rows_before
    assert _set(owner, TOKEN_DAYS_CLI, 30).ok
    assert _rows(cluster, workspace)[TOKEN_DAYS_CLI] == "30"


def test_operator_is_not_an_implicit_superset_for_the_settings_operations(
    cluster: ClusterSession, workspace: UUID, owner: WorkspaceContext
) -> None:
    """The load-bearing sentence of this chunk: ``operator`` is enumerated where it
    applies (``core.workspace.status``) and is not a superset of ``owner``."""
    operator = context_for_operator(workspace)
    assert isinstance(operator, WorkspaceContext)
    rows_before = _rows(cluster, workspace)
    for name, payload in (
        (SETTINGS_SET, {"key": TOKEN_DAYS_CLI, "value": 30}),
        (SETTINGS_SET_MEMBER, {"key": HARNESS_MEMBER, "value": "operator-pref"}),
    ):
        outcome = dispatch(operator, name, payload)
        assert outcome.state == ROLE_NOT_PERMITTED, (name, outcome)
        assert outcome.error is not None
        assert outcome.error.error_code == ROLE_NOT_PERMITTED
        assert outcome.result is None
    assert _rows(cluster, workspace) == rows_before
    # The same operator may read status; the same owner may write.
    assert dispatch(operator, WORKSPACE_STATUS, {}).ok
    assert _set(owner, TOKEN_DAYS_CLI, 30).ok
    # And the ratified role sets, on the declarations themselves.
    assert SETTINGS_SET_DECLARATION.roles == frozenset({Role.OWNER})
    assert SETTINGS_SET_MEMBER_DECLARATION.roles == frozenset({Role.OWNER, Role.MEMBER})
    assert WORKSPACE_STATUS_DECLARATION.roles == frozenset(
        {Role.OWNER, Role.MEMBER, Role.OPERATOR}
    )
    assert Role.OPERATOR not in (
        SETTINGS_SET_DECLARATION.roles | SETTINGS_SET_MEMBER_DECLARATION.roles
    )


def test_set_member_writes_the_callers_own_row_for_owner_and_member(
    cluster: ClusterSession,
    workspace: UUID,
    owner: WorkspaceContext,
    member: WorkspaceContext,
) -> None:
    for ctx, value in ((owner, "owner-pref"), (member, "member-pref")):
        outcome = dispatch(
            ctx, SETTINGS_SET_MEMBER, {"key": HARNESS_MEMBER, "value": value}
        )
        assert outcome.ok, outcome
        assert outcome.result is not None
        assert outcome.result.model_dump()["scope"] == "member"  # type: ignore[union-attr]
    row = cluster.registry_row(workspace)
    engine = cluster.backend.pools.engine_for(row.database_name)
    with UnitOfWork(engine, row.database_name) as uow:
        assert owner.actor.id is not None and member.actor.id is not None
        assert member_settings(uow.connection, owner.actor.id) == {
            HARNESS_MEMBER: "owner-pref"
        }
        assert member_settings(uow.connection, member.actor.id) == {
            HARNESS_MEMBER: "member-pref"
        }
    assert (
        resolve(
            workspace_id=workspace,
            account_id=member.actor.id,
            source=PostgresOverrideSource(),
        )[HARNESS_MEMBER]
        == "member-pref"
    )
    # A workspace-scope key cannot be written as a member row, and vice versa.
    _assert_refused_naming_the_key(
        dispatch(member, SETTINGS_SET_MEMBER, {"key": TOKEN_DAYS_CLI, "value": 30}),
        "setting_scope",
        TOKEN_DAYS_CLI,
    )
    _assert_refused_naming_the_key(
        _set(owner, HARNESS_MEMBER, "not-a-workspace-key"),
        "setting_scope",
        HARNESS_MEMBER,
    )
