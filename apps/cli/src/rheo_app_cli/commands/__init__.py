"""The ``rheo`` subcommands. Each module exposes ``add_parser(subparsers)`` and its
handlers ``(args) -> int``; ``main.py`` wires them and owns the exit code.

Output contract (shared with the Makefile's ``demo`` target and ``deploy/README.md``):
``account create`` and ``workspace create`` write exactly the new id and a newline
to stdout; every diagnostic, progress line, warning and refusal goes to stderr; a
refusal prints its state name; exit ``0`` on success and non-zero on failure.
"""
