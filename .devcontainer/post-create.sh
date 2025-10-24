#!/bin/bash

# Exit immediately on error, treat unset variables as an error, and fail if any command in a pipeline fails.
set -euo pipefail

# Function to run a command and show logs only on error
run_command() {
    local command_to_run="$*"
    local output
    local exit_code
    
    # Capture all output (stdout and stderr)
    output=$(eval "$command_to_run" 2>&1) || exit_code=$?
    exit_code=${exit_code:-0}
    
    if [ $exit_code -ne 0 ]; then
        echo -e "\033[0;31m[ERROR] Command failed (Exit Code $exit_code): $command_to_run\033[0m" >&2
        echo -e "\033[0;31m$output\033[0m" >&2
        
        exit $exit_code
    fi
}

echo -e "\n🚀 Setting up Stockz development environment with Spec Kit...\n"

# Installing UV (Python package manager)
echo -e "🐍 Installing UV - Python Package Manager..."
run_command "pipx install uv"
echo "✅ Done"

# Installing Spec Kit CLI
echo -e "\n📦 Installing Spec Kit CLI..."
run_command "uv tool install specify-cli --from git+https://github.com/github/spec-kit.git"
echo "✅ Done"

# Installing Copilot CLI (primary agent for this project)
echo -e "\n🤖 Installing GitHub Copilot CLI..."
run_command "npm install -g @github/copilot@latest"
echo "✅ Done"

echo -e "\n🧹 Cleaning cache..."
run_command "sudo apt-get autoclean"
run_command "sudo apt-get clean"

echo -e "\n✅ Setup completed. Your Codespace is ready to use Spec Kit! 🚀"
echo -e "\nYou can now use the following commands:"
echo -e "  - specify init <PROJECT_NAME>  : Initialize a new spec-kit project"
echo -e "  - specify check                 : Check your specifications"
echo -e "\nOr use the /speckit.* slash commands in GitHub Copilot Chat:"
echo -e "  - /speckit.constitution         : Create project principles"
echo -e "  - /speckit.specify              : Define what to build"
echo -e "  - /speckit.plan                 : Create technical plan"
echo -e "  - /speckit.tasks                : Break down into tasks"
echo -e "  - /speckit.implement            : Start implementation"
