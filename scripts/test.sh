#!/bin/bash

set -e

ARGS=""

if git status --porcelain | grep -q 'requirements.txt'; then
    echo "requirements.txt has changed"
    ARGS="--build"
fi

docker compose run $ARGS --remove-orphans -T app pytest
