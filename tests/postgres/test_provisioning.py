"""B16, the provisioning half: the create path, the five ``after_step`` fault
injections with ``repair`` to ``active``, and the seam's profile gate.

Seams: ``rheo_core.storage.provisioning.provision()`` / ``repair()`` and the
``PROVISION_STEPS`` fault-injection seam. Every assertion reads the registry row and
the workspace database back through the repositories; no private function of the
provisioning module is monkeypatched.
"""

import re
from collections.abc import Callable
from importlib import metadata
from uuid import UUID

import pytest
from conftest import ClusterSession, MakeWorkspace
from harness.settings_keys import HARNESS_EXPLICIT
from rheo_contracts import CONTRACT_VERSION, Role
from rheo_core.refs import uuid7
from rheo_core.storage import control_tables
from rheo_core.storage.backend import (
    ACCOUNT_MISSING,
    IDENTITY_EXISTS,
    SLUG_TAKEN,
    WORKSPACE_EXISTS,
    WORKSPACE_MISSING,
    StorageRefusal,
    UnitOfWork,
)
from rheo_core.storage.control_plane import (
    get_account,
    get_identity,
    get_membership,
    insert_account,
    insert_identity,
)
from rheo_core.storage.control_tables import WorkspaceState
from rheo_core.storage.provisioning import (
    PROVISION_STEPS,
    STEP_ACTIVATE,
    STEP_CREATE_DATABASE,
    STEP_INSERT_REGISTRY_ROW,
    STEP_MIGRATE_CORE,
    STEP_WRITE_DEFAULT_SETTINGS,
    core_version,
    database_name_for,
    provision,
    repair,
)
from rheo_core.storage.repositories import (
    list_module_states,
    read_composition,
    workspace_settings,
)
from sqlalchemy import select, text

pytestmark = pytest.mark.postgres

DATABASE_NAME = re.compile(r"ws_[0-9a-f]{32}")


class Injected(Exception):
    """Raised from the ``after_step`` callback to simulate a crash."""


def fault_after(step: str, seen: list[str]) -> Callable[[str], None]:
    def after_step(name: str) -> None:
        seen.append(name)
        if name == step:
            raise Injected(name)

    return after_step


def core_object_present(cluster: ClusterSession, workspace_id: UUID, name: str) -> bool:
    row = cluster.registry_row(workspace_id)
    engine = cluster.backend.pools.engine_for(row.database_name)
    with engine.connect() as connection:
        found = connection.execute(
            text("SELECT to_regclass(:name)"), {"name": f"core.{name}"}
        ).scalar_one()
    return found is not None


def workspace_is_whole(cluster: ClusterSession, workspace_id: UUID) -> None:
    row = cluster.registry_row(workspace_id)
    assert row.state is WorkspaceState.ACTIVE
    assert row.state_detail == STEP_ACTIVATE
    assert cluster.backend.database_exists(row.database_name)
    engine = cluster.backend.pools.engine_for(row.database_name)
    with UnitOfWork(engine, row.database_name) as uow:
        composition = read_composition(uow.connection)
        rows = workspace_settings(uow.connection)
        # No module exists before phase 2: the module table reads empty.
        assert list_module_states(uow.connection) == ()
    assert composition is not None
    assert composition.core_version == core_version()
    assert composition.core_contract_version == CONTRACT_VERSION
    assert rows == {HARNESS_EXPLICIT: "harness-package-default"}


# --- the create path ------------------------------------------------------------------


def test_provision_steps_is_the_ratified_ordered_table() -> None:
    assert PROVISION_STEPS == (
        "insert_registry_row",
        "create_database",
        "migrate_core",
        "write_default_settings",
        "activate",
    )


def test_create_leaves_state_active_with_a_derived_database(
    cluster: ClusterSession, make_workspace: MakeWorkspace, owner_account_id: UUID
) -> None:
    workspace_id = make_workspace()
    row = cluster.registry_row(workspace_id)

    assert (
        row.database_name == database_name_for(workspace_id) == f"ws_{workspace_id.hex}"
    )
    assert DATABASE_NAME.fullmatch(row.database_name)
    assert row.slug == str(workspace_id) == row.display_name
    workspace_is_whole(cluster, workspace_id)

    # Step 1 wrote the owner membership, in the same transaction as the row.
    with cluster.backend.control_engine.connect() as connection:
        membership = get_membership(
            connection, account_id=owner_account_id, workspace_id=workspace_id
        )
    assert membership is not None
    assert membership.role is Role.OWNER

    # The composition's core version is the installed distribution's, not a literal.
    assert core_version() == metadata.version("rheo-core")


