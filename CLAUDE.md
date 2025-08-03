# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference (Most Important)

**Critical Commands:**

- Format code: `./scripts/fmt.sh`
- Run tests: `pytest -n auto`
- Django commands: Use `manage` (not `python manage.py`)
- Don't commit CSS files - they're auto-generated from SCSS

**Key Principles:**

- Server-rendered HTML, not SPA
- Mobile-first design
- Look up model definitions before use - don't assume field names
- Always validate redirect URLs with `safe_redirect`

## Infrastructure

- All our infra is in GCP europe-west2 (London)
- In prod, the user uploads bucket name is gyrinx-app-bootstrap-uploads

## Critical Workflow (Before Push)

1. Format code: `./scripts/fmt.sh`
2. Run tests: `pytest -n auto`
3. Fix any failing tests
4. Commit and push changes

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

### Running the Application

```bash
# Start database services
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
# Run full test suite (uses Docker for database)
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
- **Security**: Always validate return URLs using `safe_redirect` when accepting redirect URLs from user input to prevent open redirect vulnerabilities

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

### Security

- Run `bandit -c pyproject.toml -r .` to check for security issues in Python code
- The pre-commmit hooks also check for secrets in the codebase

### Git Workflow

- Before `git pull`, check the index
- Consider running `git stash`
- After a `stash` then `pull`, run `git stash pop` if necessary
- This is useful for keeping the claude local file up-to-date
- When writing PR descriptions, keep it simple and avoid "selling the feature" in the PR

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

# important-instruction-reminders

- Do what has been asked; nothing more, nothing less.
- NEVER create files unless they're absolutely necessary for achieving your goal.
- ALWAYS prefer editing an existing file to creating a new one.
- NEVER proactively create documentation files (\*.md) or README files. Only create documentation files if explicitly requested by the User.
- ALWAYS look up model definitions before using their fields or properties - do not assume field names or choices. Use the Read tool to check the actual model definition in the models.py file.
