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

5. To check it has worked, run the `schema` command:

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

6. Set up the frontend toolchain:

    Get `nodeenv` (installed by pip) to install node and npm in the virtual env.

    ```bash
    nodeenv -p
    ```

    Check it has worked (you might need to `deactivate` then `. .venv/bin/activate`):

    ```bash
    which node # should be /path/to/repo/.venv/bin/node
    which npm # should be /path/to/repo/.venv/bin/npm
    ```

7. Build the frontend

    ```
    npm run build
    ```

8. Install the pre-commit hooks

    Before making any changes, make sure you've got pre-commit hooks installed.

    `pre-commit` is installed by pip.

    ```bash
    pre-commit install
    ```

9. Set up your environment

    Before making any changes, set up your local `.env` file.

    ```bash
    mange setupenv
    ```

## Running the Django application

Make sure your virtual environment is active and you've run `pip install --editable .`.

```
`DJANGO_SETTINGS_MODULE`=gyrinx.settings_dev manage runserver
```

We use `DJANGO_SETTINGS_MODULE=gyrinx.settings_dev` to select a Django settings file that is suitable for development.

## Building the UI

The Python toolchain installs `nodeenv` which is then used to install `node` and `npm` so we have a frontend toolchain.

## Running Tests

To run the test suite:

```bash
pytest
```

## Checking data against schema

Make sure your virtual environment is active and you've run `pip install --editable .`.

To check the data files against their schema, simply run:

```bash
schema
```
