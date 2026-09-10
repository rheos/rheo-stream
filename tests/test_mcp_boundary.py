"""Static import-boundary scan of apps/mcp (criterion 20 foundation).

The MCP facade imports the contracts (and, in 0c, the service registry) and nothing
from ``rheo_core.storage`` or any database driver. This is a static AST scan of every
``.py`` file under ``apps/mcp/`` — not a runtime import-graph walk, which could trip
on a transitive import pulled in by contracts. Given 0a's dependency-free-of-core
design, it asserts the stronger, simpler rule: no ``rheo_core`` import of any kind,
and no known DB-driver import (psycopg, sqlalchemy, asyncpg).
"""

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MCP_ROOT = _REPO_ROOT / "apps" / "mcp"
_FORBIDDEN_DRIVER_ROOTS = frozenset({"psycopg", "sqlalchemy", "asyncpg"})


def _offending_imports(tree: ast.AST) -> list[str]:
    """Return the imported module names that cross the MCP boundary.

    Any ``rheo_core`` import (of any depth) or any known DB-driver import offends.
    Relative imports (level > 0) stay inside apps/mcp and are ignored.
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
            if root == "rheo_core" or root in _FORBIDDEN_DRIVER_ROOTS:
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
