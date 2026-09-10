"""B16, the migration half, and the orchestrator's refusals.

Seams: ``env.py``'s no-connection ``RuntimeError``; ``run_chain``'s
``current_database()`` assertion and its transaction requirement; the advisory lock
(two concurrent orchestrators serialise, the second observed waiting in ``pg_locks``);
``schema_ahead``; a failing core revision leaving ``unavailable`` with the error while
startup completes; the exact table sets each chain creates (the hard 0c boundary); and
``tests/conftest.py``'s own fail-fast contract, proved in a child pytest.
"""

import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from conftest import REMEDY, ClusterSession, MakeWorkspace, run_pytest_in_subprocess
from rheo_core.migrations.orchestrator import (
    ADVISORY_LOCK_KEY,
    CHAINS,
    CONTROL_CHAIN,
    CORE_CHAIN,
    MigrationResult,
    build_config,
    known_revisions,
    migrate_active_workspaces,
    migrate_control,
    migrate_workspace,
    recorded_revisions,
    run_chain,
    script_location,
)
from rheo_core.storage.backend import (
    DATABASE_MISMATCH,
    SCHEMA_AHEAD,
    WORKSPACE_MISSING,
    WORKSPACE_UNAVAILABLE,
    StorageRefusal,
)
from rheo_core.storage.control_plane import WorkspaceState
from rheo_core.storage.postgres import advisory_lock
from rheo_core.storage.provisioning import repair
from rheo_core.storage.routing import active_workspace
from sqlalchemy import Engine, text

pytestmark = pytest.mark.postgres

_REPO_ROOT = Path(__file__).resolve().parents[2]

CONTROL_TABLES = {
    "account",
    "identity",
    "workspace",
    "membership",
    "session",
    "session_secret",
    "session_grant",
    "access_token",
    "access_token_operation",
    "identity_provider",
}
CORE_TABLES = {
    "workspace_composition",
    "module_state",
    "module_schema_version",
    "workspace_setting",
    "member_setting",
    "member_credential",
}
# Owned by run 0c's chain steps; their presence here would contaminate the trial.
ZERO_C_TABLES = {
    "outbox_event",
    "event_delivery",
    "consumer_processed",
    "job",
    "schedule",
    "operation",
    "audit_record",
    "approval",
    "approval_payload",
    "standing_grant",
    "standing_grant_operation",
    "external_action",
}


def tables_in(engine: Engine, schema: str) -> set[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :schema"
            ),
            {"schema": schema},
        ).scalars()
        return {str(name) for name in rows}


def workspace_engine(cluster: ClusterSession, workspace_id: UUID) -> tuple[str, Engine]:
    row = cluster.registry_row(workspace_id)
    return row.database_name, cluster.backend.pools.engine_for(row.database_name)


