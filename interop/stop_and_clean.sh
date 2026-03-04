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
