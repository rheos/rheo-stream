"""``rheo workspace create|repair|list|status``.

``create --owner <account-id> [--slug <slug>]`` calls C3's ``provision`` and prints
the new workspace id; it does not write the owner ``membership`` row itself — the
provisioning state machine writes it with the ``workspace`` row in one transaction
(one writer, not two). ``repair`` resumes from ``state_detail``. ``status`` builds
an operator context through ``context_for_operator`` and dispatches
``core.workspace.status`` through the registry; provisioning and repair call the
storage services directly because they run outside any workspace transaction.
"""

import argparse
import sys
from uuid import UUID

from rheo_core.boundary import Refusal, context_for_operator
from rheo_core.operations import WORKSPACE_STATUS, dispatch
from rheo_core.refs import uuid7
from rheo_core.storage.control_plane import list_workspaces
from rheo_core.storage.provisioning import provision, repair

from rheo_app_cli.context import bootstrap


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    parser = subparsers.add_parser("workspace", help="workspaces and their databases")
    commands = parser.add_subparsers(dest="workspace_command", metavar="<command>")
    commands.required = True

    create = commands.add_parser(
        "create", help="provision a workspace for an owner; prints the workspace id"
    )
    create.add_argument(
        "--owner", required=True, type=UUID, metavar="ACCOUNT_ID", help="owner account"
    )
    create.add_argument("--slug", default=None, help="lowercase letters, digits, -")
    create.set_defaults(handler=create_workspace)

    repair_parser = commands.add_parser(
        "repair", help="resume provisioning or a failed migration to active"
    )
    repair_parser.add_argument("workspace_id", type=UUID)
    repair_parser.set_defaults(handler=repair_workspace)

    list_parser = commands.add_parser("list", help="every registry row")
    list_parser.set_defaults(handler=list_workspaces_command)

    status = commands.add_parser(
        "status", help="core.workspace.status through the registry, as JSON"
    )
    status.add_argument("workspace_id", type=UUID)
    status.set_defaults(handler=workspace_status)


def create_workspace(args: argparse.Namespace) -> int:
    bootstrap()
    workspace_id = uuid7()
    provision(workspace_id, owner_account_id=args.owner, slug=args.slug)
    print(f"workspace {workspace_id} is active", file=sys.stderr)
    # The output contract: exactly the id and a newline on stdout.
    print(workspace_id)
    return 0


def repair_workspace(args: argparse.Namespace) -> int:
    bootstrap()
    repair(args.workspace_id)
    print(f"workspace {args.workspace_id} is active", file=sys.stderr)
    return 0


def list_workspaces_command(args: argparse.Namespace) -> int:
    boot = bootstrap()
    with boot.backend.control_engine.connect() as connection:
        rows = list_workspaces(connection)
    for row in rows:
        print(f"{row.id}\t{row.slug}\t{row.state.value}\t{row.state_detail or ''}")
    return 0


def workspace_status(args: argparse.Namespace) -> int:
    bootstrap()
    ctx = context_for_operator(args.workspace_id)
    if isinstance(ctx, Refusal):
        print(ctx, file=sys.stderr)
        return 1
    outcome = dispatch(ctx, WORKSPACE_STATUS, {})
    if not outcome.ok or outcome.result is None:
        error = outcome.error
        print(
            outcome.state
            if error is None
            else f"{error.error_code}: {error.error_text}",
            file=sys.stderr,
        )
        return 1
    print(outcome.result.model_dump_json(indent=2))
    return 0
