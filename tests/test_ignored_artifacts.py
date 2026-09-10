"""Criterion 3 foundation: checkout-local runtime artifacts are git-ignored.

Creates one representative file per ``.rheo-local/`` artifact family and asserts each
is reported ignored by ``git check-ignore``, then removes them so the checkout is left
as it started. ``.rheo-local/`` is already gitignored, so a leftover would not itself
trip ``test_git_clean``; the teardown is tidiness, not correctness.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]

# One example per checkout-local artifact family the map names under .rheo-local/.
_ARTIFACTS = (
    ".rheo-local/workspaces/demo/profile.json",
    ".rheo-local/uploads/evidence.pdf",
    ".rheo-local/transcripts/session.jsonl",
    ".rheo-local/exports/workspace.csv",
    ".rheo-local/backups/database.sql",
    ".rheo-local/memory/index.bin",
)


def _is_ignored(relative: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", relative],
        cwd=_REPO_ROOT,
        check=False,
    )
    return result.returncode == 0


@pytest.fixture
def rheo_local_artifacts() -> "list[str]":
    rheo_local = _REPO_ROOT / ".rheo-local"
    preexisting = rheo_local.exists()
    created: list[Path] = []
    for relative in _ARTIFACTS:
        path = _REPO_ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test artifact\n", encoding="utf-8")
        created.append(path)
    try:
        yield list(_ARTIFACTS)
    finally:
        for path in created:
            path.unlink(missing_ok=True)
        # Only remove the tree if this test created it in the first place.
        if not preexisting and rheo_local.exists():
            shutil.rmtree(rheo_local)


def test_checkout_local_artifacts_are_ignored(
    rheo_local_artifacts: "list[str]",
) -> None:
    not_ignored = [rel for rel in rheo_local_artifacts if not _is_ignored(rel)]
    assert not not_ignored, f"checkout-local artifacts not git-ignored: {not_ignored}"
