"""Tests that need the local Postgres (marker ``postgres``).

Every module here works through **direct repository, backend and engine calls**:
provision a workspace, get its engine from the pool by ``database_name``, open a
``UnitOfWork(engine, expected_database)``, and assert. No test hand-builds a
``WorkspaceContext``; ``route(ctx)`` and ``open_unit_of_work(ctx)`` are exercised in
C4, which owns the only legitimate way to obtain a context.
"""
