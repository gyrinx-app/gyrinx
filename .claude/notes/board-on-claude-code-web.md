# Agent board on Claude Code on the web: what went wrong and how to fix it

Written by agent curlew-fc34 after connecting a Claude Code on the web session to
the board by hand on 2026-09-12. Fixes 1 to 3 below are implemented on the same
branch (`scripts/board_hook.sh`, `.claude/settings.json`, `scripts/setup_web.sh`,
`CLAUDE.md`); fix 4 is for the cloud environment's own setup script.

## What the session found

`board who` from a fresh web session fails with:

```
board: connected to https://agent-board-tgva.vercel.app as tgvashworth from BOARD_TOKEN
board: no board for this repo — run `board init` in its checkout
```

The hub connection is fine. `BOARD_TOKEN` is set in the environment and the CLI
connects itself on its first command, exactly as designed. The two owner-level
boards (`@gyrinx-app`, `@tgvashworth`) are pulled. What is missing is the repo
board for `gyrinx-app/gyrinx`, and everything that depends on it.

### Root cause: the board's hooks are not installed, and cannot survive where they usually live

The board relies on Claude Code hooks (`board hook session-start`, `prompt`,
`pre-tool`, `post-tool`, `stop`, `session-end`, `subagent-start`, `subagent-stop`).
The session-start and prompt hooks are what create the repo board on a machine
that has never seen it (`maybe_auto_init`), link it to the hub (`maybe_auto_link`)
and register the agent. On a laptop these hooks are merged into
`~/.claude/settings.json` by the board's own `install.sh`.

In the web environment:

- The CLI is present (`/usr/local/bin/board` -> `/root/.agent-board/bin/board`),
  installed at 13:33, an hour before this session's container was spawned at
  14:25. So it was installed by the cloud environment's setup script or baked
  into the snapshot. That part works.
- `~/.claude/` is created fresh at 14:25 when the session starts. Anything the
  environment script may have written into `~/.claude/settings.json` at
  snapshot time is gone. There is no `~/.claude/settings.json` at all; the
  platform's `~/.claude/launcher-settings.json` carries only its own git
  identity and stop hooks.
- The repo's `.claude/settings.json` has SessionStart hooks for
  `scripts/setup_web.sh` and `scripts/activate_venv_hook.sh`, and a PostToolUse
  microcopy check. No board hooks.
- `scripts/setup_web.sh` does not mention the board.

So no hook ever runs `board`. Nothing auto-inits, nothing auto-links, and:

- `board who` dies until someone runs `board init` by hand.
- Even after `board init`, the board is not linked to the hub. `board sync`
  says "board is not linked". Linking only happens from the hook path
  (`maybe_auto_link`), so it had to be triggered from Python directly.
- No prompt digests, no inbox nudges after tool calls, no Stop gate on unread
  asks, no background sync, no automatic journal lines for pushes and PRs.
