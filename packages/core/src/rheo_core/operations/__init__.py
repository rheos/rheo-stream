"""The service registry: operation registration, authorization and dispatch.

- ``registry.py`` — ``OperationRegistry.register(decl, handler, *, origin)`` and
  ``authorize(ctx, name) -> Authorized | Refusal``; the process-wide ``REGISTRY``.
- ``dispatch.py`` — ``dispatch(ctx, name, payload) -> OperationOutcome``: the
  ``context_required`` check, ``authorize``, input validation, one unit of work
  through ``route(ctx)``, the handler, commit. No audit row, no operation record,
  no outbox (run 0c's).
- ``refusals.py`` — the state names, ``RegistrationRefused``, ``OperationRefused``.
- ``core_ops.py`` — ``core.workspace.status``, ``core.settings.set``,
  ``core.settings.set_member``, and ``register_core_operations()``.
"""

from rheo_core.operations.core_ops import (
    SETTINGS_SET,
    SETTINGS_SET_MEMBER,
    WORKSPACE_STATUS,
    SettingWrite,
    SettingWritten,
    WorkspaceStatus,
    WorkspaceStatusInput,
    register_core_operations,
)
from rheo_core.operations.dispatch import (
    OperationError,
    OperationOutcome,
    dispatch,
)
from rheo_core.operations.refusals import (
    AUTHORIZATION_STATES,
    FAILED,
    HANDLER_FAILED,
    INPUT_INVALID,
    MODULE_DISABLED,
    OPERATION_NOT_PERMITTED,
    OPERATION_UNKNOWN,
    OUTPUT_INVALID,
    ROLE_NOT_PERMITTED,
    SUCCEEDED,
    OperationRefused,
    RegistrationRefused,
)
from rheo_core.operations.registry import (
    CORE_MODULE_ID,
    HARNESS_MODULE_ID,
    REGISTRY,
    Authorized,
    Handler,
    OperationRegistry,
    RegisteredOperation,
    authorize,
    check_origin,
    module_id_for_origin,
    register,
    reserved_input_fields,
)

__all__ = [
    "AUTHORIZATION_STATES",
    "CORE_MODULE_ID",
    "FAILED",
    "HANDLER_FAILED",
    "HARNESS_MODULE_ID",
    "INPUT_INVALID",
    "MODULE_DISABLED",
    "OPERATION_NOT_PERMITTED",
    "OPERATION_UNKNOWN",
    "OUTPUT_INVALID",
    "REGISTRY",
    "ROLE_NOT_PERMITTED",
    "SETTINGS_SET",
    "SETTINGS_SET_MEMBER",
    "SUCCEEDED",
    "WORKSPACE_STATUS",
    "Authorized",
    "Handler",
    "OperationError",
    "OperationOutcome",
    "OperationRefused",
    "OperationRegistry",
    "RegisteredOperation",
    "RegistrationRefused",
    "SettingWrite",
    "SettingWritten",
    "WorkspaceStatus",
    "WorkspaceStatusInput",
    "authorize",
    "check_origin",
    "dispatch",
    "module_id_for_origin",
    "register",
    "register_core_operations",
    "reserved_input_fields",
]
