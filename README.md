# gyrinx

[![GitBook](https://img.shields.io/static/v1?message=Documented%20on%20GitBook&logo=gitbook&logoColor=ffffff&label=%20&labelColor=5c5c5c&color=3F89A1)](https://www.gitbook.com/preview?utm_source=gitbook_readme_badge&utm_medium=organic&utm_campaign=preview_documentation&utm_content=link) ![Tests](https://github.com/gyrinx-app/content/actions/workflows/test.yaml/badge.svg)

This repository contains the Gyrinx Django application. The code for this
application is in the [`gyrinx`](./gyrinx) directory.

See the [docs](./docs) directory or the [Google Doc](https://docs.google.com/document/d/1seKmLBz2L4bGPeHfUxjgl39BJ27-O1Fb0MlJWfmLQFE/edit?tab=t.5q9jh7it524z)
for technical discussions. Access to the Google Doc is limited to contributors
and admins.

## Table of Contents

- [Technical Overview](#technical-overview)
- [Development](#development)
- [Setup](#setup)
- [Running the Django application](#running-the-django-application)
- [Building the UI](#building-the-ui)
- [Running Tests](#running-tests)
- [New data migration](#new-data-migration)
- [Debugging SQL](#debugging-sql)
- [Content library for development](#content-library-for-development)
- [Markdown Linting Rules](#markdown-linting-rules)

## Technical Overview

Gyrinx is a [Django](https://www.djangoproject.com/) application running in
[Google Cloud Platform](https://console.cloud.google.com/). It runs in
[Cloud Run](https://cloud.google.com/run), a serverless application platform,
with [Cloud SQL (specifically, Postgres)](https://cloud.google.com/sql/postgresql)
for data storage. [Cloud Build](https://cloud.google.com/build) is used to deploy
the application. The frontend is built with
[Bootstrap 5](https://getbootstrap.com/docs/5.0/getting-started/introduction/).

The code is hosted here on [GitHub](https://github.com/gyrinx-app). When new code
is pushed on main to the [gyrinx repo](https://github.com/gyrinx-app/gyrinx), it
is automatically deployed by Cloud Build. This includes running database
migrations. Code is tested automatically in
[GitHub Actions](https://github.com/gyrinx-app/gyrinx/actions).

Analytics are through
[Google Analytics](https://analytics.google.com/analytics/web/#/p470310767/reports/intelligenthome?params=_u..nav%3Dmaui).

Project tasks, issues and to-dos are managed in the
[Gyrinx GitHub Project](https://github.com/orgs/gyrinx-app/projects/1).

## Development

To run Gyrinx, you will need
[Docker](https://docs.docker.com/get-started/get-docker/) with
[Compose](https://docs.docker.com/compose/gettingstarted/). You'll also need a
recent Python version: [pyenv](https://github.com/pyenv/pyenv) is a good way to
manage installed Python versions.

There's a [devcontainer](https://code.visualstudio.com/docs/devcontainers/containers)
configured in this repo which should get you up and running too, perhaps via a
[Codespace](https://github.com/features/codespaces).

The Django `manage.py` file (in `scripts/`) is added to your shell by
`setuptools`, so you can just use `manage` from anywhere:

```bash
manage shell
```

## Setup

To set up the development environment, follow these steps:

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

1. Make sure your virtual environment is active & `pip` has up-to-date
   dependencies:

    ```bash
    . .venv/bin/activate
    pip install --editable .
    ```

2. Start the database ([Postgres](https://www.docker.com/blog/how-to-use-the-postgres-docker-official-image/#Using-Docker-Compose))
   and [pgadmin](https://www.pgadmin.org/):

    ```bash
    docker compose up -d
    ```

3. Run the migrations:

    ```bash
    manage migrate
    ```

4. Run the application:

    ```bash
    manage runserver
    ```

You can also run the application itself within Docker Compose by passing
`--profile app`, but this will not auto-reload the static files.

## Building the UI

The Python toolchain installs `nodeenv` which is then used to install `node` and
`npm` so we have a frontend toolchain.

To continuously rebuild the frontend (necessary for CSS updates from SASS):

```bash
npm run watch
```

## Running Tests

To run the test suite, we also use Docker (so there is a database to talk to):

```bash
./scripts/test.sh
```

For faster test execution using parallel workers:

```bash
./scripts/test.sh --parallel
# or
./scripts/test.sh -p
```

You can also run tests directly with pytest for more control:

```bash
# Run tests in parallel (requires pytest-xdist)
pytest -n auto

# Run tests with database reuse (faster for repeated runs)
pytest --reuse-db

# Combine both for maximum speed
pytest -n auto --reuse-db
```

You can also use the `pytest-watcher`:

```bash
ptw .
```

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

> **Note**
> This process is only available for trusted developers and admins.

1. **Export**: Run the `gyrinx-dumpdata` Cloud Run job in production to export
   content to the `gyrinx-app-bootstrap-dump` bucket
2. **Import**: Download `latest.json` from the bucket and use
   `manage loaddata_overwrite latest.json` to replace local content data

This process ensures we have access to the latest production content library. See
[docs/operations/content-data-management.md](docs/operations/content-data-management.md)
for details.
