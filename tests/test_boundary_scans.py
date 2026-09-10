"""Two static AST scans for the secret store's boundary (B9).

Both copy the walk shape of ``tests/test_imports.py``: parse every Python source, walk
the tree, collect offenders, assert none. Static rather than a runtime import-graph
walk so a lazily imported name cannot hide.

1. ``SecretScope(`` is constructed only in files under
   ``packages/core/src/rheo_core/secrets/``. The scan root is the repository root,
   walking ``packages/``, ``apps/``, ``scripts/`` and ``tests/`` — tests included, so a
   test cannot forge a scope either.
2. No file under the top-level ``modules/`` distribution directory imports
   ``rheo_core.secrets``: domain modules are constructed without a scope and must have
   no way to reach the store.

``SKIP_DIRS`` is the shipped ``scripts/check_web_platform.py`` set plus ``__pycache__``
and ``.venv``; C4's ``tests/test_boundary.py`` declares its own copy rather than
importing this one, because the two files sit in different chunks' file maps.
"""

import ast
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCAN_DIRS = ("packages", "apps", "scripts", "tests")
_SECRETS_PACKAGE = _REPO_ROOT / "packages" / "core" / "src" / "rheo_core" / "secrets"
_MODULES_DIR = _REPO_ROOT / "modules"
_SECRETS_MODULE = "rheo_core.secrets"

# Generated build output and vendored dependencies, skipped while walking.
SKIP_DIRS = frozenset(
    {".next", "node_modules", "dist", "build", ".turbo", "__pycache__", ".venv"}
)


def _python_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        found.extend(
            Path(dirpath) / name for name in sorted(filenames) if name.endswith(".py")
        )
    return found


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _secret_scope_call_lines(tree: ast.AST) -> list[int]:
    """Line numbers of every call whose callee is named ``SecretScope``."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if isinstance(callee, ast.Name):
            name = callee.id
        elif isinstance(callee, ast.Attribute):
            name = callee.attr
        else:
            continue
        if name == "SecretScope":
            lines.append(node.lineno)
    return lines


def test_secret_scope_is_constructed_only_inside_the_secrets_package() -> None:
    scanned = 0
    violations: dict[str, list[int]] = {}
    for top in _SCAN_DIRS:
        for path in _python_files(_REPO_ROOT / top):
            scanned += 1
            if path.is_relative_to(_SECRETS_PACKAGE):
                continue
            lines = _secret_scope_call_lines(_parse(path))
            if lines:
                violations[str(path.relative_to(_REPO_ROOT))] = lines
    assert scanned, "no Python files scanned"
    assert not violations, (
        f"SecretScope( is constructed outside rheo_core/secrets/: {violations}"
    )
    # The scan is not vacuous: the one legitimate construction site exists.
    sites = [
        path.name
        for path in _python_files(_SECRETS_PACKAGE)
        if _secret_scope_call_lines(_parse(path))
    ]
    assert sites == ["scope.py"], sites


def _secrets_imports(tree: ast.AST) -> list[str]:
    """Every import that reaches ``rheo_core.secrets`` or anything beneath it."""
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == _SECRETS_MODULE or alias.name.startswith(
                    _SECRETS_MODULE + "."
                ):
                    offenders.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # A relative import (level > 0) cannot leave the module distribution.
            if node.level != 0 or node.module is None:
                continue
            if node.module == _SECRETS_MODULE or node.module.startswith(
                _SECRETS_MODULE + "."
            ):
                offenders.append(node.module)
            elif node.module == "rheo_core" and any(
                alias.name == "secrets" for alias in node.names
            ):
                offenders.append(_SECRETS_MODULE)
    return offenders


def test_no_module_distribution_imports_the_secret_store() -> None:
    assert _MODULES_DIR.is_dir(), f"missing {_MODULES_DIR}"
    violations: dict[str, list[str]] = {}
    # An empty walk is not an error: the module distributions may hold no source yet.
    for path in _python_files(_MODULES_DIR):
        offenders = _secrets_imports(_parse(path))
        if offenders:
            violations[str(path.relative_to(_REPO_ROOT))] = offenders
    assert not violations, (
        f"a module distribution imports rheo_core.secrets: {violations}"
    )
