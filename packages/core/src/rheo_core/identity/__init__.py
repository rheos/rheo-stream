"""The identity-provider boundary (D6, FR 3): ``IdentityProvider``, the GitHub
provider, provider-settings sync, and account resolution/first-run signup.

``rheo_core.identity`` and ``rheo_core.identity.providers`` are imported by no file
under ``modules/**`` (an AST scan in ``tests/postgres/test_identity.py`` asserts it):
domain modules never see a provider or a client secret.
"""

from rheo_core.identity.accounts import resolve_or_create
from rheo_core.identity.boundary import (
    IdentityProvider,
    ProviderIdentity,
    RedirectTarget,
)
from rheo_core.identity.provider_config import sync_providers

__all__ = [
    "IdentityProvider",
    "ProviderIdentity",
    "RedirectTarget",
    "resolve_or_create",
    "sync_providers",
]
