#!/usr/bin/env bash
# Run all interoperability test scenarios (1-4) for did:webplus
# Usage: ./run_all_interop_tests.sh
#
# Scenarios:
#   1: Python resolver vs Rust VDR (no VDG)
#   2: Python resolver vs Rust VDR + Rust VDG
#   3: Rust resolver vs Python VDR (no VDG)
#   4: Rust resolver vs Python VDR + Rust VDG

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

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

run_scenario() {
    local scenario="$1"
    echo ""
    echo "=============================================="
    echo "  Scenario $scenario"
    echo "=============================================="

    bash "$SCRIPT_DIR/stop_and_clean.sh"

    case "$scenario" in
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

    cd "$SCRIPT_DIR/.."
    if uv run python interop/run_interop_tests.py "$scenario"; then
        kill "$LOG_PID" 2>/dev/null || true
        cd "$SCRIPT_DIR"
        $COMPOSE down
        return 0
    else
        kill "$LOG_PID" 2>/dev/null || true
        cd "$SCRIPT_DIR"
        $COMPOSE down
        return 1
    fi
}

FAILED=0
for s in 1 2 3 4; do
    if run_scenario "$s"; then
        echo "Scenario $s: PASSED"
    else
        echo "Scenario $s: FAILED"
        FAILED=1
    fi
done

echo ""
echo "=============================================="
if [[ $FAILED -eq 0 ]]; then
    echo "  All scenarios PASSED"
    echo "=============================================="
    exit 0
else
    echo "  One or more scenarios FAILED"
    echo "=============================================="
    exit 1
fi
