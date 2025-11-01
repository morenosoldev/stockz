
.PHONY: help install dev db-up db-down db-migrate db-reset scan backfill test test-cov lint format type-check clean



# Detect Windows using uname (works for Git Bash/MINGW)
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Linux)
	VENV_BIN=.venv/bin
else ifeq ($(UNAME_S),Darwin)
	VENV_BIN=.venv/bin
else
	VENV_BIN=.venv/Scripts
endif

# Default target
.DEFAULT_GOAL := help

help: ## Show this help message
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'


install: ## Install dependencies
	$(VENV_BIN)/pip install -e ".[dev]"
	$(VENV_BIN)/pre-commit install || true


dev: ## Start FastAPI development server
	$(VENV_BIN)/uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

db-up: ## Start PostgreSQL container
	docker compose up -d postgres
	@echo "Waiting for PostgreSQL to be ready..."
	@sleep 3

db-down: ## Stop PostgreSQL container
	docker compose down


db-migrate: ## Run Alembic migrations
	$(VENV_BIN)/alembic upgrade head


db-reset: ## Reset database (destructive!)
   @echo "⚠️  WARNING: This will delete all data!"
   @read -p "Are you sure? [y/N] " -n 1 -r; \
   echo; \
   if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
	   docker compose down -v; \
	   docker compose up -d postgres; \
	   sleep 3; \
	   $(VENV_BIN)/alembic upgrade head; \
	   echo "✅ Database reset complete"; \
   fi


scan: ## Run one-shot scan
	$(VENV_BIN)/python scripts/one_shot_scan.py


backfill: ## Run backfill for historical data (default: 30 days)
	$(VENV_BIN)/python scripts/backfill.py --days 30


test: ## Run test suite
	$(VENV_BIN)/pytest tests/ -v


test-cov: ## Run tests with coverage report
	$(VENV_BIN)/pytest --cov=src --cov-report=term-missing --cov-report=html tests/
	@echo "Coverage report generated in htmlcov/index.html"


lint: ## Run linters (ruff, mypy)
	$(VENV_BIN)/ruff check src/ tests/
	$(VENV_BIN)/mypy src/


format: ## Format code (black, ruff)
	$(VENV_BIN)/black src/ tests/ scripts/
	$(VENV_BIN)/ruff check --fix src/ tests/ scripts/


type-check: ## Run type checker (mypy)
	$(VENV_BIN)/mypy src/

clean: ## Clean temporary files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf htmlcov/ .coverage 2>/dev/null || true
	@echo "✅ Cleaned temporary files"

docker-build: ## Build Docker image
	docker build -f docker/Dockerfile -t recover-bot:latest .

docker-run: ## Run Docker container
	docker compose up

setup: db-up db-migrate ## Complete setup (database + migrations)
	@echo "✅ Setup complete! Run 'make dev' to start the server"
