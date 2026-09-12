"""The non-token-issuable policy (B7): a policy constant, not an approval subsystem.

Checked by name, in two places: ``issue.py`` strips it from any set a token could
ever carry (an explicit list naming one is refused; a named package set never
contained one in the first place, by ``sets.py``'s own construction), and
``presentation.py``/``context_from_token`` refuses any presented token whose
snapshot somehow contains one of these six names anyway (a row that cannot arise
from ``issue()`` itself -- only from a row inserted directly, outside it -- checked
regardless, so the rule holds at both ends).

It names two operations that do not exist yet this run (``core.approval.*``,
``core.standing_grant.*``) alongside two that do (``core.token.issue``,
``core.token.revoke``, registered in ``operations/core_ops.py``). That is
deliberate: the whole point of a name-based policy constant is that it holds
*before* the approval operations exist, not only once they do.
"""

from typing import Final

NON_TOKEN_ISSUABLE: Final[frozenset[str]] = frozenset(
    {
        "core.approval.approve",
        "core.approval.refuse",
        "core.standing_grant.create",
        "core.standing_grant.revoke",
        "core.token.issue",
        "core.token.revoke",
    }
)
"""The six operation names no token may ever carry. Literal strings, not imported
constants: ``core.token.issue``/``core.token.revoke`` are also declared in
``operations/core_ops.py`` as ``TOKEN_ISSUE``/``TOKEN_REVOKE``, but importing them
from there would route ``rheo_core.tokens.policy`` -> ``rheo_core.operations.
core_ops`` -> ``rheo_core.tokens.issue`` -> ``rheo_core.tokens.policy``, a real
import cycle. Duplicating two short literal strings is cheaper than that cycle;
``core_ops.py`` carries a comment pointing back here so the two stay in lockstep."""
