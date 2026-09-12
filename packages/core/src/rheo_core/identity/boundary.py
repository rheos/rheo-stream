"""The ``IdentityProvider`` protocol (D6, FR 3): the whole identity-provider boundary.

```text
IdentityProvider
  provider_id: str
  begin(state: str, callback_url: str) -> RedirectTarget
  complete(callback_params, state: str) -> ProviderIdentity
     ProviderIdentity: provider_id, subject, email | None,
                       email_verified: bool, display_name
```

``begin`` builds the provider's authorize URL for the caller to redirect the browser
to; ``complete`` exchanges the callback into a ``ProviderIdentity``. Neither method
touches the control plane or a cookie: that is ``accounts.py`` and ``sessions/``'s job,
one layer up. ``state`` is handed to both ends of the protocol so a provider that needs
it for its own exchange has it, though GitHub's does not; comparing the returned state
against the cookie set at ``begin`` is the caller's job (08's ``/auth/callback``), not
this protocol's.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ProviderIdentity:
    """What a provider hands back once a sign-in completes. Never a secret."""

    provider_id: str
    subject: str
    email: str | None
    email_verified: bool
    display_name: str


@dataclass(frozen=True, slots=True)
class RedirectTarget:
    """Where ``begin`` wants the browser sent next."""

    url: str


@runtime_checkable
class IdentityProvider(Protocol):
    """The whole identity-provider boundary. ``rheo_core.identity.providers.<id>``
    is where an implementation lives; the GitHub provider is the only shipped one."""

    provider_id: str

    def begin(self, state: str, callback_url: str) -> RedirectTarget:
        """The redirect target that starts a sign-in, embedding ``state`` and a
        callback pointed at ``callback_url``."""
        ...

    def complete(
        self, callback_params: Mapping[str, str], state: str
    ) -> ProviderIdentity:
        """Exchange the callback's query parameters into a ``ProviderIdentity``."""
        ...
