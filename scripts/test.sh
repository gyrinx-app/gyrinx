#!/bin/bash

set -e

ARGS=""

# Function to check if requirements changed
check_requirements_changed() {
    echo "Checking if requirements.txt has changed..."
    # Try to find the merge base with main branch
    if git rev-parse --verify origin/main >/dev/null 2>&1; then
        BASE_REF="origin/main"
    elif git rev-parse --verify main >/dev/null 2>&1; then
        BASE_REF="main"
    else
        # Can't find main branch, check if we're in CI
        if [ -n "$CI" ] || [ -n "$GITHUB_ACTIONS" ]; then
            echo "Running in CI without main branch reference - forcing rebuild"
            return 0
        fi
        # Not in CI and no main branch - skip rebuild
        return 1
    fi

    echo "Base reference for comparison: $BASE_REF"

    # Find merge base if possible
    if MERGE_BASE=$(git merge-base $BASE_REF HEAD 2>/dev/null); then
        echo "Found merge base: $MERGE_BASE"
        # Check if requirements.txt changed since merge base
        if git diff --name-only $MERGE_BASE...HEAD | grep -q 'requirements.txt'; then
            echo "requirements.txt has changed since merge base $MERGE_BASE"
            return 0
        fi

        # Check if requirements.txt in staged changes
        if git diff --cached --name-only | grep -q 'requirements.txt'; then
            echo "requirements.txt has changes staged for commit"
            return 0
        fi
    else
        # Can't find merge base, check if in CI
        if [ -n "$CI" ] || [ -n "$GITHUB_ACTIONS" ]; then
            echo "Cannot determine merge base in CI - forcing rebuild"
            return 0
        fi
    fi

    echo "No changes detected in requirements.txt since $BASE_REF"

    return 1
}

echo "Checking if requirements have changed..."

# Check if we need to rebuild
if check_requirements_changed; then
    ARGS="--build"
fi

# Check for parallel flag
PYTEST_ARGS=""
if [ "$1" = "--parallel" ] || [ "$1" = "-p" ]; then
    PYTEST_ARGS="-n auto"
    shift
fi

# Check for additional pytest arguments
if [ $# -gt 0 ]; then
    PYTEST_ARGS="$PYTEST_ARGS $@"
fi

docker compose run $ARGS --remove-orphans -T app pytest $PYTEST_ARGS
