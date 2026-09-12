"""The operation-declaration subset of the module contract that the registry needs.

Source of truth: ``docs/architecture/module-contract.md`` § Operations, tools, events.

Not here, and deliberately:

- ``ToolDeclaration`` arrives in C8 (run 0b2), with the MCP facade that reads it. A tool
  type with no reader is a shape guessed a run early.
- ``ModuleManifest`` itself is phase 2, together with module install/enable lifecycle.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from rheo_contracts.context import Role
from rheo_contracts.safety import SafetyClass

RESERVED_INPUT_FIELDS = frozenset(
    {
        "workspace_id",
        "workspace",
        "actor_id",
        "actor",
        "tenant_id",
        "database",
        "schema",
        "connection_string",
        "dsn",
        "sql",
        "table_name",
        "statement",
    }
)
"""Input-model field names registration refuses, verbatim from the module contract.

The last three make criterion 20's "accepts no SQL, table name, or query fragment" a
mechanical check over the registered input models. This is the single list the operation
registry and criterion 6's test share; do not restate it anywhere else.
"""


class Idempotency(StrEnum):
    """How a repeated call is made to mean one thing.

    ``KEYED`` is absent on purpose: ``module-contract.md`` says it "arrives with phase
    five", and release one has no keyed idempotency and no stored-result table.

    ``NATURAL`` names a unique index that makes a repeat the same row. The registry is
    meant to assert that index is present in the module's schema **at module install**,
    which is phase 2 — so the 0b1 registry accepts ``NONE`` and ``NATURAL`` and performs
    no index validation. Do not go looking for that check; it is not written yet.
    """

    NONE = "none"
    NATURAL = "natural"


class AuditSpec(BaseModel):
    """What an operation's audit row records about its subject.

    Exactly one field. ``subject_field`` is the name of the input-model field carrying
    the subject :class:`~rheo_contracts.refs.RecordRef`, and ``None`` when the operation
    acts on no record (``core.settings.set`` and ``core.settings.set_member`` are the
    release-one examples). Grounded in ``intake-and-events.md`` (the audit row's
    ``subject_ref text null`` comes "From the operation's ``AuditSpec``") and
    ``confirmation-and-safety.md`` (``AuditSpec(subject = the receipt)``).

    This shape is frozen for 0c2's audit dispatcher. It is declared and stored only: no
    code in run 0b writes an audit row.
    """

    model_config = ConfigDict(frozen=True)

    subject_field: str | None


class OperationDeclaration(BaseModel):
    """What a module tells the registry about one operation.

    The subset of ``module-contract.md`` § Operations that the release-one registry
    needs. ``guards`` and ``long_running`` belong to the dispatcher work in 0c and are
    not declared here yet.

    **The handler is not a field, and that is a named deviation.** The ratified contract
    types it ``Callable[[WorkspaceContext, UnitOfWork, input], output]``, but
    ``UnitOfWork`` lives in ``rheo_core.storage`` and ``rheo_contracts`` may import only
    stdlib, ``pydantic`` and ``rheo_contracts`` — the boundary the contracts import scan
    enforces. So the handler is passed alongside the declaration at registration,
    ``OperationRegistry.register(decl, handler, *, origin)`` in
    ``rheo_core.operations``, where ``UnitOfWork`` is importable and mypy strict checks
    the signature. Typing it ``Callable[..., BaseModel]`` here was the alternative, and
    was rejected: it keeps the ratified field list at the cost of the one type check
    that matters.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    safety_class: SafetyClass
    roles: frozenset[Role] = frozenset({Role.OWNER, Role.MEMBER})
    input_model: type[BaseModel]
    output: type[BaseModel]
    idempotency: Idempotency
    audit: AuditSpec | None = None
    """Required non-``None`` above ``READ``.

    The refusal that enforces it — "class above ``READ`` with ``audit = None``:
    refused, naming the operation" (``module-contract.md`` § Registration rules) —
    arrives with 0c2's registration assertions (criterion 14). The 0b1 registry
    stores the declaration and does not check this field.
    """
