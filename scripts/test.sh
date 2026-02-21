#!/bin/bash
# A robust test runner script inspired by well-established Python patterns.
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# Check if we are in a virtual environment
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo -e "${RED}Warning: Not running in a virtual environment. Please run 'source .venv/bin/activate' first.${NC}"
fi

echo -e "${BLUE}1. Running Formatting Check (Ruff Format)...${NC}"
ruff format --check .

echo -e "\n${BLUE}2. Running Lint Checks (Ruff)...${NC}"
ruff check .

echo -e "\n${BLUE}3. Running Type Checks (Mypy)...${NC}"
mypy .

echo -e "\n${BLUE}4. Running Tests (Pytest)...${NC}"
# Suppress LangSmith tracing to avoid "I/O operation on closed file" errors during shutdown
export LANGSMITH_TRACING_V2=false

# Pass all arguments from the script call directly to pytest (e.g., ./scripts/test.sh tests/integration/test_api_chat.py)
# If no arguments are passed, it runs all tests defined in pyproject.toml
if [ $# -eq 0 ]; then
    pytest -ra
    echo -e "\n${BLUE}5. Running Frontend Tests (Vitest)...${NC}"
    cd frontend && npm run test && cd ..
else
    pytest -ra "$@"
fi

echo -e "\n${GREEN}✨ All checks passed!${NC}"
