"""The three named package sets (B7) and the MCP facade's tool table.

Each set is a rule evaluated against the registry **at issuance** (``issue.py``
calls these at the moment a token is minted), never an enumerated list stored
anywhere, so a set tracks the registry live:

- ``read_only``: every registered operation of ``SafetyClass.READ``.
- ``agent_default``: every operation named by a registered ``ToolDeclaration`` in
  :data:`REGISTERED_TOOLS`, intersected with the registry's actually registered
  operation names -- a declared tool naming an operation that failed to register
  does not silently leak into the set.
- ``cli_full``: every registered operation except :data:`NON_TOKEN_ISSUABLE`.

:data:`REGISTERED_TOOLS` is also the MCP facade's tool table
(``apps/mcp/src/rheo_app_mcp/tools.py`` imports this exact tuple -- one
declaration site, read from both directions, so the façade and this module's
policy can never drift apart). It always names both tools this run registers:
``workspace_status`` (production) and ``harness_get_note`` (test profile only).
The test-profile gate is not a runtime check *here* -- ``agent_default``'s
intersection with the registry's live names is what excludes
``harness.note.get`` outside a test run, because that operation is only ever
actually registered by ``tests/harness/registry.py``'s own ``register_harness()``
(itself gated to ``profile = test`` by the registry's origin check). Declaring
both tools unconditionally and letting registry presence do the filtering is
"gating its inclusion the same way the harness gates its own registrations":
the harness's registration attempt is what is profile-gated, not a second check
duplicated here.

This module defines its own tiny input models for both tools rather than
importing ``rheo_core.operations.core_ops`` or ``tests/harness/registry.py``'s:
the latter would make a shipped package depend on test-only code that is never
installed. Duplicating two small, stable shapes is cheaper than that.

**``REGISTRY``/``OperationRegistry`` are imported lazily, inside each function
below, not at module level.** ``core_ops.py`` imports ``rheo_core.tokens.issue``
(which imports this module for :data:`PACKAGE_SETS`), and ``rheo_core.
operations``'s own ``__init__.py`` imports ``core_ops.py`` as its first
statement -- so a module-level ``from rheo_core.operations.registry import
REGISTRY`` here would close a real cycle the moment anything imports this
module (or ``tokens.issue``) before ``rheo_core.operations`` has been touched
at all: ``operations.registry`` -> (via the package ``__init__``) ->
``core_ops.py`` -> ``tokens.issue`` -> this module -> ``operations.registry``
(still mid-init). Deferring the import to call time -- well after every module
involved has finished loading, in any realistic caller -- avoids it
regardless of import order.
"""

from collections.abc import Callable
from typing import Final

from pydantic import BaseModel, ConfigDict
from rheo_contracts import SafetyClass, ToolDeclaration

from rheo_core.tokens.policy import NON_TOKEN_ISSUABLE

_WORKSPACE_STATUS_OPERATION: Final = "core.workspace.status"
"""Duplicated from ``operations/core_ops.py``'s ``WORKSPACE_STATUS`` -- see the
module docstring's cycle note. The two are proven equal by
``test_tokens.py``'s own ``agent_default`` assertion, not by a shared import."""

_HARNESS_NOTE_GET_OPERATION: Final = "harness.note.get"
"""Duplicated from ``tests/harness/registry.py``'s ``NOTE_GET`` -- that file's own
module docstring cross-references this pairing. Same reasoning as
``_WORKSPACE_STATUS_OPERATION`` above, plus the production/test boundary:
``rheo_core`` (shipped) must not import ``tests/harness`` (never installed)."""


class _WorkspaceStatusToolInput(BaseModel):
    """Mirrors ``operations/core_ops.py``'s ``WorkspaceStatusInput``: no fields,
    the workspace comes from the context. Declared locally -- see module
    docstring's cycle note."""

    model_config = ConfigDict(extra="ignore")


class _HarnessNoteRefToolInput(BaseModel):
    """Mirrors ``tests/harness/registry.py``'s ``NoteRefInput`` (``ref: str``).
    Declared locally -- see module docstring's boundary note."""

    model_config = ConfigDict(extra="ignore")

    ref: str


WORKSPACE_STATUS_TOOL: Final[ToolDeclaration] = ToolDeclaration(
    name="workspace_status",
    operation=_WORKSPACE_STATUS_OPERATION,
    input_model=_WorkspaceStatusToolInput,
)

HARNESS_GET_NOTE_TOOL: Final[ToolDeclaration] = ToolDeclaration(
    name="harness_get_note",
    operation=_HARNESS_NOTE_GET_OPERATION,
    input_model=_HarnessNoteRefToolInput,
)

REGISTERED_TOOLS: Final[tuple[ToolDeclaration, ...]] = (
    WORKSPACE_STATUS_TOOL,
    HARNESS_GET_NOTE_TOOL,
)


def read_only() -> frozenset[str]:
    """Every registered operation of ``SafetyClass.READ``."""
    from rheo_core.operations.registry import REGISTRY  # deferred, see docstring

    names: set[str] = set()
    for name in REGISTRY.names():
        registered = REGISTRY.lookup(name)
        assert registered is not None  # names() and lookup() share one table
        if registered.declaration.safety_class is SafetyClass.READ:
            names.add(name)
    return frozenset(names)


def agent_default() -> frozenset[str]:
    """Every operation named by a registered tool, live-filtered by the registry."""
    from rheo_core.operations.registry import REGISTRY  # deferred, see docstring

    declared = frozenset(tool.operation for tool in REGISTERED_TOOLS)
    return declared & REGISTRY.names()


def cli_full() -> frozenset[str]:
    """Every registered operation except :data:`NON_TOKEN_ISSUABLE`."""
    from rheo_core.operations.registry import REGISTRY  # deferred, see docstring

    return REGISTRY.names() - NON_TOKEN_ISSUABLE


PACKAGE_SETS: Final[dict[str, Callable[[], frozenset[str]]]] = {
    "read_only": read_only,
    "agent_default": agent_default,
    "cli_full": cli_full,
}
"""Name -> evaluator, for ``issue.py``'s named-set resolution (``rheo token issue
--set <name>``). Each callable evaluates against the process-wide ``REGISTRY``."""
