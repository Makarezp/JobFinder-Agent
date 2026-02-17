#!/bin/bash

# Ensure PostgreSQL is running
echo "🐘 Starting PostgreSQL..."
docker-compose up -d

# Wait for database to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
until docker-compose exec -T db pg_isready -U postgres > /dev/null 2>&1; do
  echo -n "."
  sleep 1
done
echo -e "\n✅ PostgreSQL is ready!"

# Check if .venv exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment (.venv) not found. Please run 'python3 -m venv .venv' first."
    exit 1
fi

# Free up port 8000 if it is already in use
echo "🧹 Cleaning up port 8000..."
lsof -ti:8000 | xargs kill -9 2>/dev/null

# Activate venv and run server
echo "🚀 Starting FastAPI server..."
source .venv/bin/activate
uvicorn app.main:app --reload
