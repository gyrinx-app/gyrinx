#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
.venv/bin/python prepare.py
npm run build
npm run build:styles
.venv/bin/python server.py setup
.venv/bin/python server.py link
exec .venv/bin/python server.py
