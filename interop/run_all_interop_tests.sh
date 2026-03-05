#!/usr/bin/env bash
# Run all interoperability test scenarios (1-16) for did:webplus
# Usage: ./run_all_interop_tests.sh
#
# 16 scenarios from 4 axes: Controller, VDR, Resolver (Python/Rust each), VDG (no/yes).

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

    USE_VDG=$(( (scenario - 1) & 1 ))
    VDR_RUST=$(( ((scenario - 1) & 4) != 0 ))

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
RESULTS=()
for s in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16; do
    if run_scenario "$s"; then
        RESULTS+=("  Scenario $s: PASSED")
    else
        RESULTS+=("  Scenario $s: FAILED")
        FAILED=1
    fi
done

echo ""
echo "=============================================="
if [[ $FAILED -eq 0 ]]; then
    echo "  All scenarios PASSED"
else
    echo "  One or more scenarios FAILED"
fi
echo "=============================================="
echo ""
echo "Summary by scenario:"
for line in "${RESULTS[@]}"; do
    echo "$line"
done
echo ""
if [[ $FAILED -eq 0 ]]; then
    exit 0
else
    exit 1
fi
