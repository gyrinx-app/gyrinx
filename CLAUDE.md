# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Documentation Guidelines

- **`.claude/notes/`** - Internal documentation and plans created by Claude to help with its work
- **`docs/`** - Documentation for humans (user guides, API docs, etc.)
- When creating analysis documents, optimization plans, or working notes, place them in `.claude/notes/`
- Only create user-facing documentation in `docs/` when explicitly requested

## Quick Reference (Most Important)

**Critical Commands:**

- Start dev server: `./scripts/dev.sh` (starts Django + CSS watch, per-worktree isolation)
- Format code: `./scripts/fmt.sh`
- Run tests: `pytest -n auto`
- Django commands: Use `manage` (not `python manage.py`)
- Production shell: `manage prodshell` (read-only access to production database)
- Don't commit CSS files - they're auto-generated from SCSS
- The virtualenv is auto-activated for every Bash command by a `SessionStart` hook
  (`scripts/activate_venv_hook.sh`) that persists `.venv` into `CLAUDE_ENV_FILE`.
  There is no need to prefix commands with `. .venv/bin/activate &&`.
- The session hook also sets `DB_NAME` and `DJANGO_PORT` per-worktree — `manage` and `pytest`
  automatically target the correct database.

**Key Principles:**

- Server-rendered HTML, not SPA
- **URL-driven UI state.** Any state that picks a form variant, switches a
  visible section, opens a modal, or selects a tab belongs in the URL
  (path or query string). The server renders the right variant. JS may
  enhance (live preview, async validation, autocomplete) but the page MUST
  work — and be linkable — without it. **Do not** mutate forms client-side
  to swap fields, swap mode choices, hide/show sections, or alter
  validation. If you reach for `addEventListener('change', …)` to rewrite
  a form, you've probably skipped a navigation. See the rationale and the
  full rule in `.claude/skills/gyrinx-conventions/SKILL.md`.
- Mobile-first design
- Look up model definitions before use - don't assume field names
- Always validate redirect URLs with `safe_redirect`

## Infrastructure

- All our infra is in GCP europe-west2 (London)
- In prod, the user uploads bucket name is gyrinx-app-bootstrap-uploads

## Local Development (Per-Worktree Isolation)

Each git worktree gets its own Postgres database and Django port, started with a single command.

- **Setup (once per machine):** `./scripts/setup-local-postgres.sh` — installs Postgres 16 + pgAdmin via Homebrew,
  migrates data from Docker
- **Start dev server:** `./scripts/dev.sh` — ensures DB exists (forks from template if needed), provisions a
  per-worktree `.venv` on first run in a child worktree, runs migrations, runs `npm install` if
  `node_modules` is missing/stale, does an initial `npm run css` build if `styles.css` is missing/stale,
  then starts Django runserver + npm watch. **Always confirm the `CSS ready:` / `CSS file:` lines appear
  in the startup output — `npm run watch` alone never produces an initial build, so without `dev.sh`
  doing the seed build you'd get unstyled pages.**
- **Reset a worktree DB:** `./scripts/dev.sh --reset-db` — drops and re-forks from template
- **Rebuild a worktree's venv:** `./scripts/dev.sh --reset-venv` — wipes and re-provisions `${WT_ROOT}/.venv`
- **Clean up orphans:** `./scripts/cleanup-worktree-dbs.sh` — drops orphan DBs + reports worktree `.venv` sizes

**How it works:**

- Main worktree uses `gyrinx_main` database (port 8000) — this is the template with curated test data
- Child worktrees get `gyrinx_wt_{hash}` databases forked via `CREATE DATABASE ... TEMPLATE`
- Ports are deterministic per worktree path (range 8100-9599)
- **Each child worktree gets its own `.venv` with `gyrinx` editable-installed from that worktree**, so
  `import gyrinx` always resolves to worktree-local code (new migrations, new models, etc.). Without this,
  `manage migrate` from a child worktree silently misses new migrations and `pytest` fails with
  `ImportError`. `./scripts/dev.sh` provisions the venv via `uv venv` + `uv pip install --editable .` on
  first run (~1 minute). Main worktree continues to use whatever venv it already had.
- The session hook (`activate_venv_hook.sh`) auto-sets `DB_NAME` and `DJANGO_PORT` for every
  Claude Code Bash invocation
