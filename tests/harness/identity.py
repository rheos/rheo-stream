"""``FixedIdentityProvider``: the test-only identity provider double.

Completes with a fixed synthetic ``ProviderIdentity`` regardless of the callback
parameters or state it is handed — it never touches a network, a secret, or a real
provider. Registered only under ``profile = test``, origin ``test_harness`` (mirrors
the gate ``tests/harness/registry.py``'s own registrations sit behind): constructing
it under any other profile refuses loudly, so it can never exist where a real
deployment could reach it.
"""

from collections.abc import Mapping
from typing import Final

from rheo_core.identity.boundary import (
    IdentityProvider,
    ProviderIdentity,
    RedirectTarget,
)
from rheo_core.settings import TEST_HARNESS_ORIGIN, current_profile

FIXED_PROVIDER_ID: Final = "test_harness"

DEFAULT_FIXED_IDENTITY: Final = ProviderIdentity(
    provider_id=FIXED_PROVIDER_ID,
    subject="fixed-subject",
    email="fixed@example.test",
    email_verified=True,
    display_name="Fixed Harness Identity",
)


class FixedIdentityProvider:
    """``complete()`` always returns the ``identity`` given at construction (default
    :data:`DEFAULT_FIXED_IDENTITY`), whatever ``callback_params``/``state`` it is
    handed. A protocol-conforming :class:`IdentityProvider`."""

    provider_id: str = FIXED_PROVIDER_ID

    def __init__(self, identity: ProviderIdentity = DEFAULT_FIXED_IDENTITY) -> None:
        profile = current_profile()
        if profile != "test":
            raise RuntimeError(
                f"FixedIdentityProvider (origin {TEST_HARNESS_ORIGIN!r}) is accepted "
                f"only under profile = test (resolved profile is {profile!r})"
            )
        self._identity = identity

    def begin(self, state: str, callback_url: str) -> RedirectTarget:
        return RedirectTarget(url=f"{callback_url}?state={state}")

    def complete(
        self, callback_params: Mapping[str, str], state: str
    ) -> ProviderIdentity:
        return self._identity


# mypy strict checks the class against the protocol here, so a drifted signature
# fails the type gate rather than a runtime call (mirrors ``postgres.py``'s
# ``_PROTOCOL_CHECK`` pattern).
_PROTOCOL_CHECK: type[IdentityProvider] = FixedIdentityProvider
