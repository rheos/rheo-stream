"""Token string format and parsing (C8).

``rheo_<kind>_<43 base64url chars>``: 32 random bytes (256 bits), base64url-encoded
with padding stripped -- always exactly 43 characters for a 32-byte input. Only the
SHA-256 of the raw value is ever stored (``presentation.py``, ``issue.py``); the
rendered string is returned to the issuer once, at ``core.token.issue``, and never
again.

Parsing anything that does not match this exact shape returns ``None`` -- including
a session secret (hex, no ``rheo_`` prefix) presented here by mistake or by an
attacker guessing at credential shape. A plain ``None`` here, not a boundary
``Refusal``: this module sits one layer below the boundary, the same layering
``rheo_core.storage.control_plane``'s lookup functions use (``get_session_by_secret_
hash`` returns ``None`` on a miss; the boundary is what names the refusal state).
``presentation.py`` is the caller that turns a miss into ``TOKEN_MALFORMED``.
"""

import base64
import re
import secrets
from dataclasses import dataclass
from typing import Final

_RAW_BYTES: Final = 32
_PREFIX: Final = "rheo"
_TOKEN_RE: Final = re.compile(r"rheo_(?P<kind>[a-z]+)_(?P<value>[A-Za-z0-9_-]{43})\Z")


@dataclass(frozen=True, slots=True)
class ParsedToken:
    """A well-formed presented token: its declared ``kind`` label (not itself
    authoritative -- the row's own ``kind`` column, read by hash, is what
    ``presentation.py`` actually checks) and its raw 32-byte value."""

    kind: str
    raw: bytes


def mint(kind: str) -> tuple[str, bytes]:
    """A fresh raw value and its rendered ``rheo_<kind>_...`` presentation string.

    Returns ``(rendered, raw)`` so the caller (``issue.py``) can hash ``raw`` for
    storage while handing ``rendered`` to the issuer once.
    """
    raw = secrets.token_bytes(_RAW_BYTES)
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    return f"{_PREFIX}_{kind}_{encoded}", raw


def parse(token: str) -> ParsedToken | None:
    """``ParsedToken`` for a well-formed ``rheo_<kind>_<43 chars>`` string, else
    ``None``. Every 43-character base64url string decodes to exactly 32 bytes once
    one ``=`` pad character is restored (43 + 1 = 44, a multiple of 4), so the
    length check below is defence in depth against a future change to the regex,
    not a case this function's own construction can otherwise reach.
    """
    if not isinstance(token, str):
        return None
    match = _TOKEN_RE.fullmatch(token)
    if match is None:
        return None
    value = match["value"]
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except ValueError:
        return None
    if len(raw) != _RAW_BYTES:
        return None
    return ParsedToken(kind=match["kind"], raw=raw)
