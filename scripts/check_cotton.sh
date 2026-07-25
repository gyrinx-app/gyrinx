#!/usr/bin/env bash
# Guards the three cotton failure modes that are SILENT: they raise no exception,
# fail no test and pass djlint, but ship broken HTML to users.
#
#   1. A conditional attribute inside a <c-*> tag. Cotton emits the literal
#      template source into the page and eats the closing tag.
#   2. An UNDECLARED value passed as :attr="...". Undeclared attrs are rendered
#      through {{ attrs }}, which is mark_safe'd and does not HTML-escape, so a
#      crafted value injects a live event handler. Props DECLARED in the target
#      component's <c-vars> are autoescaped and therefore fine.
#   3. <c-errors form="..."> without the colon. The form stringifies and every
#      error silently disappears -- the exact bug #2001 was about.
#
# Run from the repo root. Wired into pre-commit and CI.
set -uo pipefail
cd "$(dirname "$0")/.."
exec python3 scripts/check_cotton.py "$@"
