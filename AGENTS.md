# Gyrinx repository instructions

Gyrinx is a Django application for managing Necromunda gangs and campaigns.
N23 uses server-rendered Bootstrap pages; N26 uses Tailwind/Cotton pages with
client-rendered React islands. Django handles routing, permissions, validation
and writes.

## Instructions by directory

Read the nearest `AGENTS.md` for the files you change. These directories have
additional instructions:

- [`n23/AGENTS.md`](n23/AGENTS.md) — N23 architecture, URL-driven UI, and pack archive semantics.
- [`n23/core/AGENTS.md`](n23/core/AGENTS.md) — N23 models, views, permissions, performance, and tests.
- [`n23/core/templates/AGENTS.md`](n23/core/templates/AGENTS.md) — N23 Cotton components and template traps.
- [`n23/core/static/AGENTS.md`](n23/core/static/AGENTS.md) — N23 SCSS and JavaScript.
- [`n26/AGENTS.md`](n26/AGENTS.md) — N26 boundaries, vocabulary, design rules, and comments.
- [`n26/core/AGENTS.md`](n26/core/AGENTS.md) — N26 player-data writes, reads, UI, and tests.
- [`n26/library/AGENTS.md`](n26/library/AGENTS.md) — N26 content models, authoring, modifiers, and ingest.
- [`n26/frontend/AGENTS.md`](n26/frontend/AGENTS.md) — React island source and dependency rules.
- [`n26/designsystem/AGENTS.md`](n26/designsystem/AGENTS.md) — component gallery and demos.
- [`n26/tests/AGENTS.md`](n26/tests/AGENTS.md) — N26 test tiers, fixtures, and conventions.
- [`gyrinx/tasks/AGENTS.md`](gyrinx/tasks/AGENTS.md) — background delivery and idempotency.
- [`gyrinx/maintenance/AGENTS.md`](gyrinx/maintenance/AGENTS.md) — production repairs and backfills.
- [`gyrinx/analytics/AGENTS.md`](gyrinx/analytics/AGENTS.md) and
  [`analytics/AGENTS.md`](analytics/AGENTS.md) — application and warehouse analytics.

Reusable specialist guidance lives in [`.agents/skills/`](.agents/skills/).
Load the relevant skill before working in its area. Use `gyrinx-conventions`
for Django and domain changes, `microcopy` for user-facing text,
`design-system` for UI, `n26-react` for N26 interactions, `sql-performance` for
database-backed pages, `worktree-db` for database lifecycle work,
`dev-server` for local browser testing and `canvas-viewer` for `.canvas.tsx`
artifacts when the IDE Canvas surface is unavailable.

## Working in the repository

- Use a dedicated worktree and task branch for every repository change. Reuse
  the worktree already assigned to the task. Do not edit the shared checkout or
  another task's branch.
- Store private notes, scratch analysis and handover notes outside the
  repository under `~/.local/share/gyrinx/agent-notes/<task>/`. Do not add
  private notes to the legacy `.claude/notes/` directory.
- Put requested project documentation in the relevant versioned `docs/`,
  `design/`, or script path.
- Look up model definitions before using fields, choices, or relationships.
- Keep changes focused. Preserve unrelated work in a dirty checkout.

## Commands and local environment

- Start the app with `./scripts/dev.sh`. It provisions the worktree environment,
  database, migrations, frontend dependencies, initial CSS build, Django server,
  and watchers. Confirm the printed `CSS ready:` and `CSS file:` lines.
- Run Django commands with `manage`, never `python manage.py`.
- For Codex shells, run direct Python and Django commands through
  `.codex/run.sh`, for example `.codex/run.sh manage check` or
  `.codex/run.sh pytest`. After a rebase that changes `package-lock.json`,
  `n26/frontend`, Cotton templates, or icon sources, `.codex/run.sh` runs
  `npm ci` and rebuilds the ignored React manifest when they are missing or
  stale. `npm run js` needs the worktree venv on PATH. Do not run
  `npm audit fix` unless the task is the audit itself. `scripts/dev.sh` and
  `scripts/fmt.sh` activate the worktree environment themselves. Pre-commit
  hook scripts find `.venv/bin/python` themselves, so a plain `git commit`
  works when PATH has no interpreter.
- Use `./scripts/test.sh` for the full suite, or build React with `npm run js`
  before direct pytest runs on a clean checkout. `pyproject.toml` already runs
  pytest with xdist and `--nomigrations`.
