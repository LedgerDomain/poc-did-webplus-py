#!/usr/bin/env bash
# Run interoperability tests for did:webplus
# Usage: ./run_interop_tests.sh <1-22>
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

SCENARIO="${1:-}"
if [[ -z "$SCENARIO" || ! "$SCENARIO" =~ ^(1[0-9]|2[0-2]|[1-9])$ ]]; then
    echo "Usage: $0 <1-22>"
    echo ""
    echo "Scenarios 1-16: Python/Rust matrix"
    echo "Scenarios 17-22: @zkred/did-webplus (TS) — see interop/README.md § TypeScript implementation"
    echo "Pinned TS version: $PINNED_TS_VERSION"
    echo ""
    echo "Optional env: INTEROP_ZKRED_DID_WEBPLUS_VERSION=<ver|github:...> for ad-hoc override"
    echo "Version card: interop/ZKRED_VERSION.md"
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
        # Semver/tag → @zkred/did-webplus@… ; github:/git+ specs used as-is
        local spec
        if [[ "$INTEROP_ZKRED_DID_WEBPLUS_VERSION" == github:* || "$INTEROP_ZKRED_DID_WEBPLUS_VERSION" == git+* ]]; then
            spec="$INTEROP_ZKRED_DID_WEBPLUS_VERSION"
        else
            spec="@zkred/did-webplus@${INTEROP_ZKRED_DID_WEBPLUS_VERSION}"
        fi
        # One-off image: install override version instead of npm ci from lockfile
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

echo "=== Scenario $SCENARIO ==="

# Ensure clean slate: stop any existing containers and remove volumes
echo "Ensuring clean slate..."
bash "$SCRIPT_DIR/stop_and_clean.sh"

# Always build zkred image (simple; required for 17-22, harmless for 1-16)
build_zkred_image

if [[ "$SCENARIO" -ge 17 ]]; then
    echo "=== TS interop: @zkred/did-webplus $PINNED_TS_VERSION (from package-lock.json) ==="
    echo "=== Version management: see interop/README.md or interop/ZKRED_VERSION.md ==="
fi

derive_compose_vdr_vdg "$SCENARIO"

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
