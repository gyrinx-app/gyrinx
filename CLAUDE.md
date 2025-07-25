# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Infrastructure

- All our infra is in GCP europe-west2 (London)
- In prod, the user uploads bucket name is gyrinx-app-bootstrap-uploads

## Development Commands

The Django management command `manage` is used to run various tasks in the Gyrinx application. It is made available by setuptools. It provides a convenient way to execute commands without needing to specify the Django project settings each time. When running management commands, you MUST use `manage` directly.

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

## Development Workflow

- When building something new, create a branch for it and open a pull request at the end
- Always run `./scripts/fmt.sh` after making code changes to format everything (Python, JS, SCSS, templates, etc.)
- **IMPORTANT**: This includes running `./scripts/fmt.sh` after editing CLAUDE.md itself to ensure consistent formatting
- Alternatively, you can run formatters individually:
    - `ruff format` and `ruff check --fix --unsafe-fixes` for Python
    - `npm run fmt` for JS, SCSS, JSON, YAML, Markdown
    - `djlint --profile=django --reformat .` and `djlint --profile=django --lint --check .` for Django templates formatting
- **CRITICAL FOR CI/GITHUB ACTIONS**: Before committing and pushing changes, you MUST:
    1. Run the formatting script: `./scripts/fmt.sh`
    2. Run the tests: `pytest -n auto`
    3. Check that ALL tests pass - if any tests fail, fix them before proceeding
    4. Only after tests pass, commit and push your changes
- **CRITICAL**: When running in CI or a GitHub action, you MUST COMMIT AND PUSH BEFORE FINISHING. This is critical: otherwise, work is lost.

## Architecture Overview

### Django Apps Structure

- **`content`** - Game data models (fighters, equipment, weapons, skills, houses)
    - Contains official Necromunda rulebook content
    - Uses django-simple-history for change tracking
    - Complex relationships between game entities

- **`core`** - User lists and gang management
    - List/ListFighter models for user-created gangs
    - Equipment assignment system with costs and modifications
    - Campaign functionality

- **`pages`** - Static content and waiting list system
    - Flat pages with visibility controls
    - User registration waiting list

- **`api`** - Minimal webhook handling for external integrations

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

- **Content → Core**: ContentFighter/ContentEquipment used as templates for user ListFighter assignments
- **Virtual Equipment System**: ListFighterEquipmentAssignment handles complex equipment with profiles, accessories, upgrades
- **Cost Calculation**: Dynamic pricing based on fighter type, equipment lists, and modifications
- **Historical Tracking**: All models use simple-history for audit trails
    - Middleware tracks user for web requests automatically
    - Use `save_with_user(user=user)` for manual user tracking (defaults to owner if not provided)
    - Use `Model.objects.create_with_user(user=user, ...)` for creating with history (defaults to owner)
    - Use `Model.bulk_create_with_history(objs, user=user)` for bulk operations with history (defaults to each object's owner)

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

### UI Layout Patterns (List/Campaign View Style)

The list view establishes the standard UI pattern for detail pages:

1. **Header Structure**:
    - Title uses `<h2 class="mb-0">` (or h1 for main pages)
    - Metadata in a horizontal stack (`hstack`) with `text-secondary` styling
    - Cost/status badges aligned to the right using `ms-md-auto`
    - Status badges use contextual colors (e.g., `bg-success` for active states)

2. **Metadata Row**:
    - Uses `d-flex flex-column flex-sm-row` for responsive stacking
    - Each metadata item in `<div class="text-secondary">` with icon + text
    - Links use `link-secondary link-underline-opacity-25 link-underline-opacity-100-hover`
    - Items separated by `column-gap-2`

3. **Action Buttons**:
    - Positioned right with `ms-sm-auto`
    - Primary actions use `btn btn-primary btn-sm`
    - Secondary actions use `btn btn-secondary btn-sm`
    - More options in a dropdown with `btn-group` and three-dots icon

4. **Information Callouts**:
    - Avoid `alert` classes
    - Use simple text with `text-secondary` or `text-muted`
    - For separated content, use `border rounded p-2` instead of alerts
    - Keep messaging minimal and inline where possible

5. **Button Patterns**:
    - All action buttons use `btn-sm` size
    - Primary actions (Add/Create) use `btn-primary`
    - Edit/modify actions use `btn-secondary`
    - Destructive actions use `btn-danger`
    - View/navigation use `btn-outline-secondary`

6. **Card Layout**:
    - Avoid using `card`
    - Use card for fighters and things that appear in a grid: nowhere else

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

# important-instruction-reminders

- Do what has been asked; nothing more, nothing less.
- NEVER create files unless they're absolutely necessary for achieving your goal.
- ALWAYS prefer editing an existing file to creating a new one.
- NEVER proactively create documentation files (\*.md) or README files. Only create documentation files if explicitly requested by the User.
- ALWAYS look up model definitions before using their fields or properties - do not assume field names or choices. Use the Read tool to check the actual model definition in the models.py file.
