#!/bin/bash

echo "Cleaning up CVviewer project..."

# 1. Stop Docker containers & remove volumes
if command -v docker-compose &> /dev/null && docker info &> /dev/null; then
    echo "Stopping Docker containers & removing volumes..."
    docker-compose down -v 2>/dev/null || true
fi

# 2. Free up active ports
echo "Cleaning ports 8000 and 3000..."
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:3000 | xargs kill -9 2>/dev/null || true

# 3. Clean Python build & test caches (preserves .venv so git pre-commit hooks remain intact)
echo "Removing Python cache directories..."
rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true

# 4. Clean Frontend build artifacts (preserves node_modules)
echo "Removing Next.js build cache..."
rm -rf frontend/.next

# 5. Clean runtime state logs & local temp files
echo "Removing runtime logs & temporary state files..."
rm -f data/state_debug.log
rm -f data/agent_telemetry.jsonl
rm -f /tmp/cvviewer_state_debug.log

echo "Full cleanup complete."
