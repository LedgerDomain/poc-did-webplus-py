#!/usr/bin/env bash
# Run interoperability tests for did:webplus
# Usage: ./run_interop_tests.sh <1|2|3|4>
#
# Scenarios:
#   1: Python resolver vs Rust VDR (no VDG)
#   2: Python resolver vs Rust VDR + Rust VDG
#   3: Rust resolver vs Python VDR (no VDG)
#   4: Rust resolver vs Python VDR + Rust VDG

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SCENARIO="${1:-}"
if [[ -z "$SCENARIO" || ! "$SCENARIO" =~ ^[1-4]$ ]]; then
    echo "Usage: $0 <1|2|3|4>"
    echo ""
    echo "Scenarios:"
    echo "  1: Python resolver vs Rust VDR (no VDG)"
    echo "  2: Python resolver vs Rust VDR + Rust VDG"
    echo "  3: Rust resolver vs Python VDR (no VDG)"
    echo "  4: Rust resolver vs Python VDR + Rust VDG"
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

# Start services based on scenario
case "$SCENARIO" in
    1)
        echo "Starting Rust VDR..."
        RUST_VDR_VDG_HOSTS= $COMPOSE up -d rust-vdr-db rust-vdr
        ;;
    2)
        echo "Starting Rust VDR + VDG..."
        RUST_VDR_VDG_HOSTS=rust-vdg:8086 $COMPOSE up -d rust-vdr-db rust-vdg-db rust-vdg rust-vdr
        ;;
    3)
        echo "Starting Python VDR..."
        $COMPOSE up -d --build python-vdr
        ;;
    4)
        echo "Starting Python VDR + Rust VDG..."
        PYTHON_VDR_VDG_HOSTS=rust-vdg:8086 $COMPOSE up -d --build rust-vdg-db rust-vdg python-vdr
        ;;
esac

echo "Streaming Docker service logs (background)..."
$COMPOSE logs -f &
LOG_PID=$!

echo "Waiting for services to be healthy..."
sleep 10

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
