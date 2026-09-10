"""``rheo account create --provider <id> --subject <subject> --display-name <name>``.

One ``control.account`` row and its ``control.identity`` row, in one transaction,
through the C3 repositories. A plain control-plane insert: no provider call and no
signup rule (the identity component is 0b2's). ``identity.provider_id`` is a plain
text column, so no ``identity_provider`` row is needed. Exists here because
``membership.account_id`` is a foreign key to ``account``, so a fresh stack needs an
account before ``rheo workspace create --owner``.
"""

import argparse
import sys

from rheo_core.storage.control_plane import insert_account, insert_identity

from rheo_app_cli.context import bootstrap


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    parser = subparsers.add_parser("account", help="control-plane accounts")
    commands = parser.add_subparsers(dest="account_command", metavar="<command>")
    commands.required = True
    create = commands.add_parser(
        "create", help="one account and its login identity; prints the account id"
    )
    create.add_argument("--provider", required=True, metavar="ID", help="provider id")
    create.add_argument("--subject", required=True, help="the provider's subject")
    create.add_argument(
        "--display-name", required=True, dest="display_name", help="shown name"
    )
    create.set_defaults(handler=create_account)


def create_account(args: argparse.Namespace) -> int:
    boot = bootstrap()
    with boot.backend.control_engine.begin() as connection:
        account = insert_account(connection, display_name=args.display_name)
        identity = insert_identity(
            connection,
            account_id=account.id,
            provider_id=args.provider,
            provider_subject=args.subject,
        )
    print(
        f"account {account.id} created with identity {identity.provider_id}/"
        f"{identity.provider_subject}",
        file=sys.stderr,
    )
    # The output contract: exactly the id and a newline on stdout.
    print(account.id)
    return 0
