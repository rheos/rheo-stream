"""``rheo member add --workspace --account --role``.

A plain ``insert_membership_if_absent`` call (the same C3 repository function
``rheo workspace create``'s provisioning step already writes the owner row
through) under an operator context — a fresh stack signs a second identity in
without provisioning it a whole new workspace. Output contract matches every
other CLI command: nothing but a confirmation to stderr; unlike ``account
create``/``workspace create`` this command mints no id of its own, so stdout
stays silent on success.
"""

import argparse
import sys
from uuid import UUID

from rheo_contracts import Role
from rheo_core.storage.control_plane import insert_membership_if_absent

from rheo_app_cli.context import bootstrap


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    parser = subparsers.add_parser("member", help="workspace memberships")
    commands = parser.add_subparsers(dest="member_command", metavar="<command>")
    commands.required = True
    add = commands.add_parser("add", help="add an account to a workspace")
    add.add_argument("--workspace", required=True, type=UUID, metavar="WORKSPACE_ID")
    add.add_argument("--account", required=True, type=UUID, metavar="ACCOUNT_ID")
    add.add_argument(
        "--role",
        required=True,
        choices=[Role.OWNER.value, Role.MEMBER.value],
        help="owner or member",
    )
    add.set_defaults(handler=add_member)


def add_member(args: argparse.Namespace) -> int:
    boot = bootstrap()
    with boot.backend.control_engine.begin() as connection:
        insert_membership_if_absent(
            connection,
            account_id=args.account,
            workspace_id=args.workspace,
            role=Role(args.role),
        )
    print(
        f"account {args.account} added to workspace {args.workspace} as {args.role}",
        file=sys.stderr,
    )
    return 0
