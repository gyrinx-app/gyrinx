#!/usr/bin/env bash
set -euo pipefail

# Activate the project venv, then prove its formatters match uv.lock before any
# command gets a chance to rewrite files.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_ACTIVATE="${SCRIPT_DIR}/../.venv/bin/activate"
if [ ! -f "$VENV_ACTIVATE" ]; then
  echo "ERROR: No project virtualenv found at ${SCRIPT_DIR}/../.venv." >&2
  echo "Run \`uv sync --locked\` and try again." >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$VENV_ACTIVATE"
python "$SCRIPT_DIR/check_formatter_versions.py"

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