- Use `pytest -n 0 -s <test>` when debugging print output. Use `pytest -n 4`
  rather than saturating the shared Postgres lock table while another agent has
  a test run active.
- Format with `./scripts/fmt.sh`.
- Build SCSS with `npm run css`; never commit generated CSS under
  `n23/core/static/core/css/`.
- See [`.codex/README.md`](.codex/README.md) for worktree lifecycle and database
  isolation. Run `.codex/setup.sh` after creating a Codex worktree and
  `.codex/cleanup.sh` before deleting one.

## Development workflow

For coding tasks, start the dev server early and share its worktree-specific URL.
If a page needs authentication, load the `dev-server` skill and run:

```bash
manage agent_login_url /path/to/page
# Codex shells:
.codex/run.sh manage agent_login_url /path/to/page
```

Use the printed one-click URL. Do not submit `/accounts/login/`, guess existing
credentials, reuse a person's account, or change a superuser password. Local
agent users are named `agent` or `agent-<purpose>`.

Before pushing:

1. Run `./scripts/fmt.sh`.
2. Run focused tests for the changed behaviour; run `./scripts/test.sh` when the
   scope warrants the full suite.
3. Manually exercise non-trivial rendered or interactive changes.
4. For database-backed pages, use the `sql-performance` skill and check query
   growth with representative repeated data.
5. For changed user-facing text, use the `microcopy` skill.
6. For meaningful UI changes, use `pr-screenshots` and add useful evidence to
   the PR when it helps reviewers.

See [`docs/developing-gyrinx/testing.md`](docs/developing-gyrinx/testing.md) for
the checks required by CI. Fix failures in the source; do not bypass static
checks or pre-commit hooks.

## Architecture and security

- In N23, views handle HTTP concerns, handlers own business operations, models
  own data invariants and templates receive prepared display data. Read
  [`n23/core/AGENTS.md`](n23/core/AGENTS.md) before changing these layers.
- In N26, every player-data write goes through `operation(...)`. Read
  [`n26/core/AGENTS.md`](n26/core/AGENTS.md) before changing the player-data
  pipeline.
- N23 interaction state that changes a form variant, visible section, tab, or
  choice set belongs in the URL and is rendered by the server. JavaScript may
  enhance the page, but the server must decide which fields and choices the
  form uses.
- Use React only for self-contained N26 interactions. Put shareable navigation
  state in the URL. React may hold temporary control state and unsaved drafts.
  Read [`docs/developing-gyrinx/react.md`](docs/developing-gyrinx/react.md).
- Prefer existing Cotton components to hand-written framework markup. Design
  for mobile screens first, then add layouts for wider screens.
- Validate any user-provided return target with `safe_redirect`,
  `get_return_url`, or the helpers in [`gyrinx/http.py`](gyrinx/http.py).
- Never apply `|safe` to user content. Use the project's `safe_rich_text`
  filter.
- The task system may deliver a background task more than once. Any task that
  changes data must handle duplicate and concurrent runs safely.

## Migrations and production data

- Generate migrations with `manage makemigrations <app> -n <name>`; do not type
  dependency lists by hand. The repository supports multiple migration leaves,
  so do not renumber or repoint a migration after rebasing.
- A branch adds at most one leaf per app. Run
  `manage check_migration_overlap --base origin/main` when another branch may
  touch the same schema or data.
- `manage prodshell` is read-only. Never work around that protection.
- Keep piped `prodshell` queries to one expression because IPython echoes
  multi-line loops unreliably. For example:
  `echo 'print(User.objects.count())' | manage prodshell`.
- Production data repair code belongs in the maintenance Backfill flow and runs
  through the task framework. Read
  [`gyrinx/maintenance/AGENTS.md`](gyrinx/maintenance/AGENTS.md) before writing
  one.
- Smoke-test migrations and data-touching work against a realistic database and
  verify affected records independently before and after the operation.

## Git and reporting

Read [`.github/COMMIT_STYLE.md`](.github/COMMIT_STYLE.md) before committing or
opening a PR. Give commit and PR titles a conventional prefix and name the
affected component or path. Mark completed work ready for review unless the
user requested a draft.

Assume the technical lead has no prior context. Start with the resulting
behaviour, name the affected page, model or command, and explain internal terms
once. Include concrete verification or steps to try the change. Keep PR
descriptions factual and update screenshots when later changes make them
inaccurate.
