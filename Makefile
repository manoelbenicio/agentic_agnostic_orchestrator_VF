.PHONY: help dev stop test lint format build migrate clean docs logs

help: ## Show this help message mapping target commands
	@echo "🪐 Agnostic Orchestration Platform (AOP) - Developer Console"
	@echo ""
	@echo "Available Execution Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

dev: ## Boot the entire monolithic cluster natively utilizing Docker Compose
	docker-compose up --build -d

stop: ## Gracefully sever TCP sockets and tear down the active cluster
	docker-compose down

test: ## Execute deep Pytest assertions strictly inside the control-plane context
	cd control-plane && poetry run pytest

lint: ## Execute strict Ruff AST validation bounds across backend modules
	cd control-plane && poetry run ruff check .
	cd agnostic-ai-platform && poetry run ruff check .

format: ## Execute Ruff geometric auto-formatter overwriting bad AST logic safely
	cd control-plane && poetry run ruff format .
	cd agnostic-ai-platform && poetry run ruff format .

build: ## Force rebuild Docker layer architectures completely ignoring cached payloads
	docker-compose build --no-cache

migrate: ## Trigger Alembic Postgres migrations executing cleanly inside the running container bounds
	docker-compose exec control-plane poetry run python -m app.migration.migrator upgrade

clean: ## Recursively annihilate massive cache bloat preventing stale executions natively
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	@echo "Workspace Cache geometries successfully obliterated."

docs: ## Programmatically extract the FastAPI OpenAPI spec mapping to JSON bounds
	cd control-plane && poetry run python -c "import json; from app.main_consolidated import app; print(json.dumps(app.openapi(), indent=2))" > openapi.json
	@echo "API Swagger JSON geometry successfully extracted to control-plane/openapi.json"

logs: ## Attach a streaming TCP tail mapping dynamically to cluster outputs
	docker-compose logs -f
