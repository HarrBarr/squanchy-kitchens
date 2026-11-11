# Every target shells out to `docker compose`, so only Docker is needed on the host.
.PHONY: up up-empty dev down seed-demo test test-backend test-frontend lint fmt reset-db logs

COMPOSE = docker compose
DEV = $(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml

up:              ## Demo mode on http://localhost:8080
	$(COMPOSE) up --build

up-empty:        ## Demo mode without the mock week (upload files yourself)
	SEED_DEMO_DATA=false $(COMPOSE) up --build

dev:             ## Hot-reload dev mode on http://localhost:4200
	$(DEV) up --build

down:
	$(COMPOSE) down

seed-demo:       ## Import the mock week into a running stack (idempotent)
	$(COMPOSE) exec api python -m app.bootstrap --demo

test: test-backend test-frontend

test-backend:    ## Parser, rules, golden oracle and API tests against a throwaway MySQL schema
	$(COMPOSE) run --rm api pytest

test-frontend:   ## Angular unit tests (Vitest) in the Node dev image
	$(DEV) run --rm --no-deps web npx ng test --watch=false

lint:
	$(COMPOSE) run --rm --no-deps api sh -c "ruff check app tests && ruff format --check app tests && mypy app"
	$(DEV) run --rm --no-deps web npx prettier --check "src/**/*.{ts,html,scss}"

fmt:
	$(COMPOSE) run --rm --no-deps -v ./backend:/app api sh -c "ruff check --fix app tests && ruff format app tests"
	$(DEV) run --rm --no-deps web npx prettier --write "src/**/*.{ts,html,scss}"

reset-db:        ## Wipe MySQL and stored uploads, then start again (deletes data)
	$(COMPOSE) down -v
	$(COMPOSE) up --build

logs:
	$(COMPOSE) logs -f api
