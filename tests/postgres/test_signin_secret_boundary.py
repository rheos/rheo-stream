"""B9 / fit-check.md Q2a: ``ResolvedSettings.__repr__`` never carries a resolved
value — only key names — closing reference disclosure (a ``secret://`` reference)
exactly as strictly as value disclosure. 08 extends this file with its own
log-line assertion over the dispatcher's own failure path (fit-check.md Q2b) —
this file's own original assertion above is the settings-repr half only.
"""

import logging
from uuid import UUID

import pytest
from conftest import ClusterSession
from harness.registry import NOTE_EXPLODE, enable_harness_module, register_harness
from rheo_contracts import WorkspaceContext
from rheo_core.boundary import context_for_operator
from rheo_core.operations import FAILED, dispatch
from rheo_core.settings import resolve
from rheo_core.storage.backend import UnitOfWork

pytestmark = pytest.mark.postgres


def test_resolved_settings_repr_never_carries_a_reference_or_a_value() -> None:
    settings = resolve()
    rendered = repr(settings)
    assert rendered.startswith("ResolvedSettings(")
    # storage.cluster_dsn_ref's package default is itself a live secret:// reference
    # (secret://env/RHEO_CLUSTER_DSN), so this is a real assertion, not a vacuous one:
    # before the fix, the old repr would have printed it verbatim.
    assert "secret://" not in rendered
    # Key NAMES are exactly what the repr is for; every declared key resolved here
    # shows up by name.
    for key in settings:
        assert key in rendered


def test_operation_failed_log_never_carries_a_sql_statement_or_its_parameters(
    cluster: ClusterSession,
    workspace: UUID,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """fit-check.md Q2b: ``logger.exception`` implied ``exc_info=True``, so a
    SQLAlchemy ``StatementError``'s formatted traceback — which carries
    ``[SQL: ...] [parameters: ...]`` — reached the log record even though the
    *returned* outcome was already safe (only ``type(exc).__name__``).
    ``dispatch.py`` now drops to ``logger.error`` with only the exception's class
    name in ``extra``, driven here through the harness's existing exploding
    operation (``tests/harness/registry.py`` ``_explode`` /
    ``NOTE_EXPLODE_DECLARATION``).
    """
    register_harness()
    row = cluster.registry_row(workspace)
    engine = cluster.backend.pools.engine_for(row.database_name)
    with UnitOfWork(engine, row.database_name) as uow:
        enable_harness_module(uow.connection)
        uow.commit()
    ctx = context_for_operator(workspace)
    assert isinstance(ctx, WorkspaceContext)

    caplog.set_level(logging.ERROR, logger="rheo_core.operations")
    message = "[SQL: SELECT 1] [parameters: {'token': 'hunter2'}]"
    outcome = dispatch(
        ctx, NOTE_EXPLODE, {"body": "written, then rolled back", "message": message}
    )
    assert outcome.state == FAILED

    (record,) = [r for r in caplog.records if r.getMessage() == "operation_failed"]
    assert record.exception_type == "RuntimeError"  # type: ignore[attr-defined]
    assert record.exc_info is None
    assert "[SQL:" not in record.getMessage()
    assert "[parameters:" not in record.getMessage()
    assert "[SQL:" not in caplog.text
    assert "[parameters:" not in caplog.text
    assert "hunter2" not in caplog.text
