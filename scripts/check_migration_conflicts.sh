#!/bin/bash
#
# Check for conflicting Django migrations using Django's own
# MigrationLoader.detect_conflicts().
#
# This catches the real problem: multiple leaf nodes in a single app's
# migration graph (i.e. two migrations that both claim to follow the
# same parent, requiring a merge migration).  This is strictly better
# than checking for duplicate numeric prefixes, because two PRs can
# create migrations with *different* numbers that still conflict.
#
# Requires Django to be importable (run inside the virtualenv or CI
# after `pip install`).

set -euo pipefail

python scripts/manage.py check_migration_conflicts
