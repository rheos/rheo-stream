"""``rheo migrate``: the control chain, then the ``core`` chain for every active
workspace, through the orchestrator (the only entry point for Alembic).

A workspace whose chain fails is marked ``unavailable`` by the orchestrator and the
loop continues; the command reports each and exits non-zero if any failed.
"""

import argparse
import sys

from rheo_core.migrations.orchestrator import (
    migrate_active_workspaces,
    migrate_control,
)

from rheo_app_cli.context import bootstrap


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    parser = subparsers.add_parser(
        "migrate", help="control chain, then the core chain per active workspace"
    )
    parser.set_defaults(handler=migrate)


def migrate(args: argparse.Namespace) -> int:
    boot = bootstrap()
    control = migrate_control(boot.backend)
    print(f"control plane {control.database_name}: at head", file=sys.stderr)
    results = migrate_active_workspaces(boot.backend)
    failed = 0
    for result in results:
        if result.ok:
            print(
                f"workspace {result.workspace_id} ({result.database_name}): at head",
                file=sys.stderr,
            )
        else:
            failed += 1
            print(
                f"workspace {result.workspace_id} ({result.database_name}): "
                f"unavailable: {result.detail}",
                file=sys.stderr,
            )
    print(
        f"{len(results)} active workspace(s) migrated, {failed} failed", file=sys.stderr
    )
    return 1 if failed else 0
