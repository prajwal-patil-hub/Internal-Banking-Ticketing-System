# SUCCESS Bank — developer convenience targets.
# All commands run from the repo root.
COMPOSE := docker compose -f infra/docker-compose.yml
COMPOSE_PROD := docker compose -f infra/docker-compose.prod.yml

.PHONY: help up down restart logs ps build rebuild backend-shell frontend-shell \
        migrate migrate-down seed test typecheck lint fmt clean prod-build prod-up

help:
	@echo "Targets:"
	@echo "  up              Start dev stack (postgres, redis, minio, backend, frontend)"
	@echo "  down            Stop dev stack"
	@echo "  restart         Restart dev stack"
	@echo "  logs            Tail backend logs"
	@echo "  ps              List running containers"
	@echo "  build           docker compose build"
	@echo "  rebuild         build with --no-cache"
	@echo "  backend-shell   Open a shell inside the backend container"
	@echo "  migrate         Apply Alembic migrations"
	@echo "  migrate-down    Rollback one Alembic migration"
	@echo "  seed            Seed roles, permissions, demo data"
	@echo "  test            Run backend pytest suite"
	@echo "  typecheck       Run frontend tsc --noEmit"
	@echo "  lint            Run ruff for backend"
	@echo "  fmt             Run ruff --fix"
	@echo "  prod-build      Build production images"
	@echo "  prod-up         Start production-style stack (nginx in front)"

up:
	$(COMPOSE) up -d
	@echo "Frontend: http://localhost:5173"
	@echo "Backend : http://localhost:8000/api/docs"
	@echo "MinIO   : http://localhost:9001"

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

logs:
	$(COMPOSE) logs -f backend

ps:
	$(COMPOSE) ps

build:
	$(COMPOSE) build

rebuild:
	$(COMPOSE) build --no-cache

backend-shell:
	$(COMPOSE) exec backend bash

frontend-shell:
	$(COMPOSE) exec frontend sh

migrate:
	$(COMPOSE) exec backend alembic upgrade head

migrate-down:
	$(COMPOSE) exec backend alembic downgrade -1

seed:
	$(COMPOSE) exec backend python -m app.db.seed

test:
	$(COMPOSE) exec backend pytest -q

typecheck:
	$(COMPOSE) exec frontend npm run typecheck

lint:
	$(COMPOSE) exec backend ruff check .

fmt:
	$(COMPOSE) exec backend ruff check --fix .

prod-build:
	$(COMPOSE_PROD) build

prod-up:
	$(COMPOSE_PROD) up -d

clean:
	$(COMPOSE) down -v
