"""The migration orchestrator: the only entry point for Alembic.

**No Alembic by hand: this paragraph is the rule's one home.** There is no
``alembic.ini`` and no console script in the image; each chain's ``env.py`` never
reads ``sqlalchemy.url`` and refuses with a ``RuntimeError`` unless
``orchestrator.py`` has passed the live connection through
``config.attributes["connection"]``, so Alembic invoked by hand has no URL, no
connection, and nothing to upgrade. The other files in this package cross-reference
this paragraph rather than restate it.

Two chains live here as Alembic script directories: ``control/`` (the control plane,
one ratified revision creating all ten tables, never edited afterwards) and ``core/``
(the per-workspace ``core`` schema, one revision creating exactly six tables; later
chain steps append revisions). Module chains in manifest dependency order are phase 2;
only the hook shape exists.
"""
