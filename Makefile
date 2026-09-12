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
	python3 scripts/check_routing_literals.py

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
# our service returns (a bare 200, or a foreign body that happens to contain the
# key, could come from an unrelated process already holding the port) and the web
# page renders the *healthy* core seam ("contract v...") rather than merely
# returning 200 (the shell 200s even when it can't reach core). Host ports are all
# overridable (RHEO_PG_PORT/RHEO_CORE_PORT/RHEO_WEB_PORT) for a machine where a
# default is already taken by something else; running this target requires those
# ports free, so stop `make up`'s shared stack first if it is using the same ones.
#
# Isolated, not merely hermetic: runs in its OWN compose project
# (`-p rheo-stream-demo`), so its containers, network, and the two named volumes
# it creates are namespaced apart from the shared `rheo-stream` project `make
# up`/`make down` manage — `down -v` at teardown can only ever remove volumes this
# target itself created, never a developer's own data. The operator sequence's
# data root is a fresh `mktemp -d` (never `.rheo-local`), removed at teardown
# because this target created it; RHEO__storage__cluster_dsn_ref is pinned so a
# stray, pre-existing deployment.toml elsewhere cannot redirect the operator
# sequence at a different cluster. Every step's failure is checked directly (`||`
# / `if !`) so `set -e` can never make a FAIL line unreachable.
#
# Isolation means this target cannot COEXIST on the same host ports as a running
# `make up` (or anything else already using them) — both would try to bind the
# same host port, and Docker doesn't namespace host ports by compose project. A
# preflight probes the three host ports this target needs before creating
# anything, so that collision fails fast with a message naming the remedy
# (`make down`, or override the port) instead of a raw "port is already
# allocated" Docker error that sends a developer to debug networking instead of
# stopping the shared stack. The preflight only reads (a TCP connect attempt via
# bash's /dev/tcp); it never stops or removes anything itself.
demo:
	@set -e; \
	demo_project="rheo-stream-demo"; \
	pg_port="$${RHEO_PG_PORT:-5432}"; \
	core_port="$${RHEO_CORE_PORT:-8000}"; \
	web_port="$${RHEO_WEB_PORT:-3000}"; \
	port_in_use() { \
		(exec 3<>"/dev/tcp/127.0.0.1/$$1") 2>/dev/null; \
		in_use_rc=$$?; \
		exec 3>&- 2>/dev/null || true; \
		exec 3<&- 2>/dev/null || true; \
		return $$in_use_rc; \
	}; \
	preflight_failed=0; \
	for portspec in "$$pg_port:postgres:RHEO_PG_PORT" "$$core_port:core:RHEO_CORE_PORT" "$$web_port:web:RHEO_WEB_PORT"; do \
		p="$${portspec%%:*}"; \
		rest="$${portspec#*:}"; \
		label="$${rest%%:*}"; \
		varname="$${rest#*:}"; \
		if port_in_use "$$p"; then \
			echo "FAIL  port $$p ($$label) is already in use — if that is this project's 'make up' dev stack, run 'make down' first; otherwise set $$varname to a free port"; \
			preflight_failed=1; \
		fi; \
	done; \
	if [ "$$preflight_failed" != 0 ]; then \
		exit 1; \
	fi; \
	demo_data_root="$$(mktemp -d)"; \
	WEB_PID=""; \
	cleanup() { \
		if [ -n "$$WEB_PID" ]; then kill "$$WEB_PID" 2>/dev/null || true; fi; \
		docker compose -p "$$demo_project" -f deploy/compose.yaml down -v || true; \
		rm -rf "$$demo_data_root"; \
	}; \
	trap cleanup EXIT; \
	docker compose -p "$$demo_project" -f deploy/compose.yaml up -d; \
	echo "Waiting for postgres to accept connections..."; \
	for _ in $$(seq 1 60); do \
		if docker compose -p "$$demo_project" -f deploy/compose.yaml exec -T postgres pg_isready -U rheo -d rheo >/dev/null 2>&1; then break; fi; \
		sleep 1; \
	done; \
	demo_dsn="postgresql://rheo:rheo_dev_only@localhost:$$pg_port/postgres"; \
	echo "Running rheo migrate..."; \
	RHEO_CLUSTER_DSN="$$demo_dsn" RHEO__storage__cluster_dsn_ref="secret://env/RHEO_CLUSTER_DSN" \
		RHEO_PROFILE=development RHEO_DATA_ROOT="$$demo_data_root" uv run rheo migrate \
		|| { echo "FAIL  rheo migrate"; exit 1; }; \
	echo "PASS  rheo migrate"; \
	echo "Running rheo account create..."; \
	account_id="$$(RHEO_CLUSTER_DSN="$$demo_dsn" RHEO__storage__cluster_dsn_ref="secret://env/RHEO_CLUSTER_DSN" \
		RHEO_PROFILE=development RHEO_DATA_ROOT="$$demo_data_root" \
		uv run rheo account create --provider github --subject demo-owner --display-name "Demo owner")" \
		|| { echo "FAIL  rheo account create"; exit 1; }; \
	if [ -z "$$account_id" ]; then \
		echo "FAIL  rheo account create  produced no account id on stdout"; exit 1; \
	fi; \
	echo "PASS  rheo account create  $$account_id"; \
	echo "Running rheo workspace create --owner $$account_id..."; \
	RHEO_CLUSTER_DSN="$$demo_dsn" RHEO__storage__cluster_dsn_ref="secret://env/RHEO_CLUSTER_DSN" \
		RHEO_PROFILE=development RHEO_DATA_ROOT="$$demo_data_root" \
		uv run rheo workspace create --owner "$$account_id" >/dev/null \
		|| { echo "FAIL  rheo workspace create --owner $$account_id"; exit 1; }; \
	echo "PASS  rheo workspace create --owner $$account_id"; \
	echo "Waiting for core /healthz..."; \
	core_up=0; \
	for _ in $$(seq 1 60); do \
		if curl -sf "http://localhost:$$core_port/healthz" 2>/dev/null | grep -q '"status":"ok","contract_version":'; then core_up=1; break; fi; \
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
	if curl -sf "http://localhost:$$core_port/healthz" 2>/dev/null | grep -q '"status":"ok","contract_version":'; then \
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
