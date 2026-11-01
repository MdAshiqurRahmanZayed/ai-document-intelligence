.PHONY: help up dev down logs migrate test lint eval

help: ## List targets
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

up: ## Build and start the stack, wait until healthy
	docker compose up -d --build --wait

dev: ## Build and start in the foreground with live logs (Ctrl+C stops)
	docker compose up --build

down: ## Stop the stack (data volumes are kept)
	docker compose down

logs: ## Follow service logs
	docker compose logs -f --tail=100

migrate: ## Apply database migrations
	docker compose exec api alembic upgrade head

test: ## Run backend and frontend tests (in Docker)
	docker compose --profile test run --build --rm backend-test
	docker compose --profile test run --build --rm web-test

lint: ## Lint and typecheck backend and frontend (in Docker)
	docker compose --profile test run --build --rm backend-test sh -c "ruff check . && ruff format --check . && mypy app tests"
	docker compose --profile test run --build --rm web-test sh -c "npm run lint && npm run typecheck"

eval: ## Run the evaluation harness (added in Phase 6)
	@echo "Evaluation harness is not implemented yet (Phase 6)."
