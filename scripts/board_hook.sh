#!/bin/bash
# Claude Code hook entry point for the agent board (`board hook <event>`).
#
# Only runs in Claude Code on the web. On a laptop the board's own install.sh
# puts these hooks in ~/.claude/settings.json; running them from the repo as
# well would fire every hook twice. On the web ~/.claude is created fresh at
# session start, so the repo's .claude/settings.json is the only settings file
# that survives, and this is where the hooks have to live.
#
# Always exits 0: a machine without the `board` CLI must not lose its session.
# Every decision the board makes (deny, block, extra context) is JSON on
# stdout, so the exit code carries nothing.
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
command -v board >/dev/null 2>&1 || exit 0
exec board hook "$1"
