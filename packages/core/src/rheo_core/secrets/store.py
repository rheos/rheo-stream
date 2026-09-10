"""``SecretStore``: ``resolve(ref, scope) -> SecretValue``, ``scope_for``, and the
startup check of every ``secret://env/*`` reference the deployment settings name.

Scope constants belong to their components, not here: the storage component (C3)
calls ``scope_for("storage", "secret://file/cluster/", "secret://env/RHEO_CLUSTER_DSN")``
where it is constructed. This module ships ``scope_for`` and nothing else.
"""

import os
from collections.abc import Mapping
from pathlib import Path

from rheo_core.secrets.backends import EnvBackend, FileBackend
from rheo_core.secrets.refs import (
    SECRET_MISSING,
    SECRET_SCOPE_DENIED,
    SecretBackend,
    SecretRef,
    SecretRefusal,
    is_secret_reference,
)
from rheo_core.secrets.scope import SecretScope, _new_scope
from rheo_core.secrets.value import SecretValue

SECRETS_SUBDIR = "secrets"


class SecretStore:
    """One store per process, rooted at ``<data_root>/secrets`` for the file backend."""

    def __init__(
        self, data_root: Path, *, environ: Mapping[str, str] | None = None
    ) -> None:
        self._files = FileBackend(Path(data_root) / SECRETS_SUBDIR)
        self._env = EnvBackend(environ)

    @staticmethod
    def scope_for(component: str, *prefixes: str) -> SecretScope:
        """The one public constructor of a ``SecretScope``."""
        return _new_scope(component, prefixes)

    def resolve(self, ref: SecretRef, scope: SecretScope) -> SecretValue:
        """The value behind ``ref``, if ``scope`` permits it.

        A missing scope, or anything that is not a ``SecretScope``, is a ``TypeError``:
        a component constructed without a scope has no way to call this at all. A
        reference outside the scope is ``secret_scope_denied``; a missing file or
        variable is ``secret_missing`` naming the path or the variable, never a value.
        """
        if not isinstance(ref, SecretRef):
            raise TypeError("resolve() takes a SecretRef")
        if not isinstance(scope, SecretScope):
            raise TypeError(
                "resolve() requires a SecretScope from SecretStore.scope_for"
            )
        if not scope.permits(ref):
            raise SecretRefusal(
                SECRET_SCOPE_DENIED,
                f"scope {scope.component!r} may not resolve {ref}",
            )
        if ref.backend is SecretBackend.FILE:
            raw = self._files.read(ref.id)
        else:
            raw = self._env.read(ref.id)
        return SecretValue(raw)


def env_references(settings: Mapping[str, object]) -> dict[str, SecretRef]:
    """Every ``secret://env/*`` reference among the values of ``settings``, by key.

    A value carrying the ``secret://`` scheme that does not parse is
    ``secret_ref_malformed`` naming the key.
    """
    found: dict[str, SecretRef] = {}
    for key, value in settings.items():
        if not is_secret_reference(value):
            continue
        try:
            ref = SecretRef.parse(value)
        except SecretRefusal as refusal:
            raise SecretRefusal(
                refusal.state, f"setting {key}: {refusal.detail}"
            ) from None
        if ref.backend is SecretBackend.ENV:
            found[key] = ref
    return found


def check_env_references(
    settings: Mapping[str, object], *, environ: Mapping[str, str] | None = None
) -> tuple[str, ...]:
    """The startup env check: refuse to start when a named variable is missing.

    Returns the variable names it verified, sorted. Raises ``secret_missing`` naming
    the first missing variable and the setting that names it.
    """
    env = os.environ if environ is None else environ
    checked: list[str] = []
    for key, ref in sorted(env_references(settings).items()):
        if ref.id not in env:
            raise SecretRefusal(
                SECRET_MISSING,
                f"environment variable {ref.id}, named by setting {key}, is not set",
            )
        checked.append(ref.id)
    return tuple(sorted(set(checked)))
