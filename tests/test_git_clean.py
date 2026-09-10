"""Criterion 2 foundation: a representative Python startup writes nothing new.

Captures ``git status --porcelain`` (default flags — never ``-uall``, which can be
slow on a large tree and is not needed for a set difference) before and after a
representative "startup": importing apps/core's FastAPI ``app`` and issuing an
in-process ``GET /healthz`` (the ``httpx.ASGITransport`` pattern of test_healthz),
then calling the CLI entry point. It asserts the after-set introduces no line absent
from the before-set — NOT that either capture is empty. The working tree can start
dirty on this branch (a pre-existing uncommitted doc change, and the run tail runs in
a worktree off main), so a global "clean" assertion would false-fail.

Docker/compose stay out of ``uv run pytest`` (spec.md Technical Risks, risk 6); the
same "writes nothing to the tracked tree" property is proved end-to-end — Postgres
and the container build included — by ``make demo``.
"""

import subprocess
from pathlib import Path

import httpx
from rheo_app_cli.main import main as cli_main
from rheo_app_core.main import app

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _porcelain() -> "set[str]":
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=_REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return {line for line in result.stdout.splitlines() if line}


async def _exercise_startup() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    cli_main([])


async def test_startup_writes_nothing_new_to_tracked_tree() -> None:
    before = _porcelain()
    await _exercise_startup()
    after = _porcelain()
    introduced = sorted(after - before)
    assert not introduced, f"startup introduced new working-tree changes: {introduced}"
