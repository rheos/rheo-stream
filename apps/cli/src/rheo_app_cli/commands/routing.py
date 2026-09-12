"""``rheo routing hosts``: the application hosts and the OAuth callback URL.

The two facts an operator needs that nothing else prints: which hosts the reverse
proxy must send to this application, and the exact callback URL to register with the
identity provider. Both are derived from the ``routing.*`` deployment settings, so
they answer for the deployment as configured rather than for the documented example.

Output contract, as elsewhere in this CLI: the values go to stdout, one per line —
the hosts sorted, then the callback URL — and the human-facing narrative goes to
stderr, so ``rheo routing hosts | tail -1`` is the callback URL.
"""

import argparse
import sys

from rheo_core.routing import IDENTITY, RoutingConfig, application_hosts, url_for

from rheo_app_cli.context import bootstrap


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    parser = subparsers.add_parser("routing", help="the URL topology")
    commands = parser.add_subparsers(dest="routing_command", metavar="<command>")
    commands.required = True
    hosts = commands.add_parser(
        "hosts", help="the application hosts, then the OAuth callback URL"
    )
    hosts.set_defaults(handler=routing_hosts)


def routing_hosts(args: argparse.Namespace) -> int:
    boot = bootstrap()
    config = RoutingConfig.from_settings(boot.settings)
    hosts = sorted(application_hosts(config))
    print(
        f"routing mode {config.mode.value}: {len(hosts)} application host(s), then "
        "the OAuth callback URL",
        file=sys.stderr,
    )
    for host in hosts:
        print(host)
    print(url_for(config, IDENTITY, "/callback"))
    return 0
