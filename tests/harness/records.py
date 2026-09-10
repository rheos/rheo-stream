"""``harness.note``: a workspace-database table created **through the storage
backend** (a ``UnitOfWork`` connection from the backend's pool), never by a shipped
migration, so the isolation tests have a record to write in one workspace and look
for in another. C4 adds the resolver and the ``harness.note.get`` operation on top.

Test-profile scaffolding: nothing under ``rheo_core`` knows this table exists.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from rheo_core.refs import uuid7
from sqlalchemy import (
    Column,
    Connection,
    DateTime,
    MetaData,
    Table,
    Text,
    insert,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

HARNESS_SCHEMA = "harness"

harness_metadata = MetaData(schema=HARNESS_SCHEMA)

note = Table(
    "note",
    harness_metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column("body", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


@dataclass(frozen=True, slots=True)
class NoteRow:
    id: UUID
    body: str
    created_at: datetime


def ensure_note_table(conn: Connection) -> None:
    """Create ``harness.note`` in the connection's database if it is absent."""
    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {HARNESS_SCHEMA}"))
    note.create(conn, checkfirst=True)


def write_note(conn: Connection, *, body: str) -> NoteRow:
    row = NoteRow(uuid7(), body, datetime.now(UTC))
    conn.execute(
        insert(note).values(id=row.id, body=row.body, created_at=row.created_at)
    )
    return row


def get_note(conn: Connection, note_id: UUID) -> NoteRow | None:
    found = conn.execute(select(note).where(note.c.id == note_id)).mappings().first()
    if found is None:
        return None
    return NoteRow(id=found["id"], body=found["body"], created_at=found["created_at"])


def list_notes(conn: Connection) -> tuple[NoteRow, ...]:
    rows = conn.execute(select(note).order_by(note.c.id)).mappings()
    return tuple(
        NoteRow(id=row["id"], body=row["body"], created_at=row["created_at"])
        for row in rows
    )
