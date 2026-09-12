# Shared Python core/worker image. The default command serves apps/core's
# hello-world /healthz on 8000; a worker-mode command override is 0c's concern,
# not 0a's. The build context is the checkout root (deploy/compose.yaml sets
# `context: ..`), so the COPYs below are repo-root-relative.
FROM python:3.12-slim

# Pin uv to an exact version (spec.md Technical Risks, risk 1: uv is the newer
# pick, so it is pinned rather than floated). Copying the static binary from the
# official uv image is uv's recommended, reproducible install path.
COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /uvx /bin/

WORKDIR /app

# Root build manifests first. The .dockerignore re-include (C4) is what lands
# these three in the build context; without it `uv sync --frozen` below has no
# manifest or lock and fails.
COPY pyproject.toml uv.lock .python-version ./

# Python workspace members the lock resolves (every member except apps/web,
# which is a pnpm app excluded from the uv workspace).
COPY packages/ ./packages/
COPY apps/core ./apps/core
COPY apps/worker ./apps/worker
COPY apps/mcp ./apps/mcp
COPY apps/cli ./apps/cli
COPY modules/ ./modules/
COPY connectors/ ./connectors/
COPY runtimes/ ./runtimes/
COPY channels/ ./channels/

# `uv sync --frozen` installs alembic's own console script (.venv/bin/alembic)
# as a side effect of resolving the alembic dependency; drop it so the image
# matches the ratified claim (storage-and-workspaces.md § Migrations): "Alembic's
# own command is not installed as a console script in the image." The real
# defence is each env.py refusing to run without the orchestrator's connection;
# this closes the doc/reality gap around it.
RUN uv sync --frozen \
    && rm -f /app/.venv/bin/alembic

# The in-image data root (rheo_core.storage.data_root reads RHEO_IN_CONTAINER to
# pick it) and the flag that makes that branch live rather than dead code.
RUN mkdir -p /var/lib/rheo-stream
ENV RHEO_IN_CONTAINER=1

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "rheo_app_core.main:app", "--host", "0.0.0.0", "--port", "8000"]
