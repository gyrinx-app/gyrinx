#!/bin/bash

set -e

# Check if Docker daemon is running
docker_available() {
    docker info &>/dev/null 2>&1
}

if docker_available; then
    docker compose run -T app manage makemigrations core content
else
    # No Docker — run directly (e.g. Claude Code on the Web)
    manage makemigrations core content
fi
