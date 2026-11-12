COMPOSE := docker compose
ARGS ?= common/tests

.PHONY: up down logs ps test migrate build lint

up:
	$(COMPOSE) up -d --build --remove-orphans

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=200 $(S)

ps:
	$(COMPOSE) ps

build:
	$(COMPOSE) build $(S)

test:
	$(COMPOSE) run --rm --build tools pytest -q $(ARGS)

lint:
	$(COMPOSE) run --rm tools ruff check common db services engines

migrate:
	$(COMPOSE) run --rm tools python db/migrate.py
