# gyrinx

Core content library & application for Gyrinx

![Tests](https://github.com/gyrinx-app/content/actions/workflows/test.yaml/badge.svg)

---

# Content

The content library is kept in the [`content`](./content/) directory.

It contains [`yaml`](https://en.m.wikipedia.org/wiki/YAML) "data" files that contain the core content relevant to the game, and [JSON schema files](https://json-schema.org/) that specifiy the valid shapes of the data files.

## Structure

The directory structure is:

```
content/
    [ruleset]/
        data/
            [anything].yaml
        schema/
            [type].schema.json
```

# Application

This repository also contains the Gynrix Django application. The code for this application is in the [`gyrinx`](./gyrinx/) directory.

The `manage.py` file (in `scripts/`) is added to your shell by `setuptools`, so you can just use `manage` from anywhere:

```bash
manage shell
```

## Getting content into gyrinx

_Note: this is TODO!_

The content library has a non-technical-user-friendly-ish (room for improvement here) static data structure that will be infrequently updated by contributors. Gyrinx is a live application with a running database. How do we connect these two?

-   The Django `manage gyriximport` command ingests the content library, transforms it, and writes it to the (production, staging...) database
-   It uses the current git sha, branch and tags to annotate the data with a version
-   The app can then be updated to enable the new content version

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

6. To further check it worked, do a `--dry-run` import:

    ```bash
    manage gyrinximport content --dry-run
    ```

7. Set up the frontend toolchain:

    Get `nodeenv` (installed by pip) to install node and npm in the virtual env.

    ```bash
    nodeenv -p
    ```

    Check it has worked (you might need to `deactivate` then `. .venv/bin/activate`):

    ```bash
    which node # should be /path/to/repo/.venv/bin/node
    which npm # should be /path/to/repo/.venv/bin/npm
    ```

8. Build the frontend

    ```
    npm run build
    ```

9. Install the pre-commit hooks

    Before making any changes, make sure you've got pre-commit hooks installed.

    `pre-commit` is installed by pip.

    ```bash
    pre-commit install
    ```

## Running the Django application

Make sure your virtual environment is active and you've run `pip install --editable .`.

```
manage runserver
```

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
