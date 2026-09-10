# Behavioral tests

Reserved for future module contract, integration, migration, and acceptance tests.
Use synthetic isolated workspaces and exercise absent/disabled modules as well as
normal operation. Never load real user data or a production database.

The current scaffold is checked with
[`scripts/check_repository.py`](../scripts/check_repository.py). Storage, boundary,
registry, settings, secrets, and CLI behavior are now covered.

From run 0b1 on, `uv run pytest` needs a reachable Postgres cluster (`make up`, or
point `RHEO_TEST_CLUSTER_DSN` at one); the `postgres` marker selects the
database-touching tests, and the suite fails fast — never a silent skip — when the
cluster is unreachable.
