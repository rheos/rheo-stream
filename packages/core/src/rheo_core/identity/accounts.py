"""Resolving a ``ProviderIdentity`` to an account, and first-run signup (D6, FR 3)."""

from typing import Final
from uuid import UUID

from sqlalchemy import func, select

from rheo_core.boundary.context import SIGNUP_CLOSED, Refusal
from rheo_core.identity.boundary import ProviderIdentity
from rheo_core.settings import resolve
from rheo_core.storage import control_tables as t
from rheo_core.storage.control_plane import (
    AccountRow,
    get_account,
    get_identity,
    insert_account,
    insert_identity,
)
from rheo_core.storage.postgres import PostgresBackend, advisory_lock, get_backend

# Distinct from the migration lock's ADVISORY_LOCK_KEY (0x5248454F4D494752, "RHEOMIGR"):
# "RHEOACCT" in ASCII, so the two locks can never collide over the same key.
_FIRST_ACCOUNT_LOCK_KEY: Final = 0x5248454F41434354


def _account_or_raise(backend: PostgresBackend, account_id: UUID) -> AccountRow:
    with backend.control_engine.connect() as connection:
        account = get_account(connection, account_id)
    if account is None:  # pragma: no cover - the identity's FK guarantees this
        raise RuntimeError(f"identity names account {account_id}, which has no row")
    return account


def resolve_or_create(identity: ProviderIdentity) -> AccountRow | Refusal:
    """The account behind ``identity``: an existing one, or a new one on first login.

    Signup is *computed*, not configured (fit-check.md D6): allowed when the control
    plane holds no account at all, or when ``identity.allow_signup`` resolves ``true``.
    Otherwise refused ``signup_closed``. The first-account check runs inside a
    control-plane advisory lock distinct from the migration lock's, so two concurrent
    first logins cannot both create an account; the same lock covers a re-check of the
    identity itself, so two concurrent logins of the very same new identity resolve to
    one account rather than racing the ``(provider_id, provider_subject)`` unique
    constraint.
    """
    backend = get_backend()
    with backend.control_engine.connect() as connection:
        existing = get_identity(
            connection,
            provider_id=identity.provider_id,
            provider_subject=identity.subject,
        )
    if existing is not None:
        return _account_or_raise(backend, existing.account_id)
    with backend.control_engine.begin() as connection:
        advisory_lock(connection, _FIRST_ACCOUNT_LOCK_KEY)
        # Re-check under the lock: another process may have created this exact
        # identity while this one waited to acquire it.
        existing = get_identity(
            connection,
            provider_id=identity.provider_id,
            provider_subject=identity.subject,
        )
        if existing is not None:
            account = get_account(connection, existing.account_id)
            if account is None:  # pragma: no cover - the identity's FK guarantees this
                raise RuntimeError(
                    f"identity names account {existing.account_id}, which has no row"
                )
            return account
        any_account = connection.execute(
            select(func.count()).select_from(t.account)
        ).scalar_one()
        signup_open = any_account == 0 or resolve().get_bool("identity.allow_signup")
        if not signup_open:
            return Refusal(SIGNUP_CLOSED)
        account = insert_account(connection, display_name=identity.display_name)
        insert_identity(
            connection,
            account_id=account.id,
            provider_id=identity.provider_id,
            provider_subject=identity.subject,
            email=identity.email,
            email_verified=identity.email_verified,
        )
        return account