def wait_until(condition: Callable[[], bool], *, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


# --- no Alembic by hand ---------------------------------------------------------------


@pytest.mark.parametrize("chain", CHAINS)
def test_env_refuses_without_the_orchestrator_connection(chain: str) -> None:
    config = build_config(chain)
    assert config.get_main_option("sqlalchemy.url") is None
    with pytest.raises(RuntimeError, match="orchestrator"):
        command.upgrade(config, "head")


def test_no_alembic_ini_is_tracked_and_each_chain_knows_one_revision() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=_REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.split("\0")
    assert not [p for p in tracked if p.endswith("alembic.ini")]
    for chain in CHAINS:
        assert not (script_location(chain) / "alembic.ini").exists()
    assert known_revisions(CONTROL_CHAIN) == {"0001_control_plane"}
    assert known_revisions(CORE_CHAIN) == {"0001_core_schema"}


# --- the two chains, exactly ----------------------------------------------------------


def test_control_chain_creates_exactly_the_ten_tables(cluster: ClusterSession) -> None:
    engine = cluster.backend.control_engine
    assert tables_in(engine, "control") == CONTROL_TABLES | {"alembic_version_control"}
    with engine.connect() as connection:
        assert recorded_revisions(connection, CONTROL_CHAIN) == {"0001_control_plane"}


def test_core_chain_creates_exactly_the_six_tables(
    cluster: ClusterSession, workspace: UUID
) -> None:
    _, engine = workspace_engine(cluster, workspace)
    names = tables_in(engine, "core")
    assert names == CORE_TABLES | {"alembic_version_core"}
    assert not names & ZERO_C_TABLES
    with engine.connect() as connection:
        assert recorded_revisions(connection, CORE_CHAIN) == {"0001_core_schema"}


def test_migrate_control_is_idempotent_and_survives_an_existing_database(
    cluster: ClusterSession,
) -> None:
    # The session already created the control database: the duplicate is success.
    assert cluster.backend.ensure_control_database() is False
    first = migrate_control(cluster.backend)
    second = migrate_control(cluster.backend)
    assert (
        first
        == second
        == MigrationResult(None, cluster.control_database, CONTROL_CHAIN, True, None)
    )


# --- the orchestrator's refusals ------------------------------------------------------


def test_current_database_assertion_refuses_a_wrong_database(
    cluster: ClusterSession, workspace: UUID
) -> None:
    database_name, engine = workspace_engine(cluster, workspace)
    with engine.begin() as connection:
        with pytest.raises(StorageRefusal) as excinfo:
            run_chain(
                connection, CORE_CHAIN, expected_database=cluster.control_database
            )
    assert excinfo.value.state == DATABASE_MISMATCH
    assert database_name in excinfo.value.detail
    # Refused before anything ran: the workspace is untouched and still active.
    assert tables_in(engine, "core") == CORE_TABLES | {"alembic_version_core"}
    assert cluster.registry_row(workspace).state is WorkspaceState.ACTIVE


def test_run_chain_refuses_a_connection_outside_a_transaction(
    cluster: ClusterSession, workspace: UUID
) -> None:
    database_name, engine = workspace_engine(cluster, workspace)
    with engine.connect() as connection:
        with pytest.raises(ValueError, match="transaction"):
            run_chain(connection, CORE_CHAIN, expected_database=database_name)


def test_migrate_workspace_refuses_an_unknown_id_and_module_chains(
    cluster: ClusterSession, workspace: UUID
) -> None:
    with pytest.raises(StorageRefusal) as excinfo:
        migrate_workspace(cluster.backend, UUID(int=0))
    assert excinfo.value.state == WORKSPACE_MISSING
    with pytest.raises(NotImplementedError, match="phase 2"):
        migrate_workspace(cluster.backend, workspace, chains=("recallatron",))
    with pytest.raises(ValueError, match="control chain"):
        migrate_workspace(cluster.backend, workspace, chains=(CONTROL_CHAIN,))
    database_name, engine = workspace_engine(cluster, workspace)
    with engine.begin() as connection:
        with pytest.raises(ValueError, match="unknown migration chain"):
            run_chain(connection, "nope", expected_database=database_name)
    # Every refusal above happened before any write: the workspace is untouched.
    assert cluster.registry_row(workspace).state is WorkspaceState.ACTIVE


# --- failure handling ----------------------------------------------------------------


def test_failing_core_revision_marks_unavailable_and_startup_completes(
    cluster: ClusterSession, make_workspace: MakeWorkspace
) -> None:
    broken = make_workspace()
    healthy = make_workspace()
    # Forget the applied revision: the chain re-runs 0001 against tables that exist,
    # and the revision fails (the tables are created with checkfirst=False).
    broken_name, broken_engine = workspace_engine(cluster, broken)
    with broken_engine.begin() as connection:
        connection.execute(text("DELETE FROM core.alembic_version_core"))

    results = migrate_active_workspaces(cluster.backend)

    by_id = {result.workspace_id: result for result in results}
    assert by_id[broken].ok is False
    assert by_id[broken].detail is not None
    assert "already exists" in by_id[broken].detail
    assert by_id[healthy].ok is True
    # The loop continued past the failure: the broken workspace ran first.
    order = [result.workspace_id for result in results]
    assert order.index(broken) < order.index(healthy)

    row = cluster.registry_row(broken)
    assert row.state is WorkspaceState.UNAVAILABLE
    assert row.state_detail is not None and "already exists" in row.state_detail
    assert cluster.registry_row(healthy).state is WorkspaceState.ACTIVE

    # Refused at routing, and the failed transaction rolled back cleanly.
    with pytest.raises(StorageRefusal) as excinfo:
        active_workspace(broken)
    assert excinfo.value.state == WORKSPACE_UNAVAILABLE
    assert excinfo.value.workspace_state == "unavailable"
    assert tables_in(broken_engine, "core") == CORE_TABLES | {"alembic_version_core"}

    # Restoring the version row and repairing brings the workspace back.
    with broken_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO core.alembic_version_core (version_num) VALUES (:v)"),
            {"v": "0001_core_schema"},
        )
    repair(broken)
    assert cluster.registry_row(broken).state is WorkspaceState.ACTIVE