- The PreToolUse guards are absent: the `pkill -f` refusal and the heavy-run
  guard `CLAUDE.md` describes ("the board's PreToolUse guard refuses a full run
  once while another is live"). On the web that guard is moot anyway, because
  each container has its own Postgres, but `CLAUDE.md` presents it as always on.

### What was verified

- `board init` in the checkout creates `~/.claude/boards/gyrinx` and registers
  the git common dir in the index. It is idempotent: directories are
  `exist_ok`, `board.json` is only written if absent.
- `boardsync.auto_link(lib, board, cwd)` links it using the machine token
  (scopes cover the `gyrinx-app` org). `board sync --once` then pushed 1 and
  pulled 1431 messages and 46 agent records.
- `board join --task …` registers the session. Claude Code on the web sets
  `CLAUDE_CODE_SESSION_ID`, so `BOARD_SESSION_ID` must not be set: a second id
  registers a second agent (a stray `grebe-0830` was created that way and
  retired with `board --as grebe-0830 leave`).
- Feeding a SessionStart payload to `board hook session-start` on stdin works
  in this environment and returns the standard `additionalContext` JSON. The
  hook machinery is fine; it is only not wired up.

### Found on the way: the web setup script was aborting at `uv sync`

`scripts/setup_web.sh` only installed uv when none was on PATH. The web image
ships uv 0.8.17 in `~/.local/bin`, and `pyproject.toml` pins
`[tool.uv] required-version = ">=0.11.12"`, so `uv sync --locked` refused and
`set -e` killed the script at step 4. In this session that left no `.venv`, no
`.env`, Postgres stopped, no `node_modules` and no static build, with nothing
in the chat to say so. `gh` was installed, which is how far the script got.
`.cursor/install.sh` had the same check. Both now read the floor from
`pyproject.toml` and reinstall uv when the installed one is older.

### Also found: the per-worktree DB block breaks every database call on the web

`scripts/activate_venv_hook.sh` writes a block that runs before every Bash
call and exports `DB_NAME=gyrinx_main` plus a `DB_CONFIG` of the login user
with an empty password (`db_config_for_local`). That is right for Homebrew's
trust auth on a workstation. The web container's Postgres uses scram auth over
TCP, only the `postgres` role exists (password `postgres`, set by
`setup_web.sh`), and no `gyrinx_main` database exists. So `manage` and the
tests fail with `fe_sendauth: no password supplied` in every web session, even
after a successful setup. The block now skips the DB variables when
`CLAUDE_CODE_REMOTE=true`, so `.env` (written by `manage setupenv`) governs.

The `Error parsing ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` lines in the setup
log come from the cloud environment's own variable values, which arrive with
backslash-escaped quotes inside single quotes. `settings.py` strips the outer
quotes but not the backslashes, logs the error and falls back to its defaults.
Harmless, but the values in the environment settings want fixing: plain
`["localhost"]` with no wrapping quotes.

## Changes to the repo

### 1. Wire the board hooks into `.claude/settings.json`, guarded

The only settings file that survives into a web session is the repo's own. Add
the eight board hooks there. Guard each one so it is a no-op on a machine that
does not have `board`, and so it does not double-fire on laptops where the
global hooks already exist. Everything the board prints is JSON on stdout with
exit 0 (deny decisions included), so masking the exit code is safe:

```json
{
  "hooks": {
    "SessionStart": [
      { "matcher": "startup", "hooks": [ { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/setup_web.sh" } ] },
      { "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/activate_venv_hook.sh" },
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/board_hook.sh session-start" }
      ] }
    ],
    "UserPromptSubmit": [ { "hooks": [ { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/board_hook.sh prompt" } ] } ],
    "PreToolUse":  [ { "matcher": "Bash", "hooks": [ { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/board_hook.sh pre-tool" } ] } ],
    "PostToolUse": [
      { "matcher": "Edit|Write", "hooks": [ { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/scripts/check_microcopy.py --hook" } ] },
      { "hooks": [ { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/board_hook.sh post-tool" } ] }
    ],
    "Stop":          [ { "hooks": [ { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/board_hook.sh stop" } ] } ],
    "SessionEnd":    [ { "hooks": [ { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/board_hook.sh session-end" } ] } ],
    "SubagentStart": [ { "hooks": [ { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/board_hook.sh subagent-start" } ] } ],
    "SubagentStop":  [ { "hooks": [ { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/board_hook.sh subagent-stop" } ] } ]
  }
}
```

`scripts/board_hook.sh`:

```bash
#!/bin/bash
# Run a board hook only in Claude Code on the web. Laptops get these hooks from
# ~/.claude/settings.json (the board's install.sh); running them twice would
# double every digest. Exit 0 whatever happens: a missing CLI must not break a session.
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
command -v board >/dev/null 2>&1 || exit 0
exec board hook "$1"
```

Check the exact event names and matchers against the board's own
`claude-hooks.snippet.json` in the agent-board repo before merging; the list
above is reconstructed from `cmd_hook` in `boardlib.py` and the manual.

With the hooks in place the session-start hook does the rest on its own:
`find_board(cwd) or maybe_auto_init(cwd)` creates and links the repo board,
registers the agent and prints the briefing. No `board init` step is needed.

### 2. Optionally pre-create the board from `scripts/setup_web.sh`

If the hooks are wired, this is belt and braces. If they are not, it at least
makes `board who` work. Add a step after the venv is up:

```bash
# --- Agent board ---
if command -v board >/dev/null 2>&1 && [ -n "${BOARD_TOKEN:-}" ]; then
  board init >/dev/null 2>&1 || true   # idempotent; links itself on the first hook
fi
```

Note that `init` alone does not link the board to the hub. Linking needs
either a hook or a Python one-liner, which is another reason to prefer fix 1.

### 3. Fix `CLAUDE.md`

- The testing section says "check `board who`" and describes the PreToolUse
  guard as if it always exists. Say that both depend on the board hooks, which
  the repo now provides on the web, and that the lock-table concern does not
  apply on the web where every container has its own Postgres.
- Add a line under "Before Starting" for web sessions: the board joins on the
  first prompt; say your board name in the first reply; `board join` is only
  for runtimes without hooks (Cursor Cloud), and `BOARD_SESSION_ID` must not be
  set under Claude Code because `CLAUDE_CODE_SESSION_ID` already identifies the
  session.

### 4. The environment setup script (outside the repo)

The cloud environment's script installs the CLI to `/root/.agent-board` and
that survives; whatever it does with `~/.claude/settings.json` does not. It
should not bother writing hooks there. If it runs the board's `install.sh`,
the merge into `~/.claude/settings.json` is wasted work and the backup files
it leaves are noise. Installing the CLI and setting `BOARD_TOKEN` is enough
once the hooks live in the repo.

## How to try it

From a fresh web session on a branch with fix 1:

```
board who          # should list you without any manual step
board sync --once  # should report pushed/pulled counts, not "not linked"
```

Until then, the manual recovery from this session is:

```
board init
python3 -c 'import sys,os;sys.path.insert(0,"/root/.agent-board/bin");import boardlib as l,boardsync as s;s.auto_link(l,l.find_board(os.getcwd()),os.getcwd())'
board join --task "…"
board sync --once
```
