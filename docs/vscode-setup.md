# VS Code Configuration Guide

**Status**: Template for Task 1.1 implementation  
**Purpose**: Guide for setting up VS Code workspace for one-click development

---

## Files to Create

### 1. `.vscode/tasks.json`

Provides tasks that can be run via `Terminal > Run Task...` or keyboard shortcuts.

**Required Tasks**:
- **Start PostgreSQL** - Run `docker-compose up -d postgres`
- **Stop PostgreSQL** - Run `docker-compose down`
- **Run Migrations** - Run `alembic upgrade head`
- **Start Dev Server** - Run `uvicorn src.api.main:app --reload`
- **Run Tests** - Run `pytest tests/`
- **Run Tests with Coverage** - Run `pytest --cov=src tests/`
- **Lint Code** - Run `ruff check src/ && mypy src/`
- **Format Code** - Run `black src/ tests/ && ruff check --fix src/`
- **One-Shot Scan** - Run `python scripts/one_shot_scan.py`
- **Backfill Data** - Run `python scripts/backfill.py`

**Example Task Structure**:
```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Start PostgreSQL",
      "type": "shell",
      "command": "docker-compose up -d postgres",
      "problemMatcher": [],
      "group": "build"
    },
    {
      "label": "Start Dev Server",
      "type": "shell",
      "command": "uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000",
      "problemMatcher": [],
      "group": {
        "kind": "build",
        "isDefault": true
      },
      "isBackground": true
    }
  ]
}
```

---

### 2. `.vscode/launch.json`

Provides debug configurations accessible via `Run and Debug` panel or **F5**.

**Required Configurations**:
- **FastAPI: Debug Server** - Debug the main FastAPI application
- **FastAPI: Full Stack** - Compound: Start DB + Migrate + Debug Server
- **Python: Current File** - Debug the currently open Python file
- **Python: Run Script** - Debug scripts with arguments
- **Python: Debug Tests** - Debug pytest tests
- **Python: Attach** - Attach to running process

