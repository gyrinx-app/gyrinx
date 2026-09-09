# Codex local worktrees

Use these scripts in the ChatGPT/Codex local environment settings. Codex creates
and removes the Git worktree; the scripts prepare and remove its local database.
They use the project's existing macOS/Homebrew development environment: Git,
Bash, uv, Node/npm, PostgreSQL 16 and a populated `gyrinx_main` template. Run
`./scripts/setup-local-postgres.sh` once from the main checkout first.

## Setup

Set the setup command to:

```bash
bash .codex/setup.sh
```

`CODEX_WORKTREE_PATH` selects the new worktree, even when the command runs from
the source workspace. `CODEX_SOURCE_TREE_PATH` selects the workspace whose `.env`
is copied if the new worktree has none. Both paths must be roots of worktrees in
the same repository. Without these variables, setup uses the current checkout
and copies `.env` from the main checkout.

Setup preserves an existing `.env`, creates separate Python and npm dependencies,
forks a database from `gyrinx_main`, runs migrations and builds both editions' CSS.
It exits without starting a server and can be rerun after a partial failure.
Shared `.env`, `.venv` and `node_modules` symlinks are rejected. Database cloning
uses the existing dev script, which briefly disconnects template DB connections.

Setup exports do not persist into later agent commands. Use `.codex/run.sh`
for Python commands, such as `.codex/run.sh manage check`.

## Cleanup

Run this command **before** the worktree is removed, with
`CODEX_WORKTREE_PATH` set to its absolute path:

```bash
bash .codex/cleanup.sh
```

With no path variable, cleanup targets the current checkout. It drops only that
worktree's database and its pytest databases (`test_<db>` and `test_<db>_gwN`).
It refuses the main checkout, another repository, missing paths and subdirectories.
It connects explicitly to local PostgreSQL on port 5432 as the current OS user,
using `GYRINX_DB_HOST` (the `/private/tmp` socket configured in `.codex/config.toml`)
or localhost when unset. Remote hosts are rejected.
Stop the worktree's dev server and test runs first: cleanup fails if a database is
still in use. It can be rerun if databases are already gone.

Preview the selection with `bash .codex/cleanup.sh --dry-run`.

Configure this as a cleanup command if your app exposes a hook that runs before
worktree deletion. Otherwise run it manually before deleting the worktree.
The published local environment docs describe setup and actions, but do not
specify a cleanup hook's timing or variables. Codex handles deleting the checkout,
including dependencies and logs; this script does not remove files or branches.
For worktrees already deleted, use `./scripts/cleanup-worktree-dbs.sh` to preview
orphaned databases and its `--force` option to remove them.

## Suggested toolbar actions

Add these commands as local environment actions. They run from the selected
checkout in the integrated terminal.

| Action | Command |
| --- | --- |
| Run dev server | `./scripts/dev.sh` |
| Open dev server | `./.codex/dev-url.sh --open` |
| Show dev URL | `./.codex/dev-url.sh` |
| Check Django | `./.codex/run.sh manage check` |
| Run core tests | `./.codex/run.sh pytest -m core -n 4` |
| Format | `./scripts/fmt.sh` |

The URL helper calculates the checkout's port without requiring setup or a running
server. Opening it does not start the server. Stop the Run action with Ctrl-C in
its terminal. Keep database cleanup out of the everyday toolbar.

## Check the scripts

```bash
python3 -m unittest discover -s .codex/tests -p 'test_lifecycle.py'
```

These tests use temporary Git repositories and stub development/Postgres commands;
they do not install dependencies or access the machine's databases.

References: [Worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)
and [Local environments](https://learn.chatgpt.com/docs/environments/local-environment).
