#!/bin/bash

set -e

ARGS=""

if git diff --name-only origin/main...HEAD | grep -q 'requirements.txt'; then
    echo "requirements.txt has changed between main and HEAD"
    ARGS="--build"
fi

docker compose run $ARGS --remove-orphans -T app pytest
