#!/bin/bash

set -e

python scripts/manage.py makemigrations --check --dry-run --verbosity 0
if [ $? -ne 0 ]; then
    echo "Migrations are not up to date. Please run 'manage makemigrations' to create new migrations."
    exit 1
fi
