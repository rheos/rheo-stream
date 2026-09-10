"""The `core` process composition root (FastAPI under uvicorn).

Exposes GET /healthz and runs the startup sequence (settings, data root, the
control-plane migration, workspace migrations, the operation registry) in the
FastAPI lifespan. The context boundary and the service registry live in
``rheo_core`` and are wired here; the MCP surface and the ``api``/internal
listeners arrive in 0b2 and 0c. See main.py and startup.py.
"""
