"""The one function that builds every session-related cookie (C7a).

The contract 08's ``/auth/*`` routes build against (``00-index.md`` § Coupling seams,
07 -> 08): 08's routes call :func:`build_cookie`, they do not construct a
``Set-Cookie`` header by hand. Three cookies, one function, so the attributes below
can never drift between them:

- ``rheo_session`` — no ``Max-Age``: the browser may hold it as long as it likes, and
  validity is entirely a server-side question (the session row's own expiry and
  revocation), never the cookie's own lifetime.
- ``rheo_oauth_state`` — ten-minute expiry (the OAuth ``begin``/``callback`` window).
- ``rheo_continue`` — five-minute expiry (the subdomain-mode continue-host grant).

Every cookie gets ``HttpOnly``, ``SameSite=Lax``, ``Path=/``, and **no ``Domain``
attribute — the signature below has no parameter for one, on purpose. If 08 finds it
needs a fourth cookie or a ``Domain`` parameter, it stops and reports rather than
adding one here (this file is 07's map, not 08's; see ``00-index.md``).
"""

from typing import Final

from rheo_core.settings import current_profile

SESSION_COOKIE: Final = "rheo_session"
OAUTH_STATE_COOKIE: Final = "rheo_oauth_state"
CONTINUE_COOKIE: Final = "rheo_continue"

_OAUTH_STATE_MAX_AGE_SECONDS: Final = 10 * 60
_CONTINUE_MAX_AGE_SECONDS: Final = 5 * 60

_MAX_AGE_BY_NAME: Final[dict[str, int | None]] = {
    SESSION_COOKIE: None,
    OAUTH_STATE_COOKIE: _OAUTH_STATE_MAX_AGE_SECONDS,
    CONTINUE_COOKIE: _CONTINUE_MAX_AGE_SECONDS,
}


def build_cookie(name: str, value: str, *, scheme: str) -> str:
    """The ``Set-Cookie`` value for one of the three cookie names above.

    Raises ``ValueError`` for any other name. Always ``HttpOnly``, ``SameSite=Lax``,
    ``Path=/``. ``Secure`` is present unless ``scheme`` is ``"http"`` **and** the
    resolved profile is not ``"production"`` — a production deployment that somehow
    resolved ``scheme = http`` still gets ``Secure`` here; the companion startup-time
    refusal for that misconfiguration belongs to 08, not this function.
    """
    if name not in _MAX_AGE_BY_NAME:
        raise ValueError(f"unknown cookie name {name!r}")
    parts = [f"{name}={value}", "HttpOnly", "SameSite=Lax", "Path=/"]
    max_age = _MAX_AGE_BY_NAME[name]
    if max_age is not None:
        parts.append(f"Max-Age={max_age}")
    if scheme != "http" or current_profile() == "production":
        parts.append("Secure")
    return "; ".join(parts)
