SHELL := /bin/bash
.DEFAULT_GOAL := help

UV ?= uv
export UV_CACHE_DIR ?= $(CURDIR)/.uv-cache

.PHONY: help setup check check-clean canary lint fmt fmt-check types boundaries licenses secrets test eval-retrieval web-install dev-setup seed start stop restart status logs api web web-test db-migrate db-roundtrip up down docker-smoke clean

help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies from the lockfile
	$(UV) sync --locked --all-groups

check: lint fmt-check types boundaries licenses test ## Exactly what CI runs

lint: ## Lint with ruff
	$(UV) run ruff check .

fmt: ## Apply formatting
	$(UV) run ruff format .

fmt-check: ## Verify formatting without writing
	$(UV) run ruff format --check .

types: ## Static type check with pyright
	$(UV) run pyright

boundaries: ## Enforce module boundaries with import-linter
	$(UV) run lint-imports

licenses: ## Dependency licence allowlist
	$(UV) run python scripts/check_licenses.py

secrets: ## Secret scan over the full history (fails if it scanned nothing)
	bash scripts/secret_scan.sh

test: ## Run the test suite
	$(UV) run pytest

check-clean: ## Run make check in a fresh clone (catches untracked-file dependence)
	bash scripts/check_clean_clone.sh

canary: ## Break one behaviour and prove a test fails (see docs/RULEBOOK.md)
	@echo "usage: uv run python scripts/canary.py --file F --old OLD --new NEW --test TEST"

web-install: ## Install the web dependencies (local npm cache: the sandbox home is read-only)
	cd web && npm install --no-audit --no-fund --cache ./.npm-cache

DEV_DATABASE_URL ?= postgresql+asyncpg://firebrief:firebrief_dev@127.0.0.1:55433/firebrief_dev

dev-setup: ## Migrate and seed the local development database (never the test one)
	DATABASE_URL=$(DEV_DATABASE_URL) $(UV) run alembic upgrade head
	$(UV) run python scripts/dev_seed.py

seed: ## Re-create the local workspace, user and demonstration corpus
	$(UV) run python scripts/dev_seed.py

start: ## Start the API and web UI in the background
	./scripts/dev.sh start

stop: ## Stop the API and web UI
	./scripts/dev.sh stop

restart: ## Restart the API and web UI (after a config or dependency change)
	./scripts/dev.sh restart

status: ## Show whether the API and web UI are running
	./scripts/dev.sh status

logs: ## Follow both dev server logs
	./scripts/dev.sh logs

api: ## Run the API locally on http://127.0.0.1:8010
	$(UV) run uvicorn firebrief.api.dev:app --reload --port 8010

web: ## Run the web UI locally on http://127.0.0.1:5173 (proxies /v1 to :8010)
	cd web && npm run dev

web-test: ## Type-check and test the web UI
	cd web && npm run typecheck && npm test

eval-retrieval: ## Recall@3 on the retrieval evaluation set
	$(UV) run pytest tests/db/test_recall.py -q -s

db-migrate: ## Apply migrations to DATABASE_URL
	$(UV) run alembic upgrade head

db-roundtrip: ## up -> down -> up, then a model drift check
	$(UV) run alembic upgrade head
	$(UV) run alembic downgrade base
	$(UV) run alembic upgrade head
	$(UV) run alembic check

up: ## Start local Postgres and Redis
	docker compose up -d --wait

down: ## Stop local services and delete their volumes
	docker compose down -v

docker-smoke: ## Build the image, prove it imports, prove it is not root
	docker build --tag firebrief:local .
	docker run --rm firebrief:local
	docker run --rm --entrypoint id firebrief:local

clean: ## Remove caches
	rm -rf .pytest_cache .ruff_cache .uv-cache .hypothesis
