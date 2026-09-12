"""Static import-boundary scan of apps/mcp (criterion 20 foundation).

The MCP facade imports the contracts, and, landed in 0b2 (C8) rather than
"later", ``rheo_core.boundary``, ``rheo_core.operations`` and
``rheo_core.tokens`` -- and nothing from ``rheo_core.storage``,
``rheo_core.migrations``, or a database driver. This is a static AST scan of
every ``.py`` file under ``apps/mcp/`` — not a runtime import-graph walk,
which could trip on a transitive import pulled in by contracts. It asserts an
allowlist over ``rheo_core``'s three permitted subpackages (each one, and
anything under it, by dotted prefix), keeping the driver denylist as before.
``rheo_core.tokens`` is on the allowlist for :func:`_offending_imports`'s
purposes because nothing under it touches storage or a driver -- consistent
with the rule this scan exists to enforce, not a carve-out from it.
"""

import ast
from pathlib import Path
from typing import Final

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MCP_ROOT = _REPO_ROOT / "apps" / "mcp"
_FORBIDDEN_DRIVER_ROOTS = frozenset({"psycopg", "sqlalchemy", "asyncpg"})
_ALLOWED_RHEO_CORE_PREFIXES: Final = (
    "rheo_core.boundary",
    "rheo_core.operations",
    "rheo_core.tokens",
)


def _allowed_rheo_core_import(name: str) -> bool:
    """True for ``rheo_core.boundary``/``.operations``/``.tokens`` and their
    submodules; false for everything else under ``rheo_core`` -- in
    particular ``rheo_core.storage`` and ``rheo_core.migrations``, and a bare
    ``rheo_core`` import naming no subpackage at all."""
    return any(
        name == prefix or name.startswith(f"{prefix}.")
        for prefix in _ALLOWED_RHEO_CORE_PREFIXES
    )


def _offending_imports(tree: ast.AST) -> list[str]:
    """Return the imported module names that cross the MCP boundary.

    A ``rheo_core`` import outside the allowlist above, or any known
    DB-driver import, offends. Relative imports (level > 0) stay inside
    apps/mcp and are ignored.
    """
    offenders: list[str] = []
    for node in ast.walk(tree):
        module_names: list[str] = []
        if isinstance(node, ast.Import):
            module_names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0 or node.module is None:
                continue
            module_names = [node.module]
        for name in module_names:
            root = name.split(".")[0]
            if root in _FORBIDDEN_DRIVER_ROOTS:
                offenders.append(name)
            elif root == "rheo_core" and not _allowed_rheo_core_import(name):
                offenders.append(name)
    return offenders


def test_mcp_imports_no_core_storage_or_db_driver() -> None:
    sources = sorted(_MCP_ROOT.rglob("*.py"))
    assert sources, f"no source files found under {_MCP_ROOT}"
    violations: dict[str, list[str]] = {}
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offenders = _offending_imports(tree)
        if offenders:
            violations[str(path.relative_to(_REPO_ROOT))] = offenders
    assert not violations, f"apps/mcp imports a forbidden module: {violations}"
