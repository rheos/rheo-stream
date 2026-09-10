"""The boundary refusal and the refusal states this run raises at the boundary.

A factory returns either a ``WorkspaceContext`` or a :class:`Refusal` whose ``state``
is one of the string constants below. They are plain string constants, not an enum:
0b2 adds ``session_missing``, ``session_expired``, ``session_revoked``,
``workspace_unselected`` and the token states beside them, and an open enum that
later runs must extend is the wrong shape for a set that grows by boundary.

``Refusal`` is also what the operation registry returns from ``authorize`` and what
the dispatcher folds into an ``OperationOutcome``: one refusal type at every seam,
so a caller never has to know which layer said no.
"""

from dataclasses import dataclass
from typing import Final

CONTEXT_REQUIRED: Final = "context_required"
"""No ``WorkspaceContext`` was supplied: ``None``, or an object that is not one."""

WORKSPACE_UNAVAILABLE: Final = "workspace_unavailable"
"""The ``control.workspace`` row is not ``active``; ``detail`` carries its state."""

MEMBERSHIP_MISSING: Final = "membership_missing"
"""No ``control.membership`` row for the account, or not with the role asked for."""

PROFILE_REQUIRED: Final = "profile_required"
"""A test-profile-only factory was called under another profile."""

WORKSPACE_MISSING_DETAIL: Final = "missing"
"""The ``workspace_unavailable`` detail when there is no registry row at all."""


@dataclass(frozen=True, slots=True)
class Refusal:
    """A named refusal. ``detail`` is safe to show and never carries a secret."""

    state: str
    detail: str | None = None

    def __str__(self) -> str:
        return self.state if self.detail is None else f"{self.state}: {self.detail}"