- `setup-local-postgres.sh` appends a block to `.venv/bin/activate` so that
  `source .venv/bin/activate` from any interactive terminal also exports the
  per-worktree DB env vars. **Re-activate the venv after switching worktrees**
  — the hook reads `git rev-parse --show-toplevel` at activation time, not on
  every command. Without this, `pytest` and `manage` from a plain shell fall
  back to `settings.py` defaults (user=postgres) and fail with
  "role postgres does not exist".
- `setup-local-postgres.sh` also tunes `max_locks_per_transaction = 256` in
  the local cluster (the default 64 is too low for pytest-xdist with 12
  workers each running syncdb in parallel — symptom is "out of shared memory").
- pgAdmin 4 (local app) connects to localhost:5432 and is pre-registered with
  a "Gyrinx (local)" server on first setup (CLI-imported into pgAdmin's
  SQLite config at `~/.pgadmin/pgadmin4.db`)

## Agents, Skills, and Commands

This repo has custom agents, skills, and slash commands in `.claude/`. Use them proactively at the right points
in the workflow.

### Agents (`.claude/agents/`)

- **feature-planner** — Use before starting any non-trivial feature or bug fix. Produces a work breakdown, testing
  strategy, and risk assessment. Loads `gyrinx-conventions` automatically.
- **code-simplifier** — Use for architecture review, code review, or refactoring analysis. Applies four analytical
  lenses (simplify, unify, abstract, boundaries). Loads `gyrinx-conventions` and `code-analysis-lenses`.
- **diataxis-docs-expert** — Use when creating or auditing documentation. Follows the Diataxis framework.
- **code-explorer** — Deeply analyzes existing codebase features by tracing execution paths, mapping architecture
  layers, and documenting dependencies.
- **code-architect** — Designs feature architectures by analyzing existing patterns and providing implementation
  blueprints with component designs, data flows, and build sequences.
- **code-reviewer** — Reviews code for bugs, security vulnerabilities, and convention adherence using confidence-based
  filtering (only reports high-confidence issues).

### Slash Commands (`.claude/commands/`)

- `/manual-test-plan [notes]` — Generate a manual test plan for recent changes, formatted for Claude for Chrome.
  Run after implementing a feature to create a browser-testable checklist.
- `/gissue <path>` — Create a GitHub issue from an analysis file (e.g., from `.claude/notes/`), uploading the full
  analysis to a gist and creating a summary issue.
- `/trace-playbook <trace-file>` — Run the full trace performance analysis playbook on a Google Cloud Trace JSON file.
- `/feature-dev [description]` — Guided 7-phase feature development workflow: discovery, codebase exploration,
  clarifying questions, architecture design, implementation, quality review, and summary. Uses `code-explorer`,
  `code-architect`, and `code-reviewer` agents.

### Skills (`.claude/skills/`)

Skills are loaded automatically by agents that need them. They can also be referenced directly:

- **gyrinx-conventions** — Canonical architectural patterns for the project (views, handlers, models, templates, tests)
- **code-analysis-lenses** — Four structured lenses for evaluating code quality
- **edit-github-discussion** — Workflow for editing GitHub Discussions via GraphQL API
- **trace-analysis** — Guide for analyzing OpenTelemetry trace files
- **pr-comments** — Fetch all PR comments, reviews, and review threads in a single GraphQL call. Shows
  resolved/unresolved status, groups by file, and summarises action items. Auto-detects PR from current branch.
  Claude loads this automatically when it needs PR feedback data.
- **pr-feedback** — Review PR feedback from reviewers and Copilot, triage each comment
  (implement / acknowledge / decline), plan changes, and implement approved fixes. Invoke with
  `/pr-feedback [PR number or URL]`. Uses the `pr-comments` fetch script for data.
- **dev-server** — Knowledge about starting/stopping the dev server, reading ports, telling Claude in Chrome
  where to point, log file locations
- **worktree-db** — Knowledge about per-worktree database isolation: forking, resetting, migrating, cleanup,
  template workflow, pgAdmin access

## Browser automation

Only use ONE of Chrome DevTools MCP or Claude in Chrome MCP in a session — they cannot work together. Prefer Claude in Chrome for browser testing.

## Long sessions

If you have the Pushpush MCP installed, you can use it to notify the user that you need their input. The tool is `send_push`. Use the `claude` topic.

IMPORTANT: Use this when you are about to pause to get input, or about to use `AskUserQuestion`.

## Critical Workflow

### Before Starting

