# Canonical command surface for run 0a. Each target is a thin alias over the
# underlying uv/pnpm/docker commands (plan.md, "Canonical commands"); the tool
# commands are the stable contract E0c freezes, the Makefile is the convenience.
# Only `up`/`down`/`demo` need Docker running; `test`/`check` stay Docker-free.

.PHONY: install test lint typecheck build up down demo check

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

# End-to-end proof that `core` (in compose) and the web shell (under `next start`,
# outside compose — 0a does not containerize web, spec.md W1) compose without a
# shared container. Starts postgres + core, waits for both to answer (poll, not a
# fixed sleep), builds and starts web pointed at the published core, curls both,
# prints pass/fail, then always tears web and compose down via an EXIT trap. The
# named Postgres volume means this writes nothing into the tracked tree.
demo:
	@set -e; \
	WEB_PID=""; \
	cleanup() { \
		if [ -n "$$WEB_PID" ]; then kill "$$WEB_PID" 2>/dev/null || true; fi; \
		$(MAKE) down || true; \
	}; \
	trap cleanup EXIT; \
	$(MAKE) up; \
	echo "Waiting for postgres to accept connections..."; \
	for _ in $$(seq 1 60); do \
		if docker compose -f deploy/compose.yaml exec -T postgres pg_isready -U rheo -d rheo >/dev/null 2>&1; then break; fi; \
		sleep 1; \
	done; \
	echo "Waiting for core /healthz..."; \
	for _ in $$(seq 1 60); do \
		if curl -sf http://localhost:8000/healthz >/dev/null 2>&1; then break; fi; \
		sleep 1; \
	done; \
	RHEO_CORE_INTERNAL_URL=http://localhost:8000 pnpm -C apps/web build; \
	RHEO_CORE_INTERNAL_URL=http://localhost:8000 pnpm -C apps/web start & \
	WEB_PID=$$!; \
	rc=0; \
	if curl -sf http://localhost:8000/healthz >/dev/null 2>&1; then \
		echo "PASS  core  http://localhost:8000/healthz"; \
	else \
		echo "FAIL  core  http://localhost:8000/healthz"; rc=1; \
	fi; \
	web_ok=0; \
	for _ in $$(seq 1 30); do \
		if curl -sf http://localhost:3000/ >/dev/null 2>&1; then web_ok=1; break; fi; \
		sleep 1; \
	done; \
	if [ "$$web_ok" = 1 ]; then \
		echo "PASS  web   http://localhost:3000/"; \
	else \
		echo "FAIL  web   http://localhost:3000/"; rc=1; \
	fi; \
	exit $$rc

check:
	python3 scripts/check_repository.py
