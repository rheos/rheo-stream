"""The `rheo` console-script stub.

The operator CLI runs in the core image and talks to the control plane and the
workspace databases through the core packages. Its real commands — workspace
create/repair, member add, token issue, migrate, export, restore, doctor — arrive
in 0c. 0a ships only the entry-point stub.
"""


def main() -> None:
    """Placeholder entry point; real command dispatch arrives in 0c."""
