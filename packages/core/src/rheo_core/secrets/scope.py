"""``SecretScope``: the unforgeable token that says what a component may resolve.

The only constructor is ``SecretStore.scope_for(component, *prefixes)``, which calls
the module-private :func:`_new_scope` here; the class's ``__init__`` demands a sentinel
that never leaves this module, so ``SecretScope(...)`` from anywhere else raises, and
so does ``dataclasses.replace``. An AST test asserts the call ``SecretScope(`` appears
in no file outside ``rheo_core/secrets/``.

A scope names the **full reference prefixes** it may resolve, which accommodates both
backends' id shapes (``secret://file/cluster/`` and ``secret://env/RHEO_CLUSTER_DSN``).
Matching is segment-aligned: a prefix ending in ``/`` covers everything beneath it, and
a prefix without one covers exactly that reference or a path beneath it, so
``secret://env/RHEO_CLUSTER_DSN`` does not also cover ``RHEO_CLUSTER_DSN_ADMIN``.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from rheo_core.secrets.refs import SCHEME, SecretBackend, SecretRef

_SENTINEL: Final = object()
_PREFIX_ROOTS: Final = tuple(f"{SCHEME}{backend.value}/" for backend in SecretBackend)


@dataclass(frozen=True, slots=True, init=False)
class SecretScope:
    component: str
    prefixes: tuple[str, ...]

    def __init__(
        self, component: str, prefixes: tuple[str, ...], *, _token: object = None
    ) -> None:
        if _token is not _SENTINEL:
            raise TypeError(
                "SecretScope is constructed only by SecretStore.scope_for()"
            )
        object.__setattr__(self, "component", component)
        object.__setattr__(self, "prefixes", prefixes)

    def permits(self, ref: SecretRef) -> bool:
        text = str(ref)
        for prefix in self.prefixes:
            if text == prefix:
                return True
            covered = prefix if prefix.endswith("/") else prefix + "/"
            if text.startswith(covered):
                return True
        return False


def _new_scope(component: str, prefixes: Iterable[str]) -> SecretScope:
    """Build a scope. Package-private: ``SecretStore.scope_for`` is the public door."""
    if not isinstance(component, str) or not component:
        raise ValueError("a secret scope needs a non-empty component name")
    names = tuple(prefixes)
    if not names:
        raise ValueError(f"scope for {component!r} names no reference prefix")
    for prefix in names:
        if not isinstance(prefix, str) or not prefix.startswith(_PREFIX_ROOTS):
            raise ValueError(
                f"scope for {component!r}: a prefix must start with one of "
                f"{list(_PREFIX_ROOTS)}"
            )
    return SecretScope(component, names, _token=_SENTINEL)
