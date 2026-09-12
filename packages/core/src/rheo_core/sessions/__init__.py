"""Web sessions and the active-workspace binding (C7a).

``rheo_core.sessions.service`` issues and manages sessions (creation, per-host
secrets, touch, revoke, workspace switch). ``rheo_core.sessions.grants`` handles the
subdomain-mode continue-host code. ``rheo_core.sessions.cookies`` is the one function
that builds every session-related cookie — the contract 08's ``/auth/*`` routes build
against (``00-index.md`` § Coupling seams, 07 -> 08).
"""

from rheo_core.sessions.cookies import (
    CONTINUE_COOKIE,
    OAUTH_STATE_COOKIE,
    SESSION_COOKIE,
    build_cookie,
)
from rheo_core.sessions.grants import consume_grant, write_grant
from rheo_core.sessions.service import (
    create_session,
    mint_host_secret,
    revoke,
    switch_workspace,
    touch,
)

__all__ = [
    "CONTINUE_COOKIE",
    "OAUTH_STATE_COOKIE",
    "SESSION_COOKIE",
    "build_cookie",
    "consume_grant",
    "create_session",
    "mint_host_secret",
    "revoke",
    "switch_workspace",
    "touch",
    "write_grant",
]