1. Create a new branch for the task: `git checkout -b issue-NAME`
2. **Label the issue (Claude Code on the Web only):** If working on a GitHub issue in a Claude Code for Web session
   (`CLAUDE_CODE_REMOTE=true`), label it so the team knows it's being handled:
   `gh issue edit <NUMBER> --add-label claude-code-web`
   The label definition is created automatically by `scripts/setup_web.sh` during session start; you still need to add this label to the issue manually.
3. For non-trivial features or bug fixes, use the **feature-planner** agent to create an implementation plan before
   writing code

### Before Push

1. Format code: `./scripts/fmt.sh`
2. Run tests: `pytest -n auto`
3. Fix any failing tests
4. Consider running the **code-simplifier** agent on changed files for a quality check
5. Commit and push changes

**In CI/GitHub Actions:** MUST commit and push before finishing or work is lost.

## Development Commands

**Django:** Use `manage` command (not `python manage.py`)

### Environment Setup

```bash
# Setup virtual environment and install dependencies
uv venv .venv
uv pip install --editable .

# Setup environment file
manage setupenv

# Install frontend dependencies and setup node in venv
nodeenv -p
npm install

# Install pre-commit hooks
pre-commit install
```

**Note:** In Claude Code on the Web environments, `setup_web.sh` runs automatically on session
start and configures PostgreSQL directly. Use `pytest` and `manage` directly — there's no
Docker layer to go through.

### Running the Application

```bash
# Start everything — handles DB, migrations, runserver, CSS watch
./scripts/dev.sh
```

### Testing

```bash
# Run full test suite (thin wrapper over pytest; tests use local Postgres)
./scripts/test.sh

# Run tests with pytest-watcher for continuous testing
ptw .

# Run specific test
pytest gyrinx/core/tests/test_models_core.py::test_basic_list

# Run tests with pytest directly
pytest

# Run tests in parallel using pytest-xdist (significant performance improvement)
pytest -n auto  # Uses all CPU cores
pytest -n 4     # Uses 4 workers

# Collect static files before running tests (required for templates with static assets)
manage collectstatic --noinput
```

**IMPORTANT for Claude:** `pyproject.toml` addopts already includes `-n auto --nomigrations`.
The test DB is rebuilt from models on every run (via `--nomigrations` syncdb), so schema
changes are picked up automatically — no `--create-db` or `--migrations` flag needed.
If you want to reuse the test DB across runs for speed, pass `--reuse-db` explicitly —
but be aware that `--reuse-db` combined with `--nomigrations` does NOT detect schema
staleness, so you'll need a one-off `--create-db` run after changing a model.

### Frontend Development

```bash
# Build CSS from SCSS
npm run css

# Lint CSS
npm run css-lint

# Format JavaScript
npm run js-fmt

# Watch for changes and rebuild CSS
npm run watch
```

DO NOT commit CSS files. They are generated from SCSS automatically.

### Database Operations

```bash
# Create migration for model changes
manage makemigrations core -n "descriptive_migration_name"
manage makemigrations content -n "descriptive_migration_name"

# Create empty migration for data migration
manage makemigrations --empty content

# Apply migrations
manage migrate

# Check for migration issues
./scripts/check_migrations.sh

# Enable SQL debugging (set in .env)
SQL_DEBUG=True
```

### Production Database Access

```bash
# Open interactive read-only shell connected to production database
manage prodshell

# Query production data by piping Python code
echo 'print(User.objects.count())' | manage prodshell
echo 'print(List.objects.filter(archived=False).count())' | manage prodshell
```

**Important:** Read-only mode is enforced — all write operations raise `RuntimeError`. Requires `gcloud` CLI,
`cloud-sql-proxy`, and valid GCP authentication (both `gcloud auth login` and `gcloud auth application-default login`).

## Key Models Reference

**Content App (Game Data):**

- `ContentFighter` - Fighter templates
- `ContentEquipment` - Equipment/weapons
- `ContentWeaponProfile` - Weapon stats
- `ContentFighterDefaultAssignment` - Default equipment on fighters
- `ContentEquipmentUpgrade` - Equipment upgrades

**Core App (User Data):**

- `List` - User's gang/list
- `ListFighter` - User's fighters
- `ListFighterEquipmentAssignment` - Equipment assigned to fighters
- `VirtualListFighterEquipmentAssignment` - Wrapper for assignments

## Architecture Overview

### Django Apps Structure

**Main Apps:**

- `content` - Game data models (ContentFighter, ContentEquipment, etc.)
- `core` - User lists/gangs (List, ListFighter, ListFighterEquipmentAssignment)
- `pages` - Static content
- `api` - Webhook handling

### Base Model Architecture

