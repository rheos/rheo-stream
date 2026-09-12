"""Import and import-boundary tests for the Python workspace skeleton.

Three seams: both core distributions import cleanly and expose the contract version,
``rheo_core`` declares no dependency on any module distribution, and ``rheo_contracts``
imports nothing but the standard library, ``pydantic`` and itself. The two scans are
static AST walks (not a runtime import-graph walk, which could miss a lazily imported
name) over every source file under each package, the import-boundary foundation the
architecture names and criterion 20 later tests more fully against ``apps/mcp``.

The contracts scan is why the operation handler is not a field on
``OperationDeclaration``: its type mentions ``UnitOfWork``, which lives in
``rheo_core.storage``, and importing it here is exactly what this test refuses.
"""

import ast
import sys
from pathlib import Path

import rheo_contracts
import rheo_core

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CORE_SRC = _REPO_ROOT / "packages" / "core" / "src" / "rheo_core"
_CONTRACTS_SRC = _REPO_ROOT / "packages" / "contracts" / "src" / "rheo_contracts"
_ALLOWED_RHEO_ROOTS = {"rheo_contracts", "rheo_core"}
_CONTRACTS_ALLOWED_ROOTS = {"pydantic", "rheo_contracts"}


def test_core_packages_import_and_expose_contract_version() -> None:
    assert rheo_core is not None
    assert rheo_contracts.CONTRACT_VERSION == 1


def _offending_rheo_imports(tree: ast.AST) -> list[str]:
    """Return the ``rheo_*`` module roots imported outside the allowed set."""
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root.startswith("rheo_") and root not in _ALLOWED_RHEO_ROOTS:
                    offenders.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # A relative import (level > 0) stays inside rheo_core; only an
            # absolute ``from rheo_<x> import ...`` can cross the boundary.
            if node.level != 0 or node.module is None:
                continue
            root = node.module.split(".")[0]
            if root.startswith("rheo_") and root not in _ALLOWED_RHEO_ROOTS:
                offenders.append(node.module)
    return offenders


def test_core_imports_no_module_distribution() -> None:
    sources = sorted(_CORE_SRC.rglob("*.py"))
    assert sources, f"no source files found under {_CORE_SRC}"
    violations: dict[str, list[str]] = {}
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offenders = _offending_rheo_imports(tree)
        if offenders:
            violations[str(path.relative_to(_REPO_ROOT))] = offenders
    assert not violations, f"rheo_core imports a module distribution: {violations}"


def _contracts_import_allowed(root: str) -> bool:
    return root in sys.stdlib_module_names or root in _CONTRACTS_ALLOWED_ROOTS


def _offending_contracts_imports(tree: ast.AST) -> list[str]:
    """Return the imported module roots that ``rheo_contracts`` may not depend on."""
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _contracts_import_allowed(alias.name.split(".")[0]):
                    offenders.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # A relative import (level > 0) stays inside rheo_contracts; only an
            # absolute ``from <x> import ...`` can cross the boundary.
            if node.level != 0 or node.module is None:
                continue
            if not _contracts_import_allowed(node.module.split(".")[0]):
                offenders.append(node.module)
    return offenders


def test_contracts_import_only_stdlib_and_pydantic() -> None:
    sources = sorted(_CONTRACTS_SRC.rglob("*.py"))
    assert sources, f"no source files found under {_CONTRACTS_SRC}"
    violations: dict[str, list[str]] = {}
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offenders = _offending_contracts_imports(tree)
        if offenders:
            violations[str(path.relative_to(_REPO_ROOT))] = offenders
    assert not violations, f"rheo_contracts imports outside its boundary: {violations}"
