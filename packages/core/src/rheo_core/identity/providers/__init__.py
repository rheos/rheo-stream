"""Identity provider implementations, one module per ``provider_id``.

GitHub is the only shipped provider in release one. Re-exported here so a caller
writes ``from rheo_core.identity.providers import GitHubProvider`` rather than
reaching into the submodule.
"""

from rheo_core.identity.providers.github import GITHUB_PROVIDER_ID, GitHubProvider

__all__ = ["GITHUB_PROVIDER_ID", "GitHubProvider"]
