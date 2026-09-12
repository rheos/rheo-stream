"""Startup sync of ``identity.providers.*`` settings into ``control.identity_provider``.

Called from the FastAPI lifespan's startup (``apps/core/.../startup.py``, 08's map),
never from here — this module only ships the function. Runs once per process start,
after ``check_env_references`` has already passed.
"""

from rheo_core.identity.providers.github import GITHUB_PROVIDER_ID
from rheo_core.settings import ResolvedSettings
from rheo_core.storage.control_plane import upsert_identity_provider
from rheo_core.storage.postgres import PostgresBackend

_GITHUB_ENABLED_KEY = "identity.providers.github.enabled"
_GITHUB_CLIENT_ID_KEY = "identity.providers.github.client_id"
_GITHUB_CLIENT_SECRET_REF_KEY = "identity.providers.github.client_secret_ref"


def sync_providers(backend: PostgresBackend, settings: ResolvedSettings) -> None:
    """Upsert every configured provider row from the resolved deployment settings.

    Skips the upsert entirely when the provider is disabled or names no client id
    (fit-check.md D5): an unconfigured provider legitimately syncs nothing, and a
    partial row (enabled with an empty client id) is not written either.
    """
    enabled = settings.get_bool(_GITHUB_ENABLED_KEY)
    client_id = settings.get_str(_GITHUB_CLIENT_ID_KEY)
    if not enabled or not client_id:
        return
    client_secret_ref = settings.get_str(_GITHUB_CLIENT_SECRET_REF_KEY)
    with backend.control_engine.begin() as connection:
        upsert_identity_provider(
            connection,
            provider_id=GITHUB_PROVIDER_ID,
            enabled=enabled,
            client_id=client_id,
            client_secret_ref=client_secret_ref,
        )
