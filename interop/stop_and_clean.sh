#!/usr/bin/env bash
# Stop all interop containers and remove volumes for a clean slate.
# Run this to guarantee containers are down and volumes are deleted.
#
# Usage: ./stop_and_clean.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

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

$COMPOSE down -v

# Wallet dirs under wallets/ (and any leftover flat wallet_dir_scenario_*) may be
# root-owned after dockerized interop-runner runs (bind-mount writes as root).
# Remove them via a disposable container so host-user cleanup needs no sudo.
docker run --rm \
    -v "$SCRIPT_DIR:/interop" \
    alpine:3.20 \
    sh -c 'rm -rf /interop/wallets /interop/wallet_dir_scenario_*'

# Recreate wallets/ as the invoking user so the next compose bind-mount starts clean.
mkdir -p "$SCRIPT_DIR/wallets"