def test_create_accepts_an_explicit_slug(
    cluster: ClusterSession, make_workspace: MakeWorkspace
) -> None:
    workspace_id = make_workspace(slug="alpha-team")
    row = cluster.registry_row(workspace_id)
    assert (row.slug, row.display_name) == ("alpha-team", "alpha-team")
    with pytest.raises(ValueError, match="slug"):
        make_workspace(slug="Not A Slug")


# --- the five fault injections, and repair --------------------------------------------


@pytest.mark.parametrize("step", PROVISION_STEPS)
def test_fault_after_each_step_is_recorded_and_repair_completes(
    cluster: ClusterSession, make_workspace: MakeWorkspace, step: str
) -> None:
    seen: list[str] = []
    workspace_id = uuid7()
    with pytest.raises(Injected, match=step):
        make_workspace(workspace_id=workspace_id, after_step=fault_after(step, seen))

    # The callback saw every step up to and including the faulted one, in order.
    assert seen == list(PROVISION_STEPS[: PROVISION_STEPS.index(step) + 1])

    row = cluster.registry_row(workspace_id)
    assert row.state_detail == step
    if step == STEP_ACTIVATE:
        assert row.state is WorkspaceState.ACTIVE
    else:
        assert row.state is WorkspaceState.PROVISIONING

    # Nothing past the fault ran.
    if step == STEP_INSERT_REGISTRY_ROW:
        assert not cluster.backend.database_exists(row.database_name)
    elif step == STEP_CREATE_DATABASE:
        assert cluster.backend.database_exists(row.database_name)
        assert not core_object_present(cluster, workspace_id, "workspace_composition")
    elif step == STEP_MIGRATE_CORE:
        assert core_object_present(cluster, workspace_id, "workspace_composition")
        engine = cluster.backend.pools.engine_for(row.database_name)
        with UnitOfWork(engine, row.database_name) as uow:
            assert workspace_settings(uow.connection) == {}
    elif step == STEP_WRITE_DEFAULT_SETTINGS:
        engine = cluster.backend.pools.engine_for(row.database_name)
        with UnitOfWork(engine, row.database_name) as uow:
            assert workspace_settings(uow.connection) == {
                HARNESS_EXPLICIT: "harness-package-default"
            }

    repair(workspace_id)
    workspace_is_whole(cluster, workspace_id)

    # Repair of an active workspace is a no-op.
    repair(workspace_id)
    workspace_is_whole(cluster, workspace_id)


def test_retry_after_a_crash_between_create_database_and_its_record(
    cluster: ClusterSession, make_workspace: MakeWorkspace
) -> None:
    """Step 2 ran ``CREATE DATABASE`` but the process died before recording it:
    "already exists" with a row still ``provisioning`` is a retry, not a failure."""
    workspace_id = uuid7()
    with pytest.raises(Injected):
        make_workspace(
            workspace_id=workspace_id,
            after_step=fault_after(STEP_INSERT_REGISTRY_ROW, []),
        )
    created = cluster.backend.ensure_database(
        database_name_for(workspace_id), template=cluster.backend.template_database
    )
    assert created is True
    assert cluster.registry_row(workspace_id).state_detail == STEP_INSERT_REGISTRY_ROW

    repair(workspace_id)
    workspace_is_whole(cluster, workspace_id)


def test_provision_again_while_provisioning_is_a_retry(
    cluster: ClusterSession, make_workspace: MakeWorkspace, owner_account_id: UUID
) -> None:
    workspace_id = uuid7()
    with pytest.raises(Injected):
        make_workspace(
            workspace_id=workspace_id, after_step=fault_after(STEP_MIGRATE_CORE, [])
        )
    provision(workspace_id, owner_account_id=owner_account_id)
    workspace_is_whole(cluster, workspace_id)


# --- refusals -------------------------------------------------------------------------