- **`AppBase`** - Abstract base model for all app models, provides:
  - UUID primary key (from `Base`)
  - Owner tracking (from `Owned`)
  - Archive functionality (from `Archived`)
  - History tracking with user information (from `HistoryMixin`)
  - History-aware manager for better user tracking
- All models inherit from `AppBase` to get consistent behavior
- Models already define `history = HistoricalRecords()` for SimpleHistory integration
- **Never call `self.full_clean()` from `save()`.** This is a Django anti-pattern: it duplicates work the form layer
  already does, runs validation queries on every write (including bulk operations and migrations), can fail in
  surprising ways for partially-loaded instances, and conflates form-level validation with persistence. Use form
  validation, `clean()` invoked explicitly where needed, or database constraints instead. A few legacy models still
  do this — do not copy the pattern, and prefer to remove it when touching those files.

### Key Model Relationships

- Content models (ContentFighter, ContentEquipment) → Templates for user data
- Core models (ListFighter, ListFighterEquipmentAssignment) → User-created content
- VirtualListFighterEquipmentAssignment → Wrapper for both default and direct assignments
- All models use django-simple-history for tracking changes

### Technical Principles

- **Not an SPA**: Server-rendered HTML with form submissions, not React/API
- **Mobile-first**: Design for mobile, scale up to desktop
- **Make it work; make it right; make it fast**: Ship functionality first, optimize later
- **Security**: Always validate return URLs using `safe_redirect` when accepting redirect URLs from user input to
  prevent open redirect vulnerabilities

### Domain Rules

#### Content packs: archive semantics

`archived` on `CustomContentPack` and `CustomContentPackItem` is a **pack-owner soft-delete**. It hides the pack/item
from the owner's pack admin/editor and prevents new subscribers from picking it up — but it does **not** retract
content from lists/gangs already subscribed.

Once a list or campaign holds a pack in its `packs` M2M, every item in that pack stays visible to that list — even
items where `archived=True`, and even if the whole pack has been archived. This applies to fighters, equipment,
default assignments, weapon profiles, accessories, skills, rules, psyker disciplines, psyker powers, and any other
pack-aware content.

**Rules of thumb when querying packs / pack items:**

- **Subscriber read paths** (anything driven by `list.packs` or `campaign.packs`) MUST NOT filter `archived=False` on
  `CustomContentPack` or `CustomContentPackItem`. This applies to both directions: the M2M lookup that finds *which*
  packs a list/campaign is subscribed to (e.g. `CustomContentPack.objects.filter(subscribed_lists__id=...)`), and the
  pack-item lookup that resolves content within those packs. The canonical join is `ContentQuerySet.with_packs(packs,
  include_archived_items=True)` in `gyrinx/content/models/base.py` — subscriber paths **must** pass
  `include_archived_items=True`; the default excludes archived items so owner-side callers don't surface them.
- **Pack-owner library views, gallery / featured listings, list-creation pack pickers, and campaign pack-add UIs** —
  these are pack-discovery / write paths. Filtering `archived=False` is correct here so archived packs don't appear
  as new options. For `with_packs([pack])` calls on owner-side, leave the default — archived items stay hidden.
- **Form validation and unique-constraint lookups** — also fine to filter `archived=False`; the unique constraint on
  `CustomContentPackItem` is conditional on `archived=False` and code that looks up the "live" item must match.

