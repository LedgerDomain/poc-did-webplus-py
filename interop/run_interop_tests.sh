#!/usr/bin/env bash
# Run interoperability tests for did:webplus
# Usage: ./run_interop_tests.sh <1-16>
#
# 16 scenarios from 4 axes: Controller (Python/Rust), VDR (Python/Rust),
# Resolver (Python/Rust), VDG (no/yes).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SCENARIO="${1:-}"
if [[ -z "$SCENARIO" || ! "$SCENARIO" =~ ^(1[0-6]|[1-9])$ ]]; then
    echo "Usage: $0 <1-16>"
    echo ""
    echo "Scenarios: 4 axes — Controller, VDR, Resolver (Python/Rust each), VDG (no/yes)."
    exit 1
fi

# Docker compose command
if command -v docker &>/dev/null; then
    if docker compose version &>/dev/null; then
        COMPOSE="docker compose"
    elif docker-compose version &>/dev/null; then
        COMPOSE="docker-compose"
    else
        echo "Error: docker compose or docker-compose required"
        exit 1
    fi
else
    echo "Error: docker required"
    exit 1
fi

echo "=== Scenario $SCENARIO ==="

# Ensure clean slate: stop any existing containers and remove volumes
echo "Ensuring clean slate..."
bash "$SCRIPT_DIR/stop_and_clean.sh"

# Derive VDR and VDG from scenario number (same mapping as run_interop_tests.py)
# (n-1) & 1 -> use_vdg, (n-1) & 4 -> vdr_rust
USE_VDG=$(( (SCENARIO - 1) & 1 ))
VDR_RUST=$(( ((SCENARIO - 1) & 4) != 0 ))

if [[ $VDR_RUST -eq 1 ]]; then
    if [[ $USE_VDG -eq 1 ]]; then
        echo "Starting Rust VDR + VDG..."
        RUST_VDR_VDG_HOSTS=rust-vdg:8086 $COMPOSE up -d rust-vdr-db rust-vdg-db rust-vdg rust-vdr
    else
        echo "Starting Rust VDR..."
        RUST_VDR_VDG_HOSTS= $COMPOSE up -d rust-vdr-db rust-vdr
    fi
else
    if [[ $USE_VDG -eq 1 ]]; then
        echo "Starting Python VDR + Rust VDG..."
        PYTHON_VDR_VDG_HOSTS=rust-vdg:8086 $COMPOSE up -d --build rust-vdg-db rust-vdg python-vdr
    else
        echo "Starting Python VDR..."
        $COMPOSE up -d --build python-vdr
    fi
fi

echo "Streaming Docker service logs (background)..."
$COMPOSE logs -f &
LOG_PID=$!

echo "Waiting for services to be healthy..."
sleep 3

# Stop containers on exit (volumes left intact for inspection on failure)
EXIT_CODE=1
cleanup() {
    kill "$LOG_PID" 2>/dev/null || true
    cd "$SCRIPT_DIR"
    $COMPOSE down
    exit "$EXIT_CODE"
}
trap cleanup EXIT

# Run Python test script
cd "$SCRIPT_DIR/.."
uv run python interop/run_interop_tests.py "$SCENARIO"
EXIT_CODE=$?
