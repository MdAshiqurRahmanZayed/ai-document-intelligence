.PHONY: help up dev down logs migrate flower test e2e bench lint check eval eval-report

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

flower: ## Start the Flower worker dashboard (login from FLOWER_USER / FLOWER_PASSWORD in .env)
	docker compose --profile monitoring up -d flower
	@echo "Flower: http://localhost:$${FLOWER_PORT:-5555}"

test: ## Run backend and frontend tests (in Docker)
	@docker compose --profile test run --build --rm backend-test sh -c "pytest && pytest /eval/tests"; status=$$?; \
	docker compose --profile test rm -sf postgres-test >/dev/null 2>&1; \
	[ $$status -eq 0 ] || exit $$status
	docker compose --profile test run --build --rm web-test

e2e: ## Browser journey against the running stack (run make up first; needs Node, installs Chromium once)
	cd frontend && npm install --no-audit --no-fund && npx playwright install chromium && npx playwright test

bench: ## Run the slow large-document benchmarks (in Docker)
	@docker compose --profile test run --build --rm backend-test pytest -m slow -s; status=$$?; \
	docker compose --profile test rm -sf postgres-test >/dev/null 2>&1; \
	exit $$status

lint: ## Lint and typecheck backend and frontend (in Docker)
	docker compose --profile test run --build --no-deps --rm backend-test sh -c "ruff check . && ruff format --check . && mypy app tests && ruff check --config pyproject.toml /eval && ruff format --check --config pyproject.toml /eval"
	docker compose --profile test run --build --rm web-test sh -c "npm run lint && npm run typecheck"

check: ## Lint, typecheck and test everything (in Docker): one build and one database start per side
	@docker compose --profile test run --build --rm backend-test sh -c "ruff check . && ruff format --check . && mypy app tests && ruff check --config pyproject.toml /eval && ruff format --check --config pyproject.toml /eval && pytest && pytest /eval/tests"; status=$$?; \
	docker compose --profile test rm -sf postgres-test >/dev/null 2>&1; \
	[ $$status -eq 0 ] || exit $$status
	docker compose --profile test run --build --rm web-test sh -c "npm run lint && npm run typecheck && npm test"

eval: ## Evaluate on the labelled dataset (stack up, empty DB, GOOGLE_API_KEY set; ARGS="--only pdf --resume")
	@test -d eval/dataset/documents || (cd backend && uv run python ../eval/build_dataset.py)
	cd backend && uv run python ../eval/run_eval.py $(ARGS)

eval-report: ## Rebuild eval/results/report.md from results.json (no stack or key needed)
	cd backend && uv run python ../eval/run_eval.py --rescore
