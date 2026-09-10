"""The two release-one backends: one file per id under ``<data_root>/secrets/``, and
the environment. Both return raw bytes; the store wraps them in ``SecretValue``.

A managed secret manager would be a third backend a deployment adds later; nothing in
release one needs one.
"""

import os
import stat
from collections.abc import Mapping
from pathlib import Path

from rheo_core.secrets.refs import SECRET_MISSING, SECRET_PERMISSIONS, SecretRefusal

SECRETS_DIR_MODE = 0o700
# Any bit outside owner read/write: group, other, or owner-execute.
_BEYOND_OWNER_RW = 0o177


class FileBackend:
    """``<root>/<id>``, read verbatim (write files with ``printf '%s'``, not ``echo``).

    :meth:`ensure` creates the root with mode 0700. A file whose mode is looser than
    0600 is ``secret_permissions``; a missing one is ``secret_missing`` naming the path.
    Ids are validated slug paths (no ``..``, no absolute segment), so ``root / id``
    cannot leave the root.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def ensure(self) -> Path:
        self.root.mkdir(mode=SECRETS_DIR_MODE, parents=True, exist_ok=True)
        self.root.chmod(SECRETS_DIR_MODE)
        return self.root

    def read(self, ref_id: str) -> bytes:
        path = self.root / ref_id
        try:
            info = path.stat()
        except FileNotFoundError:
            raise SecretRefusal(
                SECRET_MISSING, f"secret file {path} does not exist"
            ) from None
        if not stat.S_ISREG(info.st_mode):
            raise SecretRefusal(
                SECRET_MISSING, f"secret file {path} is not a regular file"
            )
        mode = stat.S_IMODE(info.st_mode)
        if mode & _BEYOND_OWNER_RW:
            raise SecretRefusal(
                SECRET_PERMISSIONS,
                f"secret file {path} has mode {mode:04o}; it must be 0600 or stricter",
            )
        return path.read_bytes()


class EnvBackend:
    """The named environment variable, UTF-8 encoded; missing is ``secret_missing``."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ: Mapping[str, str] = os.environ if environ is None else environ

    def has(self, name: str) -> bool:
        return name in self._environ

    def read(self, name: str) -> bytes:
        value = self._environ.get(name)
        if value is None:
            raise SecretRefusal(
                SECRET_MISSING, f"environment variable {name} is not set"
            )
        return value.encode("utf-8")
