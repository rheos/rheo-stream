# Repository tooling

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
