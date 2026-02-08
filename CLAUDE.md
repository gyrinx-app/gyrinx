# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Documentation Guidelines

- **`.claude/notes/`** - Internal documentation and plans created by Claude to help with its work
- **`docs/`** - Documentation for humans (user guides, API docs, etc.)
- When creating analysis documents, optimization plans, or working notes, place them in `.claude/notes/`
- Only create user-facing documentation in `docs/` when explicitly requested

## Quick Reference (Most Important)

**Critical Commands:**

- Format code: `./scripts/fmt.sh`
- Run tests: `pytest -n auto`
- Django commands: Use `manage` (not `python manage.py`)
- Production shell: `manage prodshell` (read-only access to production database)
- Don't commit CSS files - they're auto-generated from SCSS
- The virtualenv is auto-activated for every Bash command by a `SessionStart` hook
  (`scripts/activate_venv_hook.sh`) that persists `.venv` into `CLAUDE_ENV_FILE`.
  There is no need to prefix commands with `. .venv/bin/activate &&`.

**Key Principles:**

- Server-rendered HTML, not SPA
- Mobile-first design
- Look up model definitions before use - don't assume field names
- Always validate redirect URLs with `safe_redirect`

## Infrastructure

- All our infra is in GCP europe-west2 (London)
- In prod, the user uploads bucket name is gyrinx-app-bootstrap-uploads

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

## Critical Workflow

### Before Starting

1. Create a new branch for the task: `git checkout -b issue-NAME`
2. For non-trivial features or bug fixes, use the **feature-planner** agent to create an implementation plan before
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
start and configures PostgreSQL directly (no Docker). Skip `docker compose` commands and use
`pytest` / `manage` directly — the helper scripts (`test.sh`, `migrate.sh`) detect the
environment automatically.

### Running the Application

```bash
# Start database services (local dev with Docker only)
docker compose up -d

# Run migrations
manage migrate

# Build frontend assets
npm run build

# Start Django development server
manage runserver

# Watch and rebuild CSS (run in separate terminal)
npm run watch
```

### Testing

```bash
# Run full test suite (uses Docker if available, otherwise runs directly)
./scripts/test.sh

# Run tests with pytest-watcher for continuous testing
ptw .

# Run specific test
pytest gyrinx/core/tests/test_models_core.py::test_basic_list

# Run tests with pytest directly (faster, uses existing database)
pytest

# Run tests in parallel using pytest-xdist (significant performance improvement)
pytest -n auto  # Uses all CPU cores
pytest -n 4     # Uses 4 workers

# Run tests with database reuse for faster execution
pytest --reuse-db

# Combine parallel execution with database reuse
pytest -n auto --reuse-db

# Collect static files before running tests (required for templates with static assets)
manage collectstatic --noinput

# Refresh test database after adding new migrations
# Use this when you see errors like "column X does not exist" in tests
pytest --create-db --migrations path/to/test_file.py
```

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