def test_schema_ahead_marks_unavailable_and_refuses_repair(
    cluster: ClusterSession, workspace: UUID
) -> None:
    database_name, engine = workspace_engine(cluster, workspace)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE core.alembic_version_core SET version_num = :v"),
            {"v": "9999_from_the_future"},
        )

    result = migrate_workspace(cluster.backend, workspace)
    assert result == MigrationResult(
        workspace, database_name, CORE_CHAIN, False, SCHEMA_AHEAD
    )
    row = cluster.registry_row(workspace)
    assert row.state is WorkspaceState.UNAVAILABLE
    assert row.state_detail == "schema_ahead"
    with pytest.raises(StorageRefusal) as excinfo:
        active_workspace(workspace)
    assert excinfo.value.state == WORKSPACE_UNAVAILABLE

    # Repair cannot serve a database the code does not know.
    with pytest.raises(StorageRefusal) as excinfo:
        repair(workspace)
    assert excinfo.value.state == SCHEMA_AHEAD
    assert cluster.registry_row(workspace).state is WorkspaceState.UNAVAILABLE

    # Once the recorded revision is one the code knows, repair completes.
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE core.alembic_version_core SET version_num = :v"),
            {"v": "0001_core_schema"},
        )
    repair(workspace)
    assert cluster.registry_row(workspace).state is WorkspaceState.ACTIVE


def test_two_concurrent_orchestrators_serialise_on_the_advisory_lock(
    cluster: ClusterSession, workspace: UUID
) -> None:
    database_name, engine = workspace_engine(cluster, workspace)
    key_high, key_low = ADVISORY_LOCK_KEY >> 32, ADVISORY_LOCK_KEY & 0xFFFFFFFF

    def waiters() -> int:
        with engine.connect() as connection:
            count = connection.execute(
                text(
                    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                    "AND database = (SELECT oid FROM pg_database WHERE datname = :db) "
                    "AND classid = CAST(:hi AS oid) AND objid = CAST(:lo AS oid) "
                    "AND NOT granted"
                ),
                {"db": database_name, "hi": key_high, "lo": key_low},
            ).scalar_one()
        return int(count)

    # The first orchestrator: hold the chain lock inside an open transaction.
    holder = engine.connect()
    holder.begin()
    advisory_lock(holder, ADVISORY_LOCK_KEY)
    assert waiters() == 0

    outcome: dict[str, object] = {}

    def second_orchestrator() -> None:
        try:
            outcome["result"] = migrate_workspace(cluster.backend, workspace)
        except BaseException as exc:  # surfaced through the assertions below
            outcome["error"] = exc

    thread = threading.Thread(target=second_orchestrator)
    thread.start()
    try:
        # The second observes the lock: it is queued, ungranted, on the same key.
        assert wait_until(lambda: waiters() == 1, timeout=10), (
            "the second orchestrator never queued on the advisory lock"
        )
        thread.join(0.5)
        assert thread.is_alive(), "the second orchestrator did not wait for the lock"
        assert "result" not in outcome
    finally:
        holder.rollback()
        holder.close()
    thread.join(30)
    assert not thread.is_alive()
    assert "error" not in outcome, outcome.get("error")
    result = outcome["result"]
    assert isinstance(result, MigrationResult) and result.ok
    assert waiters() == 0
    assert cluster.registry_row(workspace).state is WorkspaceState.ACTIVE


# --- the harness's own contract -------------------------------------------------------


def test_suite_fails_fast_when_the_cluster_is_unreachable() -> None:
    """A child pytest pointed at a closed port exits naming the remedy; nothing is
    skipped and nothing passes."""
    unreachable = (
        "postgresql://rheo:rheo_dev_only@127.0.0.1:1/postgres?connect_timeout=2"
    )
    completed = run_pytest_in_subprocess(
        "tests/test_contracts.py",
        extra_env={"RHEO_TEST_CLUSTER_DSN": unreachable},
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode != 0, output
    assert REMEDY in output, output
    assert "unreachable" in output, output
    assert " passed" not in output, output
    assert "skipped" not in output, output
