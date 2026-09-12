"""The facade's session resolver (C8): what a presented bearer value resolves
to.

Constructs nothing itself: ``context_from_token`` is the boundary's own
function (the one place a ``WorkspaceContext`` may be built,
``rheo_core.boundary.factories``) -- this module only names the surface the
facade presents tokens against.
"""

from typing import Final

from rheo_contracts import WorkspaceContext
from rheo_core.boundary.context import Refusal
from rheo_core.boundary.factories import context_from_token

MCP_SURFACE: Final = "mcp"


def resolve_context(bearer: str) -> WorkspaceContext | Refusal:
    """The context a presented ``mcp``/``runtime`` bearer value resolves to."""
    return context_from_token(bearer, MCP_SURFACE)
