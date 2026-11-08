#!/bin/bash

# Migrate apps to the last migration filename present on main.

set -e

current_branch=$(git branch --show-current)
if [ "$current_branch" = "main" ]; then
    echo "Already on main branch, nothing to do"
    exit 0
fi

echo "Resetting migrations from '$current_branch' to 'main' state..."

apps=$(git diff --name-only main HEAD | grep -E 'migrations/[0-9]+.*\.py$' | cut -d'/' -f2 | sort -u)

if [ -z "$apps" ]; then
    echo "No migration differences found between main and $current_branch"
    exit 0
fi

echo "Found migrations in: $apps"
echo

for app in $apps; do
    echo "Processing $app..."

    last_migration=$(git ls-tree -r main --name-only | grep "/$app/migrations/[0-9]" | sort | tail -n 1 | sed 's/.*\///' | sed 's/\.py$//')

    if [ -n "$last_migration" ]; then
        echo "  → Resetting to migration: $last_migration"
        manage migrate $app $last_migration
    else
        echo "  → No migrations found in main, skipping $app"
    fi
done

echo
echo "Migration state reset complete. You can now safely:"
echo "  git checkout main"
