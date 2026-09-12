# Deployment templates

The local stack (`deploy/compose.yaml`): `make up` brings up two services, `postgres`
(`pgvector/pgvector:pg16`) and `core` (the FastAPI app, built from the repository
root `Dockerfile`). Both are published to the host — `core` on `RHEO_CORE_PORT`
(default `8000`) and `postgres` on `RHEO_PG_PORT` (default `5432`); override either
if its default is already bound by another project on your machine. Neither
container's own port changes: `core` always answers on `8000` and `postgres` on
`5432` inside the compose network regardless of a host-side remap. `make down`
tears the stack down.

The **data-root volume**: `core` writes checkout-external runtime state (the file
secret backend, deployment config, per-workspace upload/export/scratch directories —
see `docs/architecture/storage-and-workspaces.md` § The data root) under
`/var/lib/rheo-stream` inside the container, mounted from the named volume
`rheodata`. It is a **named volume, never a bind mount into the repository** — the
compose stack must write nothing into the tracked tree (criterion 2), and a bind
mount would do exactly that. Set `RHEO_DATA_ROOT` to point `core` at a different
path instead (e.g. for a host-side operator command sharing the container's data);
`RHEO_IN_CONTAINER=1` is what makes `/var/lib/rheo-stream` the in-image default when
`RHEO_DATA_ROOT` is unset.

The **0b1 operator sequence**, run against a freshly migrated cluster, in this exact
order:

```
rheo migrate
rheo account create --provider <id> --subject <subject> --display-name <name>
rheo workspace create --owner <account id>
```

`account create` must run before `workspace create --owner`: `membership.account_id`
is a foreign key to `account`, so a workspace's owner account has to exist first.
`account create` and `workspace create` each print exactly the new id and a newline
to stdout (every diagnostic goes to stderr), so a script can capture the id directly
from the command's output. Also available: `rheo workspace repair|list|status` and
`rheo doctor`. `rheo member add` and other multi-member commands do not exist at this
run's merge SHA — a later run documents them when they do.

Rate limiting of the webhook receiver and of `/auth/*` is the reverse proxy's
responsibility in release one; it is not implemented by `core` itself. This is a
recorded decision, not an omission — the reverse proxy is operator-provided and
generic per ratified decision D10.

Templates contain placeholders and secret references only. Runtime workspace data
belongs in private databases and volumes, outside source and image build contexts.
The root `.dockerignore` is a source-only starting policy; every future image and
package needs its own content review. No deployment runs from the initial CI.
