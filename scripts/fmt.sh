#!/usr/bin/env bash
set -euo pipefail

echo "Running all formatters..."

# Run Python formatters
echo "Running ruff..."
ruff format .
ruff check --fix .

# Run npm formatters (includes prettier for JS, SCSS, JSON, YAML, Markdown)
echo "Running npm fmt..."
npm run fmt

# Run Markdown linting
echo "Running markdownlint..."
npx markdownlint-cli2 --fix "**/*.md"

# Run Django template formatter
echo "Running djlint..."
djlint --profile=django --reformat .
djlint --profile=django --lint --check .

echo "All formatters completed!"
