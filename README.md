# gyrinx

Core content library & application for Gyrinx

![Tests](https://github.com/gyrinx-app/content/actions/workflows/test.yaml/badge.svg)

This repository contains the Gynrix Django application. The code for this application is in the [`gyrinx`](./gyrinx/) directory.

See the [design](./design/) directory or the [Notion](https://www.notion.so/Technical-Design-13315de8366180c19a45f5201460b804) for technical discussions.

The `manage.py` file (in `scripts/`) is added to your shell by `setuptools`, so you can just use `manage` from anywhere:

```bash
manage shell
```

## Getting content into gyrinx

> Work in progress!

The content library was static data, but we've switched to using the database directly. More documentaiton soon.

# Development

To run Gyrinx, you will need [Docker](https://docs.docker.com/get-started/get-docker/) with [Compose](https://docs.docker.com/compose/gettingstarted/). You'll also need a recent Python version: [pyenv](https://github.com/pyenv/pyenv) is a good way to manage installed Python versions.

There's a [devcontainer](https://code.visualstudio.com/docs/devcontainers/containers) configured in this repo which should get you up and running too, perhaps via a [Codespace](https://github.com/features/codespaces).

## Setup

To set up the development environment, follow these steps:

1. Clone the repository:

    ```bash
    git clone git@github.com:gyrinx-app/content.git
    cd content
    ```

2. Make sure you're using the right python version:

    ```bash
    python --version # should be >= 3.12
    ```

3. Create and activate a virtual environment:

    ```bash
    python -m venv .venv && . .venv/bin/activate
    ```

4. Install the project in editable mode so you can use the `schema` command:

    ```bash
    pip install --editable .
    ```

    `setuptools` will handle installing dependencies.

5. You should then be able to run Django `manage` commands. This one will set up your `.env` file:

    ```bash
    manage setupenv
    ```

    WIth that run, you'll have a `.env` file with a random and unique `SECRET_KEY` and `DJANGO_SUPERUSER_PASSWORD`:

    ```bash
    cat .env
    ```

6. To check other things are worked, run the `schema` command:

    ```bash
    schema
    ```

    You should see the schema being checked...

    ```
    Checking schema...
    Found these ruleset directories:
    - content/necromunda-2018

    Checking content/necromunda-2018...
    Gathering schema files from content/necromunda-2018/schema...
    ```

7. Next, set up the frontend toolchain:

    Get `nodeenv` (installed by `pip` earlier) to install [node](https://nodejs.org/en) and [npm](https://www.npmjs.com/) in the virtual env.

    ```bash
    nodeenv -p
    ```

    Check it has worked (you might need to `deactivate` then `. .venv/bin/activate`):

    ```bash
    which node # should be /path/to/repo/.venv/bin/node
    which npm # should be /path/to/repo/.venv/bin/npm
    ```

8. Install the frontend dependencies

    ```
    npm install
    ```

9. Build the frontend

    ```
    npm run build
    ```

10. Install the pre-commit hooks

    Before making any changes, make sure you've got pre-commit hooks installed.

    `pre-commit` is installed by pip.

    ```bash
    pre-commit install
    ```

## Running the Django application

1. Make sure your virtual environment is active & `pip` has up-to-date dependencies:

    ```bash
    . .venv/bin/activate
    pip install --editable .
    ```

2. Start the database ([Postgres](https://www.docker.com/blog/how-to-use-the-postgres-docker-official-image/#Using-Docker-Compose)) and [pgadmin](https://www.pgadmin.org/):

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

You can also run the application itself within Docker Compose by passing `--profile app`, but this will not auto-reload the static files.

## Building the UI

The Python toolchain installs `nodeenv` which is then used to install `node` and `npm` so we have a frontend toolchain.

To continuously rebuild the frontend (necessary for CSS updates from SASS):

```bash
npm run watch
```

## Running Tests

To run the test suite, we also use Docker (so there is a database to talk to):

```bash
./scripts/test.sh
```

## Checking data against schema

Make sure your virtual environment is active and you've run `pip install --editable .`.

To check the data files against their schema, simply run:

```bash
schema
```

# Django Admin

## New data migration

To create a new empty migration file for doing data migration:

```bash
manage makemigrations --empty content
```

This template might be useful for importing stuff from content:

```python
from django.db import migrations

from gyrinx.models import *


def do_migration(apps, schema_editor):
    ContentEquipment = apps.get_model("content", "ContentEquipment")

    ...


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0014_contentweaponprofile_cost_sign_and_more"),
    ]

    operations = [migrations.RunPython(do_migration)]
```
