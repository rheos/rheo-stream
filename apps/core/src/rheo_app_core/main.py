"""FastAPI composition root for the `core` process.

0a exposes exactly one route, GET /healthz, so 03's web shell has a real endpoint
to compose against. No database connection lives in this app; the boundary
middleware, service registry, and MCP surface are 0c work.

This module also imports rheo_core and rheo_app_mcp at module scope to establish
the composition-root import edges the architecture draws — "apps/core... importing
rheo_core/rheo_contracts and apps/mcp" (spec.md § System Components) — even though
neither is called yet in 0a.
"""

import rheo_app_mcp
import rheo_core
from fastapi import FastAPI
from rheo_contracts import CONTRACT_VERSION

# Neither package is called in 0a; naming them here records the composition-root
# import edges without leaving a bare unused import (ruff F401).
_COMPOSITION_ROOT_EDGES = (rheo_core, rheo_app_mcp)

app = FastAPI()


@app.get("/healthz")
def healthz() -> dict[str, object]:
    """Liveness probe and the 02->03 seam.

    The exact body shape {"status": "ok", "contract_version": <int>} is what 03's
    web shell fetches and parses; contract_version is rheo_contracts.CONTRACT_VERSION,
    never a literal. tests/test_healthz.py pins it.
    """
    return {"status": "ok", "contract_version": CONTRACT_VERSION}
