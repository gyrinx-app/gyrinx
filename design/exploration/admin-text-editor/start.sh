#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
.venv/bin/python prepare.py
npm run build
node_modules/.bin/tailwindcss --input src/theme.css --output public/theme.css --minify
.venv/bin/python server.py setup
.venv/bin/python server.py link
exec .venv/bin/python server.py
