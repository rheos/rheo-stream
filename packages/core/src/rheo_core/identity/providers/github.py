"""The GitHub identity provider: the only shipped ``IdentityProvider`` in release one.

``begin`` builds the GitHub authorize URL from the configured client id, the callback
url, a fixed scope, and the caller's ``state``. ``complete`` exchanges the callback's
``code`` for an access token — resolving the client secret **at that moment**, through
this provider's own :class:`~rheo_core.secrets.scope.SecretScope`, never stored on the
instance as a value — then reads ``/user`` and ``/user/emails`` for the profile.

The httpx client is a constructor parameter: tests substitute ``httpx.MockTransport``
with synthetic bodies, so no real network call is ever made in the suite.
"""

from collections.abc import Mapping
from typing import Final
from urllib.parse import urlencode

import httpx

from rheo_core.identity.boundary import (
    IdentityProvider,
    ProviderIdentity,
    RedirectTarget,
)
from rheo_core.secrets import SecretRef, SecretStore

GITHUB_PROVIDER_ID: Final = "github"

_AUTHORIZE_URL: Final = "https://github.com/login/oauth/authorize"
_TOKEN_URL: Final = "https://github.com/login/oauth/access_token"
_USER_URL: Final = "https://api.github.com/user"
_EMAILS_URL: Final = "https://api.github.com/user/emails"
_SCOPE: Final = "read:user user:email"

# Mirrors ``storage/postgres.py``'s ``STORAGE_SCOPE_COMPONENT`` /
# ``STORAGE_SCOPE_PREFIXES`` pattern: one component name, the prefixes it may resolve.
GITHUB_SCOPE_COMPONENT: Final = "identity.github"
GITHUB_SCOPE_PREFIXES: Final = (
    "secret://file/identity/github/",
    "secret://env/RHEO_GITHUB_CLIENT_SECRET",
)


class GitHubProvider:
    """``provider_id = "github"``. Constructed once per process from deployment
    settings; the httpx client is injected so tests never touch the network."""

    # Not ``Final``: a Protocol's plain attribute must remain assignable to satisfy
    # structural matching for ``type[GitHubProvider]`` against
    # ``type[IdentityProvider]`` (mirrors ``storage/postgres.py``'s own
    # ``supports_vector: bool = True`` pattern).
    provider_id: str = GITHUB_PROVIDER_ID

    def __init__(
        self,
        *,
        client_id: str,
        client_secret_ref: str,
        secret_store: SecretStore,
        client: httpx.Client,
    ) -> None:
        self._client_id = client_id
        self._client_secret_ref = SecretRef.parse(client_secret_ref)
        self._secret_store = secret_store
        self._scope = SecretStore.scope_for(
            GITHUB_SCOPE_COMPONENT, *GITHUB_SCOPE_PREFIXES
        )
        self._client = client

    def begin(self, state: str, callback_url: str) -> RedirectTarget:
        params = {
            "client_id": self._client_id,
            "redirect_uri": callback_url,
            "scope": _SCOPE,
            "state": state,
        }
        return RedirectTarget(url=f"{_AUTHORIZE_URL}?{urlencode(params)}")

    def complete(
        self, callback_params: Mapping[str, str], state: str
    ) -> ProviderIdentity:
        code = callback_params.get("code")
        if not code:
            raise ValueError("github callback carries no code")
        secret = self._secret_store.resolve(self._client_secret_ref, self._scope)
        try:
            token_response = self._client.post(
                _TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": secret.expose().decode("utf-8"),
                    "code": code,
                },
                headers={"Accept": "application/json"},
            )
            token_response.raise_for_status()
            access_token = token_response.json()["access_token"]
        finally:
            # Drops this local binding as soon as it's no longer needed, narrowing
            # the window it's reachable in this frame. Not a security guarantee:
            # ``del`` only removes the name here, it neither zeroes
            # ``SecretValue``'s underlying bytes nor makes them unreachable while
            # any other reference (or the interpreter's own internals) still holds
            # them.
            del secret
        auth_headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        }
        user_response = self._client.get(_USER_URL, headers=auth_headers)
        user_response.raise_for_status()
        user = user_response.json()
        emails_response = self._client.get(_EMAILS_URL, headers=auth_headers)
        emails_response.raise_for_status()
        primary = next(
            (
                row
                for row in emails_response.json()
                if row.get("primary") and row.get("verified")
            ),
            None,
        )
        return ProviderIdentity(
            provider_id=self.provider_id,
            subject=str(user["id"]),
            email=None if primary is None else primary["email"],
            email_verified=primary is not None,
            display_name=user.get("name") or user.get("login") or str(user["id"]),
        )


# mypy strict checks the class against the protocol here, so a drifted signature
# fails the type gate rather than a runtime call.
_PROTOCOL_CHECK: type[IdentityProvider] = GitHubProvider
