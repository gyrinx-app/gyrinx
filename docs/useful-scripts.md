# Useful Scripts

This document provides an overview of commonly used scripts in the Gyrinx project.

## Development Scripts

### `scripts/fmt.sh`
Formats all code in the project including Python, JavaScript, SCSS, and Django templates.
```bash
./scripts/fmt.sh
```

### `scripts/test.sh`
Runs the full test suite using Docker for database services.
```bash
./scripts/test.sh
```

### `scripts/check_migrations.sh`
Checks for any migration issues or conflicts.
```bash
./scripts/check_migrations.sh
```

## Database Scripts

### `scripts/reset-migrations-to-main.sh`
Safely resets Django migration state to match the main branch. Useful when switching between branches with different migration histories.
```bash
./scripts/reset-migrations-to-main.sh
```

## Quality Assurance Scripts

### `scripts/fmt-check.sh`
Checks if code formatting is correct without making changes.
```bash
./scripts/fmt-check.sh
```

## Management Commands

These are Django management commands available through the `manage` command:

### `manage setupenv`
Sets up the development environment file (.env).
```bash
manage setupenv
```

### `manage ensuresuperuser`
Ensures a superuser exists for development.
```bash
manage ensuresuperuser
```

### `manage loaddata_overwrite`
Loads Django fixtures with overwrite capability.
```bash
manage loaddata_overwrite <fixture_name>
```
