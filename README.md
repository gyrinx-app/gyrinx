# content

Core content library for Gyrinx

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

# Development

## Setup

To set up the development environment, follow these steps:

1. Clone the repository:

    ```bash
    git clone git@github.com:gyrinx-app/content.git
    cd content
    ```

2. Create and activate a virtual environment:

    ```bash
    python -m venv .venv && . .venv/bin/activate
    ```

3. Install the project in editable mode so you can use the `schema` command:

    ```bash
    pip install --editable .
    ```

    `setuptools` will handle installing dependencies.

4. To check it has worked, run the `schema` command:

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

## Running Tests

To run the test suite:

```bash
python -m pytest
```

## Checking data against schema

Make sure your virtual environment is active and you've run `pip install --editable .`.

To check the data files against their schema, simply run:

```bash
schema
```
