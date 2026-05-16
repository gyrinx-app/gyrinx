# gyrinx

[![GitBook][gitbook-badge]][gitbook-link]
[![Tests][tests-badge]][tests-link]

[gitbook-badge]: https://img.shields.io/static/v1?message=Documented%20on%20GitBook&logo=gitbook&logoColor=ffffff&label=%20&labelColor=5c5c5c&color=3F89A1
[gitbook-link]: https://www.gitbook.com/preview?utm_source=gitbook_readme_badge&utm_medium=organic&utm_campaign=preview_documentation&utm_content=link
[tests-badge]: https://github.com/gyrinx-app/content/actions/workflows/test.yaml/badge.svg
[tests-link]: https://github.com/gyrinx-app/content/actions/workflows/test.yaml

This repository contains the Gyrinx Django application - a gang management tool
for Necromunda. The code for this application is in the [`gyrinx`](./gyrinx)
directory.

📚 **[Full Documentation](./docs/README.md)** - Technical overview, architecture,
and development guides.

## Prerequisites

Before getting started, you'll need:

- **Python 3.12+** - Use [pyenv](https://github.com/pyenv/pyenv) to manage versions
- **macOS with Homebrew** - The local dev scripts (`setup-local-postgres.sh`, `dev.sh`) are
  macOS-only. Linux contributors will need to set up PostgreSQL 16 manually and start it
  before running `dev.sh`
- **Git** - For version control

## Quick Start

```bash
# Clone and enter the repository
git clone git@github.com:gyrinx-app/gyrinx.git && cd gyrinx

# Set up Python environment
python -m venv .venv && . .venv/bin/activate
pip install --editable .

# Configure the application
manage setupenv

# Set up frontend toolchain
nodeenv -p && npm install && npm run build

# One-time: install and initialise local PostgreSQL (macOS via Homebrew)
./scripts/setup-local-postgres.sh

# Start the development server (DB fork + migrate + runserver + CSS watch)
./scripts/dev.sh
```

Visit http://localhost:8000 to see the application.

## Development

There's a [devcontainer](https://code.visualstudio.com/docs/devcontainers/containers)
configured in this repo which should get you up and running too, perhaps via a
[Codespace](https://github.com/features/codespaces).

The Django `manage.py` file (in `scripts/`) is added to your shell by
`setuptools`, so you can just use `manage` from anywhere:

```bash
manage shell
```

## Detailed Setup

The Quick Start above gets you running fast. For more detailed steps:

1. Clone the repository:

    ```bash
    git clone git@github.com:gyrinx-app/gyrinx.git
    cd gyrinx
    ```

2. Make sure you're using the right Python version:

    ```bash
    python --version # should be >= 3.12
    ```

    If you use `pyenv`, we have a `.python-version` file. If you have pyenv active
    in your environment, this file will automatically activate this version for you.

3. Create and activate a virtual environment:

    ```bash
    python -m venv .venv && . .venv/bin/activate
    ```

4. Install the project in editable mode so you can use the `manage` command:

    ```bash
    pip install --editable .
    ```

    `setuptools` will handle installing dependencies.

5. You should then be able to run Django `manage` commands. This one will set up
   your `.env` file:

    ```bash
    manage setupenv
    ```

    With that run, you'll have a `.env` file with a random and unique
    `SECRET_KEY` and `DJANGO_SUPERUSER_PASSWORD`:

    ```bash
    cat .env
    ```

6. Next, set up the frontend toolchain:

    Get `nodeenv` (installed by `pip` earlier) to install
    [node](https://nodejs.org/en) and [npm](https://www.npmjs.com/) in the
    virtual env.

    ```bash
    nodeenv -p
    ```

    Check it has worked (you might need to `deactivate` then
    `. .venv/bin/activate`):

    ```bash
    which node # should be /path/to/repo/.venv/bin/node
    which npm # should be /path/to/repo/.venv/bin/npm
    ```

7. Install the frontend dependencies:

    ```bash
    npm install
    ```

8. Build the frontend:

    ```bash
    npm run build
    ```

9. Install the pre-commit hooks:

    Before making any changes, make sure you've got pre-commit hooks installed.

    `pre-commit` is installed by pip.

    ```bash
    pre-commit install
    ```

## Running the Django application

The development workflow is a single command:

```bash
./scripts/dev.sh
```

This handles:

- Forking the per-worktree database from the `gyrinx_main` template (if missing)
- Running migrations
- Starting Django on a deterministic per-worktree port (8000 for `main`, 8100–9599 for child worktrees)
- Starting `npm run watch` for SCSS rebuilds

Useful flags:

```bash
./scripts/dev.sh --no-watch    # skip the CSS watcher
./scripts/dev.sh --reset-db    # drop and re-fork the worktree DB
```

If you've never set up local PostgreSQL on this machine, run
`./scripts/setup-local-postgres.sh` first.

> [!NOTE]
> For details on the per-worktree database model and how `gyrinx_main` is used as a template,
> see [docs/useful-scripts.md](docs/useful-scripts.md).

## Building the UI

The Python toolchain installs `nodeenv` which is then used to install `node` and
`npm` so we have a frontend toolchain.

To continuously rebuild the frontend (necessary for CSS updates from SASS):

```bash
npm run watch
```

## Running Tests

Tests run against your local PostgreSQL database. `setup-local-postgres.sh`
configures everything you need: `max_locks_per_transaction = 256` on the
cluster (required for pytest-xdist parallel syncdb), and a hook in
`.venv/bin/activate` that exports the per-worktree `DB_NAME` / `DB_CONFIG` /
`DJANGO_PORT` so `pytest` and `manage` target the right database.

> [!IMPORTANT]
> Re-run `source .venv/bin/activate` after switching worktrees. The hook
> reads `git rev-parse --show-toplevel` at activation time, not on every
> command. Symptom of forgetting: `pytest` fails with `FATAL: role "postgres"
> does not exist` (settings.py fell back to defaults because `DB_CONFIG` was
> unset or pinned to the wrong worktree).

The wrapper script is a thin convenience over `pytest`:

```bash
./scripts/test.sh                 # parallel (via pyproject addopts: -n auto)
./scripts/test.sh -n 0            # serial
```

Or invoke `pytest` directly — `pyproject.toml` already sets `-n auto
--nomigrations`, so the bare command runs the full suite in parallel and
rebuilds the test DB from current model definitions on every run:

```bash
pytest                            # full suite, parallel
pytest gyrinx/core/tests/         # one directory
pytest -k campaign                # by name
```

You can also use `pytest-watcher` for continuous testing:

```bash
ptw .
```

CI runs the same `pytest` invocation against a GitHub Actions service container
Postgres — see [.github/workflows/test.yaml](.github/workflows/test.yaml).

## New data migration

To create a new empty migration file for doing data migration:

```bash
manage makemigrations --empty content
```

## Debugging SQL

You can debug the SQL that Gyrinx is running using the
[Django Debug Toolbar](https://django-debug-toolbar.readthedocs.io/en/latest/)
that is installed.

You can also enable SQL logging by setting the `SQL_DEBUG` variable:

```text
SQL_DEBUG=True
```

## Content library for development

To test Gyrinx locally, you are really limited unless you have the content
library data available. This is because the content library is what provides the
data for the Gyrinx application to work with.

The content library is managed by the Gyrinx content team in production, and is
what makes Gyrinx useful.

Gyrinx uses a custom-ish data export/import process to manage content library
data from production, so you can test locally.

> [!NOTE]
> This process is only available for trusted developers and admins.

1. **Export**: Run the `gyrinx-dumpdata` Cloud Run job in production to export
   content to the `gyrinx-app-bootstrap-dump` bucket
2. **Import**: Download `latest.json` from the bucket and use
   `manage loaddata_overwrite latest.json` to replace local content data

This process ensures we have access to the latest production content library. See
[docs/operations/content-data-management.md](docs/operations/content-data-management.md)
for details.
