#!/usr/bin/env bash
# Run did:webplus test-vector interop suite.
# Extra args are forwarded to interop/run_test_vectors.py (do not pass the
# script name). Useful filters for debugging a single failure:
#
#   ./run_test_vectors.sh --resolver python --name some-vector-name
#   ./run_test_vectors.sh --resolver rust --name some-vector-name
#   ./run_test_vectors.sh --resolver zkred --name some-vector-name
#
# --resolver: python | rust | zkred | all (default: all)
# --name:     catalog vector name (repeatable); also --group NAME (repeatable)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SERVICE="ledgerdomain.github.io"
HEALTH_TIMEOUT_SECONDS="${TEST_VECTOR_HEALTH_TIMEOUT_SECONDS:-60}"
CATALOG_INDEX="ledgerdomain.github.io/did-webplus-spec/test-vector/index.json"

if [[ ! -f "$CATALOG_INDEX" ]]; then
    echo "Error: test-vector catalog missing at $CATALOG_INDEX"
    echo "Initialize the did-webplus-spec submodule (see resolver-conformance-testing.md):"
    echo "  git submodule update --init interop/ledgerdomain.github.io/did-webplus-spec"
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

# Sibling docker run --resolver zkred needs did-webplus-zkred on the host daemon
build_zkred_image

echo "Starting $SERVICE..."
$COMPOSE up -d --build "$SERVICE"

SERVICE_CONTAINER_ID="$($COMPOSE ps -q "$SERVICE")"
if [[ -z "$SERVICE_CONTAINER_ID" ]]; then
    echo "Error: failed to get container id for $SERVICE"
    $COMPOSE ps
    exit 1
fi

echo "Waiting for $SERVICE to be healthy..."
START_SECONDS="$(date +%s)"
while true; do
    HEALTH_STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$SERVICE_CONTAINER_ID" 2>/dev/null || true)"
    case "$HEALTH_STATUS" in
        healthy)
            break
            ;;
        unhealthy|exited|dead)
            echo "Error: $SERVICE health status is $HEALTH_STATUS"
            $COMPOSE logs "$SERVICE" || true
            exit 1
            ;;
    esac

    NOW_SECONDS="$(date +%s)"
    ELAPSED_SECONDS="$((NOW_SECONDS - START_SECONDS))"
    if [[ "$ELAPSED_SECONDS" -ge "$HEALTH_TIMEOUT_SECONDS" ]]; then
        echo "Error: timed out waiting for $SERVICE to become healthy (${HEALTH_TIMEOUT_SECONDS}s)"
        $COMPOSE ps
        $COMPOSE logs "$SERVICE" || true
        exit 1
    fi
    sleep 1
done

echo "Streaming Docker service logs (background)..."
$COMPOSE logs -f "$SERVICE" &
LOG_PID=$!

EXIT_CODE=1
cleanup() {
    kill "$LOG_PID" 2>/dev/null || true
    cd "$SCRIPT_DIR"
    $COMPOSE down
    exit "$EXIT_CODE"
}
trap cleanup EXIT

echo "Running test-vector runner..."
set +e
$COMPOSE run --rm --build test-vector-runner "$@"
EXIT_CODE=$?
set -e
