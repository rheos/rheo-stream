# Identity, sessions, tokens, and URL topology

**Part of:** the [architecture specification](README.md). Designs against D6, D7, D10, R1, FR 1,
FR 3 to FR 6, FR 47, FR 48, and criteria 8, 9, 22, 23. Records the ratified host assignments.
**Decision:** A11 (host-only session cookies with an identity-host session grant; identity
endpoints on every application host). See the [decision list](README.md#architecture-decisions).

## The identity-provider boundary (D6, FR 3)

```text
IdentityProvider
  provider_id: str
  begin(state: str, callback_url: str) -> RedirectTarget
  complete(callback_params, state: str) -> ProviderIdentity
     ProviderIdentity: provider_id, subject, email | None, email_verified: bool, display_name
```

That is the whole boundary. `rheo_core.identity` owns it, resolves a `ProviderIdentity` to an
`account` through `control.identity`, creates the account on first login when the deployment
setting `identity.allow_signup` permits (default `true` on a fresh install, `false` once an owner
exists unless changed), and creates the session. Providers live in
`rheo_core.identity.providers.<provider_id>`; the GitHub implementation is the only shipped one,
configured by `control.identity_provider` with the client secret as a reference. Domain modules
import neither the providers package nor the boundary; a CI check asserts it (criterion 8). The
test double is a provider that completes with a fixed synthetic identity, registered by the test
harness only.

An account is not a workspace. Membership is many-to-many with a role (R1), and every context
carries the role read from `control.membership` at request time, never cached in the session.

## Accounts, sessions, and the active workspace

A web session is a `control.session` row. Its `active_workspace_id` is the only source of "which
workspace" for a web request. The workspace switcher calls `core.session.set_active_workspace`,
which checks membership and updates the row; it is the one operation that takes a workspace id
as input, and it takes it as the *target* of a membership check, not as routing. After a switch,
every request in that session routes to the new workspace with no identifier in any URL, which is
what criterion 6 requires literally. Session lifetime: idle expiry `identity.session_idle_days`
(default 14), absolute `identity.session_max_days` (default 30); logout revokes the row, which
ends every host's cookie at once because every cookie carries the same session id.

## Tokens for CLI and MCP (FR 4)

| Concern | Design |
| --- | --- |
| Format | `rheo_<kind>_<43 base64url chars>`: 256 random bits from a CSPRNG. Only the SHA-256 is stored (`access_token.token_hash`). |
| Scope | Exactly one account, one workspace, one operation set. The operation set is chosen at issuance from the named sets the workspace defines or the package ships (`read_only`, `agent_default`, `cli_full`), never widened later; a new scope is a new token. |
| Kinds | `cli` may include `core.approval.*`; `mcp` may not, and issuance refuses an `mcp` token whose set contains one. `runtime` is the run-scoped `mcp` token the runtime adapter issues for a single run ([runtime](runtime-and-mcp.md#claudecliruntime)). |
| Issuance | From an authenticated web session (`core.token.issue`, the account issuing for itself in a workspace it belongs to), or on a headless install by `rheo token issue --account <id> --workspace <id> --set <name>` on the operator command against the control plane. The value is shown once. |
| Lifetime | `cli` default 90 days, `mcp` default 30 days (`identity.token_max_days`, floor `min`), `runtime` the run's deadline. |
| Presentation | `Authorization: Bearer` on the `api` and `mcp` surfaces; the surfaces ignore cookies. No browser flow is ever involved after issuance. |
| Refusal | Malformed, expired, revoked, and out-of-scope each return a distinct state (`token_malformed`, `token_expired`, `token_revoked`, `operation_not_permitted`) at the boundary, before any service runs, with no partial effect (criterion 9). |
| Revocation | `core.token.revoke`; membership removal revokes the account's tokens for that workspace. |

The operator command that adds a second member (`rheo member add --workspace <id> --account
<id> --role member`) is the only way a second membership exists in release one (R1); criterion 8's
member session comes from that member signing in through the provider.

## Sessions and cookies

The ratified requirements say that in subdomain mode one session covers the shell host, the
identity host, and the module hosts; that `api.` and `mcp.` authenticate by token and ignore the
cookie; and that the apex, `docs.`, and the reserved integration host must not receive the cookie.
A cookie scoped to the parent domain would be sent by the browser to every host beneath it,
including hosts served by other software, so cookie scope cannot satisfy the last rule and a
reverse proxy cannot strip what is sent to a different server. This specification therefore uses
**host-only cookies and a session grant**.

- The session cookie `rheo_session` is set with no `Domain` attribute, `Secure`, `HttpOnly`,
  `SameSite=Lax`, `Path=/`, on each application host separately. Its value is the session id.
- The identity host (`auth.` in subdomain mode) holds the primary cookie after login.
- When an application host receives a request with no valid cookie, the web tier redirects to
  `<identity>/auth/continue?return=<absolute url>`, built through the routing configuration
  from the forwarded host, never from a hard-coded name.
- `/auth/continue` on the identity host: with a valid session cookie, it writes a
  `control.session_grant` row (a random 256-bit code, its SHA-256 stored, `target_host` set to
  the return URL's host, 60-second expiry, single use) and redirects to
  `<return host>/auth/continue?code=<code>`. Without one, it starts the login flow and returns
  here afterward.
- `/auth/continue` on the application host: the core (which serves `/auth/*` on every
  application host) looks up the code's hash, checks `target_host` equals the request's forwarded
  host and the code is unused and unexpired, marks it used, sets the host-only cookie for this
  host, and redirects to the return path. The session id is the same, so it is one session.
- In single-host path mode there is one host: `/auth/continue` finds the cookie directly and
  redirects to the return path. Same code, no grant row, which is why both modes are one
  implementation (criterion 22).
- Logout on any host revokes the session row; every other host's cookie now names a revoked
  session and is cleared on its next request.

CSRF: state-changing web requests are Next.js server actions and route handlers that check
`Origin` against the routing configuration's host set; the `/auth/*` POSTs do the same. The
`api` and `mcp` surfaces accept no cookie, so they need no CSRF defence. CORS: no
`Access-Control-Allow-Origin` is emitted anywhere by default; `api.cors_origins` (deployment
setting, empty) exists for a later second front end and is not needed by the first-party web
tier, which reaches the core server-side.

## URL topology as configuration (D7, FR 47)

### The routing configuration

One typed object, loaded by the core from deployment settings and served to the web tier at
startup through the internal API (and to the browser as a serialised copy in the shell's initial
render):

```text
RoutingConfig
  mode: "path" | "subdomain"
  scheme: "https"
  base_host: "example.test"                 # the apex in subdomain mode; the single host in path mode
  surfaces:
    shell:    { host: "circuit", path: "/" }
    identity: { host: "auth",    path: "/auth" }
    api:      { host: "api",     path: "/api" }
    mcp:      { host: "mcp",     path: "/mcp" }
    docs:     { host: "docs",    external: true }
    integration: { host: "tuttle", external: true, reserved: true }
    modules:  { leads: { host: "leads", path: "/leads" }, current: {...}, recallatron: {...}, relationships: {...} }
```

Both the Python core and the web tier expose one function, `url_for(surface, path)`, and every
link, redirect, callback URL, and MCP configuration file goes through it. In `subdomain` mode it
yields `https://<host>.<base_host><path>`; in `path` mode `https://<base_host><surface path><path>`.
The OAuth callback URL registered with the provider is `url_for("identity", "/callback")`, which
is `https://auth.example.test/auth/callback` in one mode and `https://example.test/auth/callback`
in the other (criterion 22). A route string that names a host or a topology-specific prefix
anywhere else is a lint failure in both codebases.

### The routing table

The reverse proxy's rules are the same in both modes; only the host matching changes:

| Request | Goes to |
| --- | --- |
| Any application host, `/auth/*` | `core` (identity endpoints) |
| `api` surface | `core` (HTTP API, intake receiver); token auth |
| `mcp` surface | `core` (MCP facade); token auth |
| Any application host, everything else | `web` |
| apex, `docs`, `tuttle` | not this application |

"Application host" means the shell host, the identity host, and every module host in subdomain
mode, and the single host in path mode. Inside `web`, the module's route tree is mounted at
`url_for(module, "/")`, so a module's screens are the same components under either topology.

### The reference deployment's hosts

Recorded from the ratified requirements; each is configuration a self-hoster may change.

| Host | Role | Served by |
| --- | --- | --- |
| apex `rheo.stream` | Project and marketing page | Not the application. Never receives the session cookie. |
| `circuit.rheo.stream` | The application shell and the workspace switcher | `web` |
| `auth.rheo.stream` | Login, the OAuth callback, the session grant | `core` |
| `leads.`, `current.`, `recallatron.`, `relationships.` | Module surfaces | `web` |
| `api.rheo.stream` | HTTP API and intake | `core`, token auth |
| `mcp.rheo.stream` | MCP facade | `core`, token auth |
| `docs.rheo.stream` | Documentation | Not the application. |
| `tuttle.rheo.stream` | Reserved for the back-office integration surface | Not the application; nothing in release one. |
| `app.rheo.stream` | Kept in reserve as a permanent redirect to `circuit.` | Reverse-proxy configuration, implemented in the deployment phase; not part of this specification's application routing. |

Subdomain mode needs wildcard DNS (`*.rheo.stream` to the proxy) and a wildcard certificate for
one label; the proxy terminates TLS for every host in the table. Single-host path mode needs one
name and one certificate and is the default a fresh install produces (edge case 19), which is the
arrangement guardrail 15 keeps continuously exercised.

### Constraint carried to the hosted edition

Module subdomains and per-tenant subdomains compete for the one label a wildcard certificate
covers. A hosted edition that wants `<tenant>.rheo.stream` cannot also have
`leads.rheo.stream` mean "the Leads module for the current tenant" without either a second
label (`leads.<tenant>.rheo.stream`, needing a certificate per tenant or a deeper wildcard) or a
return to path mode per tenant. It must choose deliberately ([later phases](later-phases.md#phase-8-the-hosted-edition));
nothing in release one presumes either answer, because the routing configuration is the only
place hosts are named.

## Platform independence (D10, FR 48)

The web tier runs under `next start` behind the proxy with no edge function, no hosted image
pipeline, and no build integration from any hosting platform. The build fails on a platform-only
import or configuration key by a dependency allow list and a check over `next.config` (criterion
23). Redirects from middleware are absolute URLs built from the forwarded host through
`url_for`, never relative, and never from the internal listener's host.