def test_after_step_is_refused_outside_the_test_profile(
    cluster: ClusterSession, owner_account_id: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RHEO_PROFILE", "production")
    workspace_id = uuid7()
    cluster.record(database_name_for(workspace_id))
    with pytest.raises(ValueError, match="profile"):
        provision(
            workspace_id, owner_account_id=owner_account_id, after_step=lambda _: None
        )
    # Refused at the call site: nothing was written.
    assert cluster.registry_row_or_none(workspace_id) is None
    assert not cluster.backend.database_exists(database_name_for(workspace_id))


def test_provision_refuses_an_existing_active_workspace(
    cluster: ClusterSession, make_workspace: MakeWorkspace, owner_account_id: UUID
) -> None:
    workspace_id = make_workspace()
    with pytest.raises(StorageRefusal) as excinfo:
        provision(workspace_id, owner_account_id=owner_account_id)
    assert excinfo.value.state == WORKSPACE_EXISTS
    workspace_is_whole(cluster, workspace_id)


def test_provision_refuses_a_missing_owner_without_a_partial_row(
    cluster: ClusterSession, harness_keys: None
) -> None:
    workspace_id = uuid7()
    cluster.record(database_name_for(workspace_id))
    with pytest.raises(StorageRefusal) as excinfo:
        provision(workspace_id, owner_account_id=uuid7())
    assert excinfo.value.state == ACCOUNT_MISSING
    # The row and the membership are one transaction: no row survives.
    assert cluster.registry_row_or_none(workspace_id) is None
    assert not cluster.backend.database_exists(database_name_for(workspace_id))


def test_provision_refuses_a_taken_slug(
    cluster: ClusterSession, make_workspace: MakeWorkspace, owner_account_id: UUID
) -> None:
    make_workspace(slug="taken-slug")
    workspace_id = uuid7()
    cluster.record(database_name_for(workspace_id))
    with pytest.raises(StorageRefusal) as excinfo:
        provision(workspace_id, owner_account_id=owner_account_id, slug="taken-slug")
    assert excinfo.value.state == SLUG_TAKEN
    assert cluster.registry_row_or_none(workspace_id) is None


def test_repair_refuses_an_unknown_workspace(cluster: ClusterSession) -> None:
    with pytest.raises(StorageRefusal) as excinfo:
        repair(uuid7())
    assert excinfo.value.state == WORKSPACE_MISSING


def test_identifiers_must_be_uuids(owner_account_id: UUID) -> None:
    with pytest.raises(TypeError):
        provision("ws_not_a_uuid", owner_account_id=owner_account_id)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        database_name_for("ws_not_a_uuid")  # type: ignore[arg-type]


def memberships_of(
    cluster: ClusterSession, workspace_id: UUID
) -> list[tuple[UUID, str]]:
    table = control_tables.membership
    with cluster.backend.control_engine.connect() as connection:
        rows = connection.execute(
            select(table.c.account_id, table.c.role)
            .where(table.c.workspace_id == workspace_id)
            .order_by(table.c.created_at)
        )
        return [(account_id, str(role)) for account_id, role in rows]


def test_retry_with_a_different_owner_is_refused_and_adds_no_second_owner(
    cluster: ClusterSession, make_workspace: MakeWorkspace, owner_account_id: UUID
) -> None:
    workspace_id = uuid7()
    with pytest.raises(Injected):
        make_workspace(
            workspace_id=workspace_id,
            after_step=fault_after(STEP_INSERT_REGISTRY_ROW, []),
        )
    with cluster.backend.control_engine.begin() as connection:
        other_owner = insert_account(connection, display_name="member-two").id

    with pytest.raises(StorageRefusal) as excinfo:
        provision(workspace_id, owner_account_id=other_owner)
    assert excinfo.value.state == WORKSPACE_EXISTS
    assert memberships_of(cluster, workspace_id) == [(owner_account_id, "owner")]
    assert cluster.registry_row(workspace_id).state is WorkspaceState.PROVISIONING

    # The original owner's retry completes, and there is still exactly one owner.
    provision(workspace_id, owner_account_id=owner_account_id)
    workspace_is_whole(cluster, workspace_id)
    assert memberships_of(cluster, workspace_id) == [(owner_account_id, "owner")]


# --- the account and identity repositories ---------------------------------------


def test_identity_refusals_and_lookups(
    cluster: ClusterSession, owner_account_id: UUID
) -> None:
    engine = cluster.backend.control_engine
    subject = f"subject-{uuid7().hex[:8]}"

    with pytest.raises(StorageRefusal) as excinfo:
        with engine.begin() as connection:
            insert_identity(
                connection,
                account_id=uuid7(),
                provider_id="github",
                provider_subject=subject,
            )
    assert excinfo.value.state == ACCOUNT_MISSING

    with engine.begin() as connection:
        identity = insert_identity(
            connection,
            account_id=owner_account_id,
            provider_id="github",
            provider_subject=subject,
            email="owner-one@example.test",
            email_verified=True,
        )
    with pytest.raises(StorageRefusal) as excinfo:
        with engine.begin() as connection:
            insert_identity(
                connection,
                account_id=owner_account_id,
                provider_id="github",
                provider_subject=subject,
            )
    assert excinfo.value.state == IDENTITY_EXISTS

    with engine.connect() as connection:
        found = get_identity(connection, provider_id="github", provider_subject=subject)
        assert found == identity
        assert found.email_verified is True
        assert (
            get_identity(connection, provider_id="github", provider_subject="nope")
            is None
        )
        account = get_account(connection, owner_account_id)
        assert account is not None
        assert (account.display_name, account.disabled_at) == ("owner-one", None)
        assert get_account(connection, uuid7()) is None
        with pytest.raises(ValueError, match="provider"):
            insert_identity(
                connection,
                account_id=owner_account_id,
                provider_id="",
                provider_subject="x",
            )
        with pytest.raises(ValueError, match="display name"):
            insert_account(connection, display_name="   ")
