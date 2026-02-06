#!/usr/bin/env bash
set -euo pipefail

# Activate the project venv so we use the pinned tool versions (e.g. ruff)
# rather than whatever happens to be on the system PATH.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_ACTIVATE="${SCRIPT_DIR}/../.venv/bin/activate"
if [ -f "$VENV_ACTIVATE" ]; then
  # shellcheck disable=SC1090
  source "$VENV_ACTIVATE"
fi

echo "Running all formatters..."

# Run Python formatters
echo "Running ruff..."
ruff format .
ruff check --fix .

# Run npm formatters (includes prettier for JS, SCSS, JSON, YAML)
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
