"""Control-plane repositories: typed functions over the control tables, the only place
control-plane SQL lives.

This run ships the ``account``, ``identity``, ``workspace`` and ``membership``
repositories only. The ``session``, ``session_secret``, ``session_grant``,
``access_token``, ``access_token_operation`` and ``identity_provider`` repositories
arrive in 0b2 (C7/C8) **in this same file**, with their callers and their tests; their
DDL is already whole in the control revision ``0001_control_plane``. There is no
placeholder for any of them here: a function with no caller and no test is what
burdens a reviewer, and the ratified revision is what the "never edited afterward"
rule protects.

Every function takes the caller's ``Connection`` and runs inside the caller's
transaction; none commits. Ids are minted here with ``uuid7()`` in the creating
transaction (A2). Timestamps are ``timestamptz`` and are written from the process
clock in UTC.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import psycopg.errors
from rheo_contracts import Role
from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError

from rheo_core.refs import uuid7
from rheo_core.storage import control_tables as t
from rheo_core.storage.backend import (
    ACCOUNT_MISSING,
    IDENTITY_EXISTS,
    SLUG_TAKEN,
    WORKSPACE_MISSING,
    StorageRefusal,
)
from rheo_core.storage.control_tables import WorkspaceState


def _now() -> datetime:
    return datetime.now(UTC)


def _constraint_name(exc: IntegrityError) -> str:
    orig = exc.orig
    if isinstance(orig, psycopg.Error):
        return orig.diag.constraint_name or ""
    return ""


# --- account --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AccountRow:
    id: UUID
    display_name: str
    created_at: datetime
    disabled_at: datetime | None


def _account(row: RowMapping) -> AccountRow:
    return AccountRow(
        id=row["id"],
        display_name=row["display_name"],
        created_at=row["created_at"],
        disabled_at=row["disabled_at"],
    )


def insert_account(conn: Connection, *, display_name: str) -> AccountRow:
    """Insert one person. The id is minted here."""
    if not isinstance(display_name, str) or not display_name.strip():
        raise ValueError("an account needs a non-empty display name")
    row = AccountRow(uuid7(), display_name, _now(), None)
    conn.execute(
        insert(t.account).values(
            id=row.id,
            display_name=row.display_name,
            created_at=row.created_at,
            disabled_at=None,
        )
    )
    return row


def get_account(conn: Connection, account_id: UUID) -> AccountRow | None:
    found = (
        conn.execute(select(t.account).where(t.account.c.id == account_id))
        .mappings()
        .first()
    )
    return None if found is None else _account(found)


# --- identity -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IdentityRow:
    id: UUID
    account_id: UUID
    provider_id: str
    provider_subject: str
    email: str | None
    email_verified: bool
    created_at: datetime


def _identity(row: RowMapping) -> IdentityRow:
    return IdentityRow(
        id=row["id"],
        account_id=row["account_id"],
        provider_id=row["provider_id"],
        provider_subject=row["provider_subject"],
        email=row["email"],
        email_verified=row["email_verified"],
        created_at=row["created_at"],
    )


def insert_identity(
    conn: Connection,
    *,
    account_id: UUID,
    provider_id: str,
    provider_subject: str,
    email: str | None = None,
    email_verified: bool = False,
) -> IdentityRow:
    """One login identity for an existing account.

    ``account_missing`` when no such account; ``identity_exists`` when
    ``(provider_id, provider_subject)`` is already bound.
    """
    if not provider_id or not provider_subject:
        raise ValueError("an identity needs a provider id and a provider subject")
    row = IdentityRow(
        uuid7(),
        account_id,
        provider_id,
        provider_subject,
        email,
        email_verified,
        _now(),
    )
    try:
        conn.execute(
            insert(t.identity).values(
                id=row.id,
                account_id=row.account_id,
                provider_id=row.provider_id,
                provider_subject=row.provider_subject,
                email=row.email,
                email_verified=row.email_verified,
                created_at=row.created_at,
            )
        )
    except IntegrityError as exc:
        if isinstance(exc.orig, psycopg.errors.ForeignKeyViolation):
            raise StorageRefusal(
                ACCOUNT_MISSING, f"account {account_id} does not exist"
            ) from None
        if isinstance(exc.orig, psycopg.errors.UniqueViolation):
            raise StorageRefusal(
                IDENTITY_EXISTS,
                f"identity {provider_id}/{provider_subject} is already bound",
            ) from None
        raise
    return row


def get_identity(
    conn: Connection, *, provider_id: str, provider_subject: str
) -> IdentityRow | None:
    found = (
        conn.execute(
            select(t.identity).where(
                t.identity.c.provider_id == provider_id,
                t.identity.c.provider_subject == provider_subject,
            )
        )
        .mappings()
        .first()
    )
    return None if found is None else _identity(found)


# --- workspace ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WorkspaceRow:
    id: UUID
    slug: str
    display_name: str
    database_name: str
    state: WorkspaceState
    created_at: datetime
    state_changed_at: datetime
    state_detail: str | None


def _workspace(row: RowMapping) -> WorkspaceRow:
    return WorkspaceRow(
        id=row["id"],
        slug=row["slug"],
        display_name=row["display_name"],
        database_name=row["database_name"],
        state=WorkspaceState(row["state"]),
        created_at=row["created_at"],
        state_changed_at=row["state_changed_at"],
        state_detail=row["state_detail"],
    )


def insert_workspace_if_absent(
    conn: Connection,
    *,
    workspace_id: UUID,
    slug: str,
    display_name: str,
    database_name: str,
    state_detail: str,
) -> tuple[WorkspaceRow, bool]:
    """Insert the registry row in state ``provisioning``, or leave an existing row as
    it is (a retry of a crashed create). Returns the row now present and whether this
    call inserted it, so the caller can tell a fresh create from a retry.

    ``slug_taken`` when another workspace holds the slug. ``database_name`` is
    computed by provisioning and never accepted from any input; this function is the
    only writer of that column.
    """
    now = _now()
    statement = (
        pg_insert(t.workspace)
        .values(
            id=workspace_id,
            slug=slug,
            display_name=display_name,
            database_name=database_name,
            state=WorkspaceState.PROVISIONING.value,
            created_at=now,
            state_changed_at=now,
            state_detail=state_detail,
        )
        .on_conflict_do_nothing(index_elements=[t.workspace.c.id])
        .returning(t.workspace.c.id)
    )
    try:
        # RETURNING yields a row only when the insert happened; ``rowcount`` is not
        # a reliable signal for an ``ON CONFLICT DO NOTHING`` insert.
        inserted = conn.execute(statement).first() is not None
    except IntegrityError as exc:
        if isinstance(exc.orig, psycopg.errors.UniqueViolation) and (
            "slug" in _constraint_name(exc)
        ):
            raise StorageRefusal(
                SLUG_TAKEN, f"slug {slug!r} belongs to another workspace"
            ) from None
        raise
    row = get_workspace(conn, workspace_id)
    if row is None:  # pragma: no cover - the insert or the existing row is visible
        raise StorageRefusal(WORKSPACE_MISSING, f"workspace {workspace_id} vanished")
    return row, inserted


def get_workspace(conn: Connection, workspace_id: UUID) -> WorkspaceRow | None:
    found = (
        conn.execute(select(t.workspace).where(t.workspace.c.id == workspace_id))
        .mappings()
        .first()
    )
    return None if found is None else _workspace(found)


def list_workspaces(
    conn: Connection, *, state: WorkspaceState | None = None
) -> tuple[WorkspaceRow, ...]:
    """Every registry row, oldest first, optionally only those in ``state``."""
    statement = select(t.workspace).order_by(t.workspace.c.created_at, t.workspace.c.id)
    if state is not None:
        statement = statement.where(t.workspace.c.state == state.value)
    return tuple(_workspace(row) for row in conn.execute(statement).mappings())


def set_workspace_state(
    conn: Connection,
    workspace_id: UUID,
    *,
    state: WorkspaceState,
    state_detail: str | None,
) -> None:
    """Write ``state`` and ``state_detail``; ``workspace_missing`` when no row."""
    result = conn.execute(
        update(t.workspace)
        .where(t.workspace.c.id == workspace_id)
        .values(
            state=WorkspaceState(state).value,
            state_detail=state_detail,
            state_changed_at=_now(),
        )
    )
    if result.rowcount != 1:
        raise StorageRefusal(WORKSPACE_MISSING, f"workspace {workspace_id} has no row")


# --- membership -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MembershipRow:
    account_id: UUID
    workspace_id: UUID
    role: Role
    created_at: datetime


def _membership(row: RowMapping) -> MembershipRow:
    return MembershipRow(
        account_id=row["account_id"],
        workspace_id=row["workspace_id"],
        role=Role(row["role"]),
        created_at=row["created_at"],
    )


def insert_membership_if_absent(
    conn: Connection, *, account_id: UUID, workspace_id: UUID, role: Role
) -> MembershipRow:
    """The membership row, inserted if absent. Only ``owner`` and ``member`` are
    membership roles; ``operator`` and ``service`` are boundary roles, never rows.

    ``account_missing`` / ``workspace_missing`` when a foreign key is unmet.
    """
    if Role(role).value not in t.MEMBERSHIP_ROLES:
        raise ValueError(f"{role.value!r} is not a membership role")
    statement = (
        pg_insert(t.membership)
        .values(
            account_id=account_id,
            workspace_id=workspace_id,
            role=role.value,
            created_at=_now(),
        )
        .on_conflict_do_nothing(
            index_elements=[t.membership.c.account_id, t.membership.c.workspace_id]
        )
    )
    try:
        conn.execute(statement)
    except IntegrityError as exc:
        if isinstance(exc.orig, psycopg.errors.ForeignKeyViolation):
            if "account" in _constraint_name(exc):
                raise StorageRefusal(
                    ACCOUNT_MISSING, f"account {account_id} does not exist"
                ) from None
            raise StorageRefusal(
                WORKSPACE_MISSING, f"workspace {workspace_id} does not exist"
            ) from None
        raise
    row = get_membership(conn, account_id=account_id, workspace_id=workspace_id)
    if row is None:  # pragma: no cover - the insert or the existing row is visible
        raise StorageRefusal(WORKSPACE_MISSING, "membership row vanished")
    return row


def get_membership(
    conn: Connection, *, account_id: UUID, workspace_id: UUID
) -> MembershipRow | None:
    found = (
        conn.execute(
            select(t.membership).where(
                t.membership.c.account_id == account_id,
                t.membership.c.workspace_id == workspace_id,
            )
        )
        .mappings()
        .first()
    )
    return None if found is None else _membership(found)
