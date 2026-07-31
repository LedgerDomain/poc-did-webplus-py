#!/usr/bin/env bash
# Run all interoperability test scenarios (1-22) for did:webplus
# Usage: ./run_all_interop_tests.sh
#
# Scenarios 1-16: Python/Rust matrix (Controller, VDR, Resolver × VDG)
# Scenarios 17-22: @zkred/did-webplus (TS) — see interop/README.md
#
# Optional: INTEROP_ZKRED_DID_WEBPLUS_VERSION=<ver> rebuilds the zkred image
# for this run only (does not modify package-lock.json).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Pinned @zkred/did-webplus version from committed lockfile (for banners / logging).
pinned_ts_version() {
    python3 -c "import json; print(json.load(open('package-lock.json'))['packages']['node_modules/@zkred/did-webplus']['version'])" 2>/dev/null \
        || echo "unknown"
}
PINNED_TS_VERSION="$(pinned_ts_version)"

echo "Scenarios 1-16: Python/Rust matrix"
echo "Scenarios 17-22: @zkred/did-webplus (TS) — see interop/README.md § TypeScript implementation"
echo "Pinned TS version: $PINNED_TS_VERSION"
if [[ -n "${INTEROP_ZKRED_DID_WEBPLUS_VERSION:-}" ]]; then
    echo "TS version override: $INTEROP_ZKRED_DID_WEBPLUS_VERSION"
fi
echo "Version card: interop/ZKRED_VERSION.md"
echo ""

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

# Derive VDR and VDG for compose startup.
# 1-16: bits 0 and 2 of (n-1) — same as run_interop_tests.py (controller/resolver ignored).
# 17-22: TS mapping in _ts_scenario_params (bits of n-1 do not encode VDR for these).
derive_compose_vdr_vdg() {
    local n="$1"
    if [[ "$n" -ge 17 ]]; then
        case "$n" in
            17) USE_VDG=0; VDR_RUST=0 ;;
            18) USE_VDG=1; VDR_RUST=0 ;;
            19) USE_VDG=0; VDR_RUST=1 ;;
            20) USE_VDG=1; VDR_RUST=1 ;;
            21) USE_VDG=0; VDR_RUST=0 ;;
            22) USE_VDG=0; VDR_RUST=1 ;;
        esac
    else
        USE_VDG=$(( (n - 1) & 1 ))
        VDR_RUST=$(( ((n - 1) & 4) != 0 ))
    fi
}

build_zkred_image() {
    echo "Building zkred runner image (did-webplus-zkred)..."
    if [[ -n "${INTEROP_ZKRED_DID_WEBPLUS_VERSION:-}" ]]; then
        echo "=== TS version override: $INTEROP_ZKRED_DID_WEBPLUS_VERSION (lockfile unchanged) ==="
        local spec
        if [[ "$INTEROP_ZKRED_DID_WEBPLUS_VERSION" == github:* || "$INTEROP_ZKRED_DID_WEBPLUS_VERSION" == git+* ]]; then
            spec="$INTEROP_ZKRED_DID_WEBPLUS_VERSION"
        else
            spec="@zkred/did-webplus@${INTEROP_ZKRED_DID_WEBPLUS_VERSION}"
        fi
        docker build -t did-webplus-zkred --build-arg "ZKRED_SPEC=$spec" -f - . <<'EOF'
FROM node:20-slim
ARG ZKRED_SPEC
WORKDIR /app
COPY ts_runner.mjs ./
RUN npm init -y && npm install --ignore-scripts --save "$ZKRED_SPEC"
ENTRYPOINT ["node", "ts_runner.mjs"]
EOF
    else
        docker build -f Dockerfile.zkred -t did-webplus-zkred .
    fi
}

# Build once before the full run (needed for scenarios 17-22)
build_zkred_image

run_scenario() {
    local scenario="$1"
    echo ""
    echo "=============================================="
    echo "  Scenario $scenario"
    echo "=============================================="

    bash "$SCRIPT_DIR/stop_and_clean.sh"

    if [[ "$scenario" -ge 17 ]]; then
        echo "=== TS interop: @zkred/did-webplus $PINNED_TS_VERSION (from package-lock.json) ==="
        echo "=== Version management: see interop/README.md or interop/ZKRED_VERSION.md ==="
    fi

    derive_compose_vdr_vdg "$scenario"

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

    if $COMPOSE run --rm --build interop-runner "$scenario"; then
        kill "$LOG_PID" 2>/dev/null || true
        $COMPOSE down
        return 0
    else
        kill "$LOG_PID" 2>/dev/null || true
        $COMPOSE down
        return 1
    fi
}

FAILED=0
RESULTS=()
for s in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22; do
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
