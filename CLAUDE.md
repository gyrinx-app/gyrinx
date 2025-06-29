# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Infrastructure

- All our infra is in GCP europe-west2 (London)
- In prod, the user uploads bucket name is gyrinx-app-bootstrap-uploads

## Development Commands

### Environment Setup

```bash
# Setup virtual environment and install dependencies
python -m venv .venv && . .venv/bin/activate
pip install --editable .

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
pytest gyrinx/core/tests/test_models_core.py::TestListModel::test_list_creation

# Run tests with pytest directly (faster, uses existing database)
pytest

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

- Always run `./scripts/fmt.sh` after making code changes to format everything (Python, JS, SCSS, templates, etc.)
- **IMPORTANT**: This includes running `./scripts/fmt.sh` after editing CLAUDE.md itself to ensure consistent formatting
- Alternatively, you can run formatters individually:
    - `ruff format` and `ruff check --fix` for Python
    - `npm run fmt` for JS, SCSS, JSON, YAML, Markdown
    - `djlint --profile=django --reformat .` for Django templates
- When building something new, create a branch for it and open a pull request at the end
- Use the screenshot tool when making UI changes and add the screenshot to the PR description. Mobile UI is important to show as we are mobile-first.
- Always run the tests and ensure they are passing before pushing from CI/GitHub Action context
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

- Game data stored in YAML files with JSON schema validation (deprecated - now in database)
- Content managed through Django admin interface
- Complex equipment/weapon relationship modeling
- Equipment ordering handled by manager (category name, then equipment name)

### Template Patterns

- Use `{% extends "core/layouts/base.html" %}` for full-page layouts
- Use `{% extends "core/layouts/page.html" %}` for simple content pages
- Back buttons use `{% include "core/includes/back.html" with url=target_url text="Back Text" %}`
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

### Code Quality

- Run `./scripts/fmt.sh` to format all code (Python, JS, SCSS, templates, etc.) in one go
- This script runs:
    - `ruff format` and `ruff check --fix` for Python formatting and linting
    - `npm run fmt` for Markdown, YAML, JSON, SCSS, and JavaScript formatting
    - `djlint --profile=django --reformat .` for Django template formatting
- Always run `./scripts/fmt.sh` after making code changes

### Git Workflow

- Before `git pull`, check the index
- Consider running `git stash`
- After a `stash` then `pull`, run `git stash pop` if necessary
- This is useful for keeping the claude local file up-to-date
- When writing PR descriptions, keep it simple and avoid "selling the feature" in the PR

### UI Documentation

When making UI changes, use the automated screenshot utility to capture before/after screenshots:

```bash
# Install Playwright if not already installed
pip install playwright

# Capture before screenshots (Chromium will be installed automatically)
python scripts/screenshot.py core:campaign --before --args <campaign_id>

# Make your UI changes...

# Capture after screenshots
python scripts/screenshot.py core:campaign --after --args <campaign_id>

# Capture multiple viewports
python scripts/screenshot.py core:list --viewports desktop,tablet,mobile --args <list_id>

# Capture specific element only
python scripts/screenshot.py core:campaign --selector ".campaign-header" --args <id>
```

The automated script will:

1. Use Playwright to launch a headless browser
2. Authenticate using Django test client
3. Navigate to the specified URL
4. Capture full-page screenshots
5. Save to `ui_archive/` with comparison markdown
6. Support multiple viewports and themes

Screenshots are organized as:

- `ui_archive/<url_name>_<label>_<viewport>_<timestamp>.png`
- `ui_archive/<url_name>_<label>_<viewport>_latest.png`
- `ui_archive/<url_name>_comparison.md` for before/after pairs

The `ui_archive/` directory is gitignored to keep the repository clean.

### Changelog Management

The project uses an automated changelog update script that leverages the `llm` CLI tool to analyze commits and maintain the CHANGELOG.md file.

```bash
# Update the changelog with recent commits
./scripts/update_changelog.sh

# Update a specific changelog file
./scripts/update_changelog.sh path/to/changelog.md
```

The script will:

1. Detect the last date in the existing changelog
2. Find all commits since that date
3. Use LLM to analyze commits and generate properly formatted entries
4. Group commits by date and category (Features, Fixes, Documentation, etc.)
5. Create a backup of the original file before updating

**Important for Claude Code**: When working on this repository, check the last date in CHANGELOG.md. If it's more than 2 days old, proactively offer to run the changelog update script to ensure the changelog stays current with recent development activity.

### Fighter Advancement System

The advancement system allows fighters to spend XP in campaign mode. Key implementation details:

1. **Model Structure**: The `ListFighterAdvancement` model tracks advancements with fields for:
    - `advancement_type` - Either "stat" or "skill"
    - `stat_increased` - Which stat was improved (for stat advancements)
    - `skill` - Which skill was gained (for skill advancements)
    - `xp_cost` - How much XP was spent
    - `cost_increase` - How much the fighter's credit cost increased

2. **Multi-Step Form Flow**: Uses a wizard-style flow with forms in `core/forms/advancement.py`:
    - Step 1: Choose dice rolling vs manual selection
    - Step 2: Select advancement type (stat/skill)
    - Step 3: Choose specific stat or skill
    - Step 4: Confirmation

3. **Important Notes**:
    - Advancements only work in campaign mode (`List.CAMPAIGN_MODE`)
    - XP is tracked with `xp_current` (available) and `xp_total` (lifetime)
    - Stat improvements with "+" values (like WS 4+) improve by reducing the number
    - Skills are restricted to fighter's primary/secondary categories
    - Uses HTMX for dynamic form updates without page reloads

4. **Common Issues**:
    - If you see advancement models with `description`, `stat_mod`, `dice_count` fields, that's from an older version before the rebuild
    - The current system uses `advancement_type` with separate `stat_increased` and `skill` fields
    - Form validation happens in the form's `clean()` method, not just the model's `clean()`
