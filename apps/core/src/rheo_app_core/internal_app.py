"""The internal listener: a second, standalone FastAPI app (port 8100).

A separate instance from ``public_app`` — not a second mount on the same app —
because the two answer on different ports with entirely different trust models
(shared-secret header vs. cookie); ``internal_routes.py`` holds the two routes and
the shared-secret dependency that gates every one of them. 11's ``serve.py`` runs
this app and ``public_app`` under one event loop, in one process, so both share
every process-wide singleton (the settings resolver, the storage backend) without
either needing its own startup sequence: ``main.py``'s ``lifespan`` is
``public_app``'s alone, and by the time real traffic reaches this app the control
plane it reads is already migrated.
"""

from fastapi import FastAPI

from rheo_app_core.internal_routes import router

internal_app = FastAPI()
internal_app.include_router(router)
