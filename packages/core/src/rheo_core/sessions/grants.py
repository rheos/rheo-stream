"""Session grants: the subdomain-mode continue-host code (C7a).

A grant moves an existing session's authentication onto a second host without ever
handing that host the first host's cookie value: the identity host writes a
``control.session_grant`` row and redirects with a code in the URL; the target host
looks the code up, checks it, mints its **own** host secret, and sets its own cookie.
Path mode never calls :func:`write_grant`: same code (``/auth/continue`` on a single
host finds the existing cookie directly), no grant row, no nonce.
"""

import hashlib
import secrets as _secrets
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID

from rheo_core.boundary.context import INVALID_GRANT, Refusal
from rheo_core.storage.control_plane import (
    SessionGrantRow,
    consume_session_grant,
    insert_session_grant,
)
from rheo_core.storage.postgres import get_backend

_GRANT_CODE_BYTES: Final = 32  # 256 random bits
_GRANT_EXPIRY_SECONDS: Final = 60


def _hash(value: bytes) -> bytes:
    return hashlib.sha256(value).digest()


def write_grant(session_id: UUID, target_host: str, nonce: bytes) -> str:
    """A fresh, single-use, 60-second grant code for ``session_id`` -> ``target_host``,
    bound to ``nonce`` (the ``rheo_continue`` cookie's value, hashed here — the raw
    nonce never enters the control plane). Returns the raw code, shown once, embedded
    in the redirect URL; only its SHA-256 is stored."""
    code = _secrets.token_urlsafe(_GRANT_CODE_BYTES)
    backend = get_backend()
    now = datetime.now(UTC)
    with backend.control_engine.begin() as connection:
        insert_session_grant(
            connection,
            code_hash=_hash(code.encode("ascii")),
            session_id=session_id,
            target_host=target_host,
            nonce_hash=_hash(nonce),
            expires_at=now + timedelta(seconds=_GRANT_EXPIRY_SECONDS),
        )
    return code


def consume_grant(code: str, host: str, nonce: bytes) -> SessionGrantRow | Refusal:
    """Validate and consume a grant code in one call. Any failure — unknown, already
    used, expired, the wrong host, or a nonce mismatch — is the same ``invalid_grant``
    refusal (the login-CSRF defence depends on these being indistinguishable from the
    outside): a caller cannot tell an attack from a stale link."""
    backend = get_backend()
    with backend.control_engine.begin() as connection:
        row = consume_session_grant(
            connection,
            code_hash=_hash(code.encode("ascii")),
            target_host=host,
            nonce_hash=_hash(nonce),
        )
    return Refusal(INVALID_GRANT) if row is None else row
