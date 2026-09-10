"""Criterion 3 foundation: checkout-local runtime artifacts are git-ignored.

Creates one representative file per ``.rheo-local/`` artifact family and asserts each
is reported ignored by ``git check-ignore``, then removes only what it created so the
checkout is left as it started.

Every fixture path carries a unique per-run token (e.g.
``.rheo-local/workspaces/<uuid>/profile.json``), never a fixed literal path. Later
phases keep real workspace data under ``.rheo-local/``, so writing then deleting a
fixed shared path like ``.rheo-local/workspaces/demo/profile.json`` would be a
data-loss footgun. ``.rheo-local/`` is already gitignored, so a leftover would not
trip ``test_git_clean``; the teardown is tidiness, and removes only this run's own
subpaths.
"""

import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _artifact_relpaths(token: str) -> "tuple[str, ...]":
    """Representative artifact per checkout-local family, keyed by a unique token."""
    # A workspace profile/config and a database backup are the two families
    # criterion 3 names explicitly; the rest exercise the other .rheo-local/ trees.
    return (
        f".rheo-local/workspaces/{token}/profile.json",
        f".rheo-local/uploads/{token}/evidence.pdf",
        f".rheo-local/transcripts/{token}/session.jsonl",
        f".rheo-local/exports/{token}/workspace.csv",
        f".rheo-local/backups/{token}.sql",
        f".rheo-local/memory/{token}/index.bin",
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
    token = uuid.uuid4().hex
    relpaths = _artifact_relpaths(token)
    rheo_local = _REPO_ROOT / ".rheo-local"
    preexisting = rheo_local.exists()
    created: list[Path] = []
    for relative in relpaths:
        path = _REPO_ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test artifact\n", encoding="utf-8")
        created.append(path)
    try:
        yield list(relpaths)
    finally:
        for path in created:
            path.unlink(missing_ok=True)
        if not preexisting:
            # The test brought .rheo-local into existence, so the whole tree is
            # ours to remove.
            shutil.rmtree(rheo_local, ignore_errors=True)
        else:
            # .rheo-local already held (possibly real) data: remove only the unique
            # per-run token dirs this test created, never a shared family path.
            for relative in relpaths:
                token_dir = (_REPO_ROOT / relative).parent
                if token in token_dir.name:
                    shutil.rmtree(token_dir, ignore_errors=True)


def test_checkout_local_artifacts_are_ignored(
    rheo_local_artifacts: "list[str]",
) -> None:
    not_ignored = [rel for rel in rheo_local_artifacts if not _is_ignored(rel)]
    assert not not_ignored, f"checkout-local artifacts not git-ignored: {not_ignored}"