If you find a place where archived pack content is being hidden from subscribers, treat it as a bug (see #1742).

### Settings Configuration

- `settings.py` - Production defaults
- `settings_dev.py` - Development overrides
- `settings_prod.py` - Production-specific config
- Environment variables loaded from `.env` file

### Frontend Stack

- Bootstrap 5 for UI components
- SCSS compiled to CSS via npm scripts
- No JavaScript framework - vanilla JS where needed
- Django templates with custom template tags

### Deployment

- Google Cloud Platform (Cloud Run + Cloud SQL PostgreSQL)
- Automatic deployment via Cloud Build on main branch pushes
- WhiteNoise for static file serving
- Docker containerized application

### Content Management

- Content is managed through Django admin interface

### Template Patterns

- Use `{% extends "core/layouts/base.html" %}` for full-page layouts
- Use `{% extends "core/layouts/page.html" %}` for simple content pages
- Back buttons use `{% include "core/includes/back.html" with url=target_url text="Back Text" %}`
- Work "mobile-first" with responsive design
- Left-align templates: typically `col-12 col-xl-6` works well
- User content should use `|safe` filter for HTML rendering
- Templates follow Bootstrap 5 patterns with cards, alerts, and responsive utilities

### UI Patterns

**Button Classes:**

- Primary: `btn btn-primary btn-sm`
- Secondary: `btn btn-secondary btn-sm`
- Danger: `btn btn-danger btn-sm`
- Link style: `link-secondary link-underline-opacity-25 link-underline-opacity-100-hover`

**Layout:**

- Headers: `<h2 class="mb-0">`
- Metadata: `text-secondary` with icons
- Avoid `alert` classes - use `border rounded p-2` instead
- Cards only for fighters in grids

### URL Patterns

- List views: plural noun (e.g., `/campaigns/`, `/lists/`)
- Detail views: singular noun with ID (e.g., `/campaign/<id>`, `/list/<id>`)
- Action views: noun-verb pattern (e.g., `/list/<id>/edit`, `/fighter/<id>/archive`)

### Testing Patterns

- Tests use pytest with `@pytest.mark.django_db` decorator
- Test functions at module level, not in classes
- Do not use Django's TestCase or SimpleTestCase - use plain pytest functions
- Use Django test client for view testing
- Static files must be collected before running tests that render templates
- The conftest.py configures tests to use StaticFilesStorage to avoid manifest issues

**IMPORTANT: Use existing fixtures from `gyrinx/conftest.py`.** Read the conftest before writing tests. Do not
manually create users, houses, fighters, campaigns, or lists inline when a fixture or factory already exists.

Key fixtures:

- `user` - creates user "testuser" with password "password"
- `make_user(username, password)` - factory for additional users
- `client` - Django test client (from pytest-django, use with `client.login()` or `client.force_login(user)`)
- `content_house` - a ContentHouse
- `content_fighter` - a ContentFighter with full statline
- `make_content_fighter(type, category, house, base_cost, **kwargs)` - factory for custom fighters
- `campaign` - an IN_PROGRESS campaign owned by `user`
- `make_campaign(name, **kwargs)` - factory for campaigns
- `make_list(name, **kwargs)` - factory for lists (owned by `user`, uses `content_house`)
- `make_list_fighter(list_, name, **kwargs)` - factory for fighters
- `list_with_campaign` - a list in CAMPAIGN_MODE with associated campaign
- `house` - backward-compat alias, creates a separate ContentHouse (prefer `content_house`)

When tests need multiple distinct users (e.g. campaign owner vs list owner), use `make_user` for the extra users
and override the `owner` kwarg on the factory fixtures.

### Security

- Run `bandit -c pyproject.toml -r .` to check for security issues in Python code
- The pre-commmit hooks also check for secrets in the codebase

### Git Workflow

- Before `git pull`, check the index
- Consider running `git stash`
- After a `stash` then `pull`, run `git stash pop` if necessary
- This is useful for keeping the claude local file up-to-date
- When writing PR descriptions, keep it simple and avoid "selling the feature" in the PR
- Use conventional commit prefixes for commit messages and PR titles:
  - `feat:` — new feature or capability
  - `fix:` — bug fix
  - `refactor:` — code restructuring with no behaviour change
  - `docs:` — documentation only
  - `test:` — adding or updating tests
  - `chore:` — maintenance, dependencies, CI, tooling
  - `perf:` — performance improvement
  - `style:` — formatting, whitespace (no logic change)

## Common File Locations

**Models:**

- `gyrinx/content/models.py` - Game content models
- `gyrinx/core/models/list.py` - User list/fighter models
- `gyrinx/core/models/campaign.py` - Campaign models

**Views:**

- `gyrinx/core/views/list.py` - List/fighter views
- `gyrinx/core/views/campaign.py` - Campaign views
- `gyrinx/core/views/vehicle.py` - Vehicle flow

**Templates:**

- `gyrinx/core/templates/core/` - Main templates
- `gyrinx/core/templates/core/includes/` - Reusable components

**Tests:**

- `gyrinx/core/tests/` - Core app tests
- `gyrinx/content/tests/` - Content app tests

## important-instruction-reminders

- Do what has been asked; nothing more, nothing less.
- NEVER create files unless they're absolutely necessary for achieving your goal.
- ALWAYS prefer editing an existing file to creating a new one.
- NEVER proactively create documentation files (\*.md) or README files. Only create documentation files if explicitly
  requested by the User.
- ALWAYS look up model definitions before using their fields or properties - do not assume field names or choices. Use
  the Read tool to check the actual model definition in the models.py file.
