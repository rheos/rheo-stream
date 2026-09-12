# Repository tooling

`python3 scripts/check_routing_literals.py` fails on a hard-coded route literal
(`http(s)://`, `/auth/`, `/api/`, `/mcp`) anywhere under `apps/web/src` or
`apps/core/src` outside `apps/web/src/lib/routing/` and the two FastAPI route
modules that serve those paths — every link must go through `url_for`/`urlFor`
instead. Self-tests itself on every run (plants a literal, confirms it is caught)
before scanning the real tree.

Run `python3 scripts/check_repository.py` from any directory in a checkout.
Git and Python 3.9 or newer are the only dependencies.

The check verifies that private runtime and local agent-instruction paths are
ignored, public source/example paths remain trackable, no ignored artifacts are
already tracked, and local inline
Markdown links resolve to tracked files or directories. Stage newly added public
files before running it. It does not scan file contents for secrets, validate
external URLs or Markdown anchors, or inspect release image/package contents.

Content review remains necessary before publishing. Future application tooling
must use synthetic isolated data and the agreed private-storage boundary.