**Example Launch Configuration**:
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "FastAPI: Debug Server",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "src.api.main:app",
        "--reload",
        "--host",
        "0.0.0.0",
        "--port",
        "8000"
      ],
      "jinja": true,
      "justMyCode": false,
      "env": {
        "DATABASE_URL": "${env:DATABASE_URL}"
      }
    },
    {
      "name": "Python: Current File",
      "type": "python",
      "request": "launch",
      "program": "${file}",
      "console": "integratedTerminal",
      "justMyCode": false
    },
    {
      "name": "Python: Debug Tests",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": [
        "${file}",
        "-v"
      ],
      "console": "integratedTerminal",
      "justMyCode": false
    }
  ],
  "compounds": [
    {
      "name": "FastAPI: Full Stack",
      "configurations": [],
      "preLaunchTask": "Start Full Stack",
      "stopAll": true
    }
  ]
}
```

**Note**: The compound configuration requires a `preLaunchTask` that:
1. Starts PostgreSQL (if not running)
2. Runs migrations
3. Then launches the FastAPI server with debugger

---

### 3. `.vscode/settings.json`

Workspace-specific settings for Python development.

**Required Settings**:
```json
{
  // Python
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.envFile": "${workspaceFolder}/.env",

  // Formatting
  "python.formatting.provider": "black",
  "python.formatting.blackArgs": ["--line-length", "100"],
  "[python]": {
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.organizeImports": true
    },
    "editor.defaultFormatter": "ms-python.black-formatter"
  },

  // Linting
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.linting.mypyEnabled": true,
  "python.linting.lintOnSave": true,

  // Testing
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false,
  "python.testing.pytestArgs": [
    "tests"
  ],

  // File associations
  "files.associations": {
    "*.yml": "yaml",
    "*.yaml": "yaml"
  },

  // Editor
  "editor.rulers": [100],
  "files.trimTrailingWhitespace": true,
  "files.insertFinalNewline": true,

  // Exclusions
  "files.exclude": {
    "**/__pycache__": true,
    "**/*.pyc": true,
    "**/.pytest_cache": true,
    "**/.mypy_cache": true,
    "**/.ruff_cache": true
  }
}
```

---

### 4. `.vscode/extensions.json`

Recommended extensions for the workspace.

**Required Extensions**:
```json
{
  "recommendations": [
    "ms-python.python",
    "ms-python.vscode-pylance",
    "ms-python.black-formatter",
    "charliermarsh.ruff",
    "ms-azuretools.vscode-docker",
    "mtxr.sqltools",
    "mtxr.sqltools-driver-pg",
    "redhat.vscode-yaml",
    "ms-vscode.makefile-tools",
    "github.copilot",
    "tamasfe.even-better-toml"
  ]
}
```

---

## Compound Launch Strategy

The "one-click" experience should use a compound launch configuration with pre-launch tasks:

### Pre-Launch Task (`tasks.json`)
```json
{
  "label": "Start Full Stack",
  "dependsOrder": "sequence",
  "dependsOn": [
    "Ensure PostgreSQL Running",
    "Run Database Migrations"
  ],
  "problemMatcher": []
}
```

### Supporting Tasks
```json
{
  "label": "Ensure PostgreSQL Running",
  "type": "shell",
  "command": "docker-compose up -d postgres && sleep 3",
  "problemMatcher": []
},
{
  "label": "Run Database Migrations",
  "type": "shell",
  "command": "alembic upgrade head",
  "problemMatcher": []
}
```

### Compound Configuration (`launch.json`)
```json
{
  "name": "🚀 Full Stack (F5)",
  "configurations": ["FastAPI: Debug Server"],
  "preLaunchTask": "Start Full Stack",
  "stopAll": true,
  "presentation": {
    "hidden": false,
    "group": "",
    "order": 1
  }
}
```

---

## User Experience

After implementation, developers should be able to:

1. **Open Project in VS Code**
2. **Press F5** (or click "Run and Debug > 🚀 Full Stack")
3. **Automatically**:
   - PostgreSQL starts (if not running)
   - Database migrations run
   - FastAPI server starts with debugger attached
   - Browser opens to http://localhost:8000/docs
4. **Set breakpoints** and debug normally
5. **Press Shift+F5** to stop everything

---

## Keyboard Shortcuts to Document (in AGENTS.md)

After implementation, update AGENTS.md with:

- **F5** - Start debugging (launches full stack)
- **Shift+F5** - Stop debugging
- **Ctrl+Shift+B** (Cmd+Shift+B on Mac) - Run default build task (Start Dev Server)
- **Ctrl+Shift+P** > "Run Task" - Access all tasks
- **Ctrl+Shift+`** - Open integrated terminal

---

## Testing the Configuration

After creating all files, verify:

1. ✅ Recommended extensions prompt appears
2. ✅ F5 starts PostgreSQL, runs migrations, starts server
3. ✅ Breakpoints in FastAPI routes work
4. ✅ Tests can be run from Test Explorer
5. ✅ Format on save works (Black)
6. ✅ Linting shows errors inline (Ruff, Mypy)
7. ✅ All tasks appear in `Terminal > Run Task`

---

## Update AGENTS.md

After implementation, add section to AGENTS.md:

### VS Code Integration

**One-Click Development**:
```
Press F5 to start everything:
- PostgreSQL (via Docker)
- Database migrations
- FastAPI server with debugger attached
```

**Available Tasks** (Ctrl+Shift+P > Run Task):
- Start PostgreSQL
- Run Migrations
- Start Dev Server
- Run Tests
- Lint Code
- Format Code
- One-Shot Scan
- Backfill Data

**Debug Configurations**:
- FastAPI: Debug Server
- FastAPI: Full Stack (F5)
- Python: Current File
- Python: Debug Tests

**Keyboard Shortcuts**:
- **F5** - Start debugging (full stack)
- **Shift+F5** - Stop debugging
- **Ctrl+Shift+B** - Build task (start server)
- **Ctrl+Shift+`** - Toggle terminal

---

**Implementation**: See Task 1.1 in TASKS.md
