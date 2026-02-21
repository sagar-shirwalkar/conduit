#!/usr/bin/env bash
set -euo pipefail

echo "Conduit Development Setup"
echo "=============================="

# Check Python version
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✓ Python version: $PYTHON_VERSION"

if [[ "$PYTHON_VERSION" < "3.12" ]]; then
    echo "Python 3.12+ is required"
    exit 1
fi

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Installing dependencies..."
pip install -e ".[dev]" --quiet

echo "Starting Docker services (PostgreSQL + Redis)..."
docker compose -f docker/docker-compose.yml up -d postgres redis

echo "→ Waiting for PostgreSQL..."
sleep 3

echo "Running database migrations..."
alembic upgrade head

echo ""
echo "Setup complete! Start the dev server with:"
echo "   source .venv/bin/activate"
echo "   make dev"
echo ""