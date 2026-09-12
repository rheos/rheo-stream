"""The internal listener's two routes and its shared-secret dependency (C7b).

Container-network only — compose never publishes port 8100 (11 asserts this with
``make demo``). Every route depends on :func:`require_internal_secret`, which
compares ``X-Rheo-Internal`` in constant time against the secret resolved fresh, at
request time, from ``internal.secret_ref`` through this component's own secret
scope (mirroring the storage/identity scope-construction pattern: a scope built
once here, a value resolved at the moment of use, never cached). This listener
reads only its own three headers — ``X-Rheo-Internal``, ``X-Rheo-Session``,
``X-Rheo-Host`` — and never a cookie: a valid ``rheo_session`` cookie sent
alongside a request with no ``X-Rheo-Session`` header authenticates nothing here.
"""

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from rheo_core.boundary.context import Refusal
from rheo_core.boundary.factories import context_from_session
from rheo_core.routing import RoutingConfig
from rheo_core.secrets import SecretRef, SecretRefusal, SecretStore
from rheo_core.settings import resolve
from rheo_core.storage.data_root import resolve_data_root

from rheo_app_core.auth_routes import normalize_host

INTERNAL_SCOPE_COMPONENT = "internal"
INTERNAL_SCOPE_PREFIXES = (
    "secret://file/internal/",
    "secret://env/RHEO_INTERNAL_SECRET",
)

_SECRET_KEY = "internal.secret_ref"


def _resolved_internal_secret() -> bytes:
    settings = resolve()
    reference = SecretRef.parse(settings.get_str(_SECRET_KEY))
    store = SecretStore(resolve_data_root().path)
    scope = SecretStore.scope_for(INTERNAL_SCOPE_COMPONENT, *INTERNAL_SCOPE_PREFIXES)
    return store.resolve(reference, scope).expose()


def require_internal_secret(
    x_rheo_internal: str | None = Header(default=None, alias="X-Rheo-Internal"),
) -> None:
    """Refuse before either route below runs, unless ``X-Rheo-Internal`` matches
    the resolved secret in constant time. A missing header, or a secret that is
    not configured at all (the package default is an empty string), both refuse —
    neither ever falls back to trusting a cookie."""
    if not x_rheo_internal:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    try:
        expected = _resolved_internal_secret()
    except SecretRefusal as refusal:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from refusal
    if not expected or not hmac.compare_digest(
        x_rheo_internal.encode("utf-8"), expected
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


router = APIRouter(dependencies=[Depends(require_internal_secret)])


@router.get("/internal/v1/routing")
def routing_config() -> dict[str, object]:
    """The serialised :class:`RoutingConfig` (06's shape) — the contract 10 reads,
    proven byte-shape-compatible in ``00-index.md`` § Coupling seams."""
    return RoutingConfig.from_settings(resolve()).model_dump(mode="json")


@router.get("/internal/v1/session")
def session_info(
    x_rheo_session: str | None = Header(default=None, alias="X-Rheo-Session"),
    x_rheo_host: str | None = Header(default=None, alias="X-Rheo-Host"),
) -> dict[str, object]:
    """The account, active workspace, role and memberships behind
    ``X-Rheo-Session``/``X-Rheo-Host``, or the boundary's refusal state — never a
    cookie, and never a workspace id in any URL (B3)."""
    if not x_rheo_session or not x_rheo_host:
        return {"state": "session_missing"}
    try:
        secret = bytes.fromhex(x_rheo_session)
    except ValueError:
        return {"state": "session_missing"}
    ctx = context_from_session(secret, normalize_host(x_rheo_host))
    if isinstance(ctx, Refusal):
        return {"state": ctx.state}
    return {
        "state": "ok",
        "actor": {"kind": ctx.actor.kind.value, "id": str(ctx.actor.id)},
        "active_workspace_id": str(ctx.workspace_id),
        "role": ctx.role.value,
        "memberships": [
            {"workspace_id": str(ctx.workspace_id), "role": ctx.role.value}
        ],
    }
