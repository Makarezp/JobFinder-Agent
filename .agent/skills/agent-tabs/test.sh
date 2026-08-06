#!/bin/sh
# Self-contained gate for agentctl.
#
# The tool travels as one directory into any repository, so this must not assume
# a virtualenv, a pyproject.toml, or a host project's test runner. Only pytest is
# required; lint and type checks run when their tools happen to be available and
# are reported as skipped when they are not.
#
# POSIX sh on purpose: macOS ships bash 3.2.
#
#   ./test.sh              run everything
#   ./test.sh -k predicate pass arguments through to pytest
set -e

DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PY=${AGENTCTL_PYTHON:-python3}

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m'

have() { "$PY" -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('$1') else 1)" 2>/dev/null; }
say() { printf "%b\n" "$1"; }

say "${BLUE}Interpreter${NC}"
"$PY" "$DIR/agentctl.py" --version
"$PY" -c 'import sys; print("python", ".".join(map(str, sys.version_info[:3])))'

if have ruff; then
    say "\n${BLUE}Lint (ruff)${NC}"
    "$PY" -m ruff check "$DIR"
    "$PY" -m ruff format --check "$DIR"
else
    say "\n${YELLOW}Skipping lint — ruff not available.${NC}"
fi

if have mypy; then
    say "\n${BLUE}Types (mypy --strict)${NC}"
    "$PY" -m mypy --strict "$DIR"
else
    say "\n${YELLOW}Skipping type checks — mypy not available.${NC}"
fi

if ! have pytest; then
    say "\n${YELLOW}pytest is not available; cannot run the suite.${NC}"
    exit 1
fi

say "\n${BLUE}Tests (pytest)${NC}"
"$PY" -m pytest "$DIR/tests" -ra "$@"

if ! command -v tmux > /dev/null 2>&1; then
    say "${YELLOW}Note: tmux is not installed — the tmux-backed tests reported as skipped.${NC}"
fi
if [ "${AGENT_TABS_E2E:-}" != "1" ]; then
    say "${YELLOW}Note: set AGENT_TABS_E2E=1 (with tmux and a worker binary) to include the live end-to-end test.${NC}"
fi

say "\n${GREEN}All checks passed.${NC}"
