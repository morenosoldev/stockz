# Recover-Bot

A backend service for identifying stock market recovery opportunities through systematic screening and scoring. Read-only analysis with pluggable strategy modules.

## 🎯 Project Status

**Phase**: Initial Development (Pre-MVP)
**Version**: 1.0.0-MVP (in development)
**Last Updated**: October 24, 2025

## 📚 Documentation

### For Humans
- **[CONSTITUTION.md](./CONSTITUTION.md)** - Project principles and values (WHY)
- **[SPECIFICATION.md](./SPECIFICATION.md)** - Requirements and scope (WHAT)
- **[PLAN.md](./PLAN.md)** - Technical architecture and design (HOW)
- **[TASKS.md](./TASKS.md)** - Implementation roadmap (WHEN/WHO)

### For AI Agents
- **[AGENTS.md](./AGENTS.md)** - Comprehensive guide for autonomous AI development
  - Project structure and conventions
  - Coding standards and interfaces
  - Common workflows and commands
  - Troubleshooting guide

## 🚀 Quick Start

### Prerequisites
- **Python 3.11+** (Python 3.13 recommended)
- **Docker & Docker Compose** (for PostgreSQL)
- **VS Code** (recommended for one-click development)
- **Git** (for pre-commit hooks)

### Installation

1. **Clone the repository** (if not already done):
   ```bash
   git clone https://github.com/your-org/recover-bot.git
   cd recover-bot
   ```

2. **Create virtual environment** (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install the project**:
   ```bash
   # Install with all dependencies
   pip install -e ".[dev]"

   # Or use the Makefile
   make install
   ```

4. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

5. **Install pre-commit hooks**:
   ```bash
   pre-commit install
   ```

6. **Start PostgreSQL**:
   ```bash
   make db-up
   ```

7. **Run database migrations**:
   ```bash
   make db-migrate
   ```

8. **Verify installation**:
   ```bash
   # Test imports
   python -c "import fastapi; import sqlalchemy; print('✅ OK')"

   # Run tests
   make test
   ```

### VS Code One-Click Development

If you're using **VS Code**, you can launch the entire stack with one keystroke:

1. **Open the project in VS Code**
2. **Press F5** (or click Debug > Start Debugging)
3. This will:
   - Start PostgreSQL container
   - Run database migrations
   - Launch FastAPI with debugger attached
4. **API available at**: http://localhost:8000
5. **Swagger docs**: http://localhost:8000/docs

**Keyboard Shortcuts:**
- **F5** - Start debugging (Full Stack)
- **Shift+F5** - Stop debugging
- **Ctrl+Shift+F5** - Restart debugging
- **Ctrl+Shift+B** - Run build task (Start Full Stack)

**Available VS Code Tasks** (Terminal > Run Task):
- `Start PostgreSQL` - Launch database container
- `Stop PostgreSQL` - Stop database container
- `Run Migrations` - Apply database migrations
- `Start Dev Server` - Run FastAPI with hot-reload
- `Run Tests` - Execute test suite
- `Run Tests with Coverage` - Tests + coverage report
- `Lint Code` - Run ruff and mypy
- `Format Code` - Run black and ruff
- `One-Shot Scan` - Trigger manual scan
- `Backfill Data` - Run historical backfill
- `Start Full Stack` - PostgreSQL + Migrations (sequential)

### Manual Development

If not using VS Code, use the Makefile:

```bash
# Start development server
make dev

# Run tests
make test

# Lint and format
make lint
make format

# View all commands
make help
```

### First Scan

Trigger a scan via API:
```bash
# Trigger a scan
curl -X POST http://localhost:8000/v1/scan \
  -H "Content-Type: application/json" \
  -d '{"strategies": ["drop5"]}'

# View candidates
curl "http://localhost:8000/v1/candidates?date=2025-10-24"
```

Or use the one-shot script:
```bash
python scripts/one_shot_scan.py --date 2025-10-24 --strategy drop5
```

## 🏗️ Tech Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI
- **Database**: PostgreSQL 15+ with SQLAlchemy 2.0
- **Scheduler**: APScheduler
- **Config**: Pydantic Settings

## 🎨 Core Principles

1. **Facts-First Data** - All data attributed, never invented
2. **Reproducibility** - Versioned data, features, and models
3. **Safety** - Read-only mode, no trading in v1
4. **Observability** - Structured logs and metrics
5. **Modularity** - Pluggable strategy folders
6. **Performance** - <10min scans for 1-2k tickers
7. **Simplicity First** - Rules-based MVP, ML later

## 📖 Development with Spec Kit

This project is set up to use [Spec Kit](https://github.com/github/spec-kit) for spec-driven development in GitHub Codespaces.

### Getting Started

1. Open this repository in GitHub Codespaces
2. Wait for the dev container to build and initialize (this will install Spec Kit CLI and dependencies)
3. Use the Spec Kit slash commands in GitHub Copilot Chat to drive development:
   - `/speckit.constitution` - Create project principles ✅
   - `/speckit.specify` - Define what to build ✅
   - `/speckit.plan` - Create technical plan ✅
   - `/speckit.tasks` - Break down into tasks ✅
   - `/speckit.implement` - Start implementation ⏭️

### Spec Kit CLI

You can also use the `specify` CLI directly:

```bash
# Initialize a new spec-kit project
specify init <PROJECT_NAME>

# Check your specifications
specify check
```

For more information about Spec Kit, visit the [official documentation](https://github.github.io/spec-kit/).

## 🛠️ Available Commands

```bash
make help         # Show all available commands
make install      # Install dependencies
make dev          # Start dev server
make db-up        # Start PostgreSQL
make db-migrate   # Run migrations
make scan         # Run one-shot scan
make test         # Run tests
make lint         # Run linters
```

See [AGENTS.md](./AGENTS.md) for complete command reference.

## 📁 Project Structure

```
src/
├── api/          # FastAPI application
├── scheduler/    # APScheduler cron jobs
├── strategies/   # Pluggable strategy modules
├── datasources/  # Data adapters (prices, news)
├── features/     # Feature engineering
├── scanner/      # Core scanning engine
├── storage/      # Database models & migrations
├── eval/         # Evaluation & backtesting
└── ops/          # Config, logging, utilities
```

See [AGENTS.md](./AGENTS.md) for detailed structure.

## 🔌 Adding a New Strategy

1. Create folder: `src/strategies/my_strategy/`
2. Add `implementation.py` with strategy class
3. Add `config.yml` with parameters
4. Restart service - auto-discovered!

See [AGENTS.md](./AGENTS.md#adding-a-new-strategy) for detailed guide.

## 📊 API Endpoints

- `GET /health` - Health check
- `POST /v1/scan` - Trigger scan
- `GET /v1/candidates` - List candidates
- `GET /v1/candidate/{ticker}/{asof}` - Candidate detail
- `GET /v1/runs/{date}` - Run metadata
- `GET /v1/metrics` - Performance metrics

API documentation available at: http://localhost:8000/docs

## 🧪 Testing

```bash
make test          # Run all tests
make test-cov      # Run with coverage
pytest tests/unit/ # Run unit tests only
```

## 🤝 Contributing

This is a spec-driven project. Before contributing:
1. Read [CONSTITUTION.md](./CONSTITUTION.md) for principles
2. Review [SPECIFICATION.md](./SPECIFICATION.md) for scope
3. Check [TASKS.md](./TASKS.md) for current work
4. Follow conventions in [AGENTS.md](./AGENTS.md)

## 📄 License

[Add your license here]

## 🔗 Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 Docs](https://docs.sqlalchemy.org/)
- [Spec Kit Documentation](https://github.github.io/spec-kit/)

---

**Next Steps**: Start with Task 1.1 in [TASKS.md](./TASKS.md) or use `/speckit.implement` to begin!
