#!/bin/bash

# Trap Ctrl+C (SIGINT) and SIGTERM to kill all background child processes cleanly
cleanup() {
  echo -e "\n🛑 Stopping backend and frontend services..."
  kill $(jobs -p) 2>/dev/null || true
  exit 0
}
trap cleanup EXIT INT TERM

# Check or auto-create Python virtual environment
if [ ! -d ".venv" ]; then
    echo "⚙️ Creating virtual environment (.venv)..."
    python3 -m venv .venv
    echo "📦 Installing backend dependencies & pre-commit..."
    source .venv/bin/activate
    pip install pyyaml pre-commit -e ".[dev]"
    pre-commit install 2>/dev/null || true
else
    source .venv/bin/activate
fi

# Check or auto-install frontend dependencies
if [ ! -d "frontend/node_modules" ]; then
    echo "📦 Installing frontend dependencies..."
    (cd frontend && npm install)
fi

# Try starting PostgreSQL if Docker is running
if command -v docker-compose &> /dev/null && docker info &> /dev/null; then
    echo "🐘 Starting PostgreSQL..."
    docker-compose up -d 2>/dev/null || true
fi

# Free up ports 8000 and 3000 if already in use
echo "🧹 Cleaning up ports 8000 and 3000..."
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:3000 | xargs kill -9 2>/dev/null || true

# Activate venv and start FastAPI backend
echo "🚀 Starting Backend (FastAPI on http://localhost:8000)..."
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

# Start Next.js frontend
echo "🎨 Starting Frontend (Next.js on http://localhost:3000)..."
(cd frontend && npm run dev) &
FRONTEND_PID=$!

echo -e "\n✅ Backend (port 8000) and Frontend (port 3000) are starting!"
echo "💡 Press Ctrl+C at any time to stop all services."

# Wait for background processes
wait
