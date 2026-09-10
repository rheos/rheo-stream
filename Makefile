# Canonical command surface, started in run 0a. Each target is a thin alias over
# the underlying uv/pnpm/docker commands (plan.md, "Canonical commands"); the tool
# commands are the stable contract E0c freezes, the Makefile is the convenience.
# `test` needs a reachable Postgres (`make up`, or `RHEO_TEST_CLUSTER_DSN`
# pointing at one); `check` stays Docker-free.
#
# This deliberately reverses 0a's original rule ("only up/down/demo need Docker
# running; test/check stay Docker-free"), from run 0b1 on: `core` now makes a
# real database call at startup, and tests/conftest.py bridges the suite into the
# production settings->secret-scope path against a real cluster rather than an
# injected DSN. When the cluster is unreachable, `uv run pytest` fails fast
# (tests/conftest.py, pytest.exit) with a message naming the remedy — it never
# skips, because a skipped `postgres` marker would pass this gate vacuously.

.PHONY: install test lint typecheck build up down demo check migrate

install:
	uv sync --frozen
	pnpm install --frozen-lockfile

test:
	uv run pytest
	pnpm -C apps/web test

lint:
	uv run ruff check .
	uv run ruff format --check .
	pnpm -C apps/web lint

typecheck:
	uv run mypy
	pnpm -C apps/web exec tsc --noEmit

build:
	pnpm -C apps/web build
	docker build -f Dockerfile .

up:
	docker compose -f deploy/compose.yaml up -d

down:
	docker compose -f deploy/compose.yaml down

migrate:
	uv run rheo migrate

# End-to-end proof that `core` (in compose) and the web shell (under `next start`,
# outside compose — 0a does not containerize web, spec.md W1) compose without a
# shared container. Starts postgres + core, polls (not a fixed sleep) for core to
# answer and fails loudly if it never does, builds and starts web pointed at the
# published core, then asserts both seams: core answers /healthz with a body only
# our service returns (a bare 200 could come from an unrelated process already
# holding the port) and the web page renders the *healthy* core seam ("contract
# v...") rather than merely returning 200 (the shell 200s even when it can't reach
# core). Host ports are all overridable (RHEO_PG_PORT/RHEO_CORE_PORT/
# RHEO_WEB_PORT) for a machine where a default is already taken by something
# else. Hermetic: the EXIT trap always tears down web, containers, the two named
# volumes (`down -v`, unlike the plain `down` target, which deliberately leaves a
# developer's data alone) and the `.rheo-local` directory this target's operator
# sequence creates — so `make demo` is repeatable (a fixed --subject would
# otherwise collide with the previous run's account on the second invocation) and
# writes nothing durable outside the tracked tree.
demo:
	@set -e; \
	core_port="$${RHEO_CORE_PORT:-8000}"; \
	web_port="$${RHEO_WEB_PORT:-3000}"; \
	WEB_PID=""; \
	cleanup() { \
		if [ -n "$$WEB_PID" ]; then kill "$$WEB_PID" 2>/dev/null || true; fi; \
		docker compose -f deploy/compose.yaml down -v || true; \
		rm -rf .rheo-local; \
	}; \
	trap cleanup EXIT; \
	$(MAKE) up; \
	echo "Waiting for postgres to accept connections..."; \
	for _ in $$(seq 1 60); do \
		if docker compose -f deploy/compose.yaml exec -T postgres pg_isready -U rheo -d rheo >/dev/null 2>&1; then break; fi; \
		sleep 1; \
	done; \
	demo_dsn="postgresql://rheo:rheo_dev_only@localhost:$${RHEO_PG_PORT:-5432}/postgres"; \
	demo_data_root="$$(pwd)/.rheo-local"; \
	echo "Running rheo migrate..."; \
	if ! RHEO_CLUSTER_DSN="$$demo_dsn" RHEO_PROFILE=development RHEO_DATA_ROOT="$$demo_data_root" \
		uv run rheo migrate; then \
		echo "FAIL  rheo migrate"; exit 1; \
	fi; \
	echo "PASS  rheo migrate"; \
	echo "Running rheo account create..."; \
	account_id="$$(RHEO_CLUSTER_DSN="$$demo_dsn" RHEO_PROFILE=development RHEO_DATA_ROOT="$$demo_data_root" \
		uv run rheo account create --provider github --subject demo-owner --display-name "Demo owner")"; \
	if [ -z "$$account_id" ]; then \
		echo "FAIL  rheo account create  produced no account id on stdout"; exit 1; \
	fi; \
	echo "PASS  rheo account create  $$account_id"; \
	echo "Running rheo workspace create --owner $$account_id..."; \
	if ! RHEO_CLUSTER_DSN="$$demo_dsn" RHEO_PROFILE=development RHEO_DATA_ROOT="$$demo_data_root" \
		uv run rheo workspace create --owner "$$account_id" >/dev/null; then \
		echo "FAIL  rheo workspace create --owner $$account_id"; exit 1; \
	fi; \
	echo "PASS  rheo workspace create --owner $$account_id"; \
	echo "Waiting for core /healthz..."; \
	core_up=0; \
	for _ in $$(seq 1 60); do \
		if curl -sf "http://localhost:$$core_port/healthz" 2>/dev/null | grep -q '"contract_version"'; then core_up=1; break; fi; \
		sleep 1; \
	done; \
	if [ "$$core_up" != 1 ]; then \
		echo "FAIL  core  http://localhost:$$core_port/healthz did not become ready within 60s"; \
		exit 1; \
	fi; \
	RHEO_CORE_INTERNAL_URL="http://localhost:$$core_port" PORT="$$web_port" pnpm -C apps/web build; \
	RHEO_CORE_INTERNAL_URL="http://localhost:$$core_port" PORT="$$web_port" pnpm -C apps/web start & \
	WEB_PID=$$!; \
	rc=0; \
	if curl -sf "http://localhost:$$core_port/healthz" 2>/dev/null | grep -q '"contract_version"'; then \
		echo "PASS  core  http://localhost:$$core_port/healthz"; \
	else \
		echo "FAIL  core  http://localhost:$$core_port/healthz"; rc=1; \
	fi; \
	web_ok=0; \
	for _ in $$(seq 1 30); do \
		if curl -s "http://localhost:$$web_port/" | grep -q 'contract v'; then web_ok=1; break; fi; \
		sleep 1; \
	done; \
	if [ "$$web_ok" = 1 ]; then \
		echo "PASS  web   http://localhost:$$web_port/ (core seam healthy: contract v present)"; \
	else \
		echo "FAIL  web   http://localhost:$$web_port/ never rendered the healthy core seam (contract v)"; rc=1; \
	fi; \
	exit $$rc

check:
	python3 scripts/check_repository.py
