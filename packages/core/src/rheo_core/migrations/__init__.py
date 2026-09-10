"""The migration orchestrator: the only entry point for Alembic.

Two chains live here as Alembic script directories with no ``alembic.ini`` and no
console script: ``control/`` (the control plane, one ratified revision creating all
ten tables, never edited afterwards) and ``core/`` (the per-workspace ``core`` schema,
one revision creating exactly six tables; later chain steps append revisions). Each
chain's ``env.py`` refuses to run without the connection ``orchestrator.py`` passes
through ``config.attributes["connection"]``, so Alembic invoked by hand has no URL,
no connection, and nothing to upgrade. Module chains in manifest dependency order are
phase 2; only the hook shape exists.
"""
