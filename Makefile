.PHONY: dev-up dev-down db-upgrade db-downgrade db-revision db-init engine-seed engine-tick engine-run

dev-up:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

dev-down:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml down

COMPOSE_RUN = docker compose run --rm -v "$(CURDIR):/app" api

db-upgrade:
	$(COMPOSE_RUN) alembic -c /app/server/api/alembic.ini upgrade head

db-downgrade:
	$(COMPOSE_RUN) alembic -c /app/server/api/alembic.ini downgrade -1

db-revision:
	@if [ -z "$(MSG)" ]; then echo 'MSG is required. Usage: make db-revision MSG="your message"'; exit 1; fi
	$(COMPOSE_RUN) alembic -c /app/server/api/alembic.ini revision --autogenerate -m "$(MSG)"

db-init: db-upgrade

engine-seed:
	docker compose run --rm data-engine seed

engine-tick:
	docker compose run --rm data-engine tick

engine-run:
	docker compose --profile simulation up data-engine
