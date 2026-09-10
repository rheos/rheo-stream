"""In-process test of apps/core's GET /healthz (the 02->03 coupling seam).

Drives the FastAPI ``app`` object directly through httpx's ASGI transport — no
running server process, no Docker — and pins the exact response shape 03's web
shell fetches and parses. If this body changes, the run's one cross-coder seam
breaks. asyncio_mode = "auto" (pyproject) runs the async test without a decorator.
"""

import httpx
from rheo_app_core.main import app


async def test_healthz_returns_ok_and_contract_version() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "contract_version": 1}
