#!/usr/bin/env bash
# Record one complete pytest run, including failures and resource use.
# Compare baseline and candidate with identical pytest arguments and workers.
# Usage: ./scripts/measure_test_performance.sh --label baseline -- -n 4
set -euo pipefail

cd "$(dirname "$0")/.."
exec .codex/run.sh python scripts/measure_test_performance.py "$@"
