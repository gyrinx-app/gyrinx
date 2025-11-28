# Security Baseline - Bandit Analysis

This document provides context for the Bandit security baseline established on 2025-06-28.

## Overview

The Gyrinx codebase uses [Bandit](https://bandit.readthedocs.io/) for automated security scanning. The baseline captures the current state of security findings to:

1. Track only new security issues in CI/CD
2. Document accepted security risks
3. Plan security improvements over time

## Baseline Files

- **`bandit/bandit-baseline.json`** - Machine-readable baseline for CI comparison (committed to git)
- **`bandit/bandit-baseline.txt`** - Human-readable report with detailed findings (committed to git)

## Running Bandit

```bash
# Run scan with baseline comparison (as CI does)
bandit -c pyproject.toml -r . --baseline bandit/bandit-baseline.json

# Generate new baseline files
bandit -c pyproject.toml -r . -f json -o bandit/bandit-baseline.json
bandit -c pyproject.toml -r . -f txt -o bandit/bandit-baseline.txt
```

## Updating the Baseline

When security issues are resolved or new acceptable findings are added:

1. Run Bandit to generate new baseline files
2. Review the changes carefully
3. Commit both JSON and TXT files with explanation

## Configuration

Bandit is configured in `pyproject.toml`:

### Excluded Directories

- `.venv`, `.git`, `__pycache__` - Infrastructure directories
- `*/migrations/*` - Django migrations (auto-generated)
- `*/tests/*` - Test files (assertions expected)
- `node_modules` - Node.js dependencies

### Skipped Checks

- **B101** (`assert_used`): Assertions are used in tests
- **B601** (`paramiko_calls`): Paramiko is not used
- **B603** (`subprocess_without_shell_equals_true`): Reviewed case-by-case

## Additional Security Practices

### Input Validation

- Use `safe_redirect()` helper for all redirect URLs to prevent open redirect vulnerabilities
- Validate user input at form level using Django forms
- Sanitise HTML content with appropriate filters

### Authentication

- Django's built-in authentication system with session management
- reCAPTCHA verification for registration (when enabled)
- Password validation using Django validators

### Pre-commit Hooks

Security checks run automatically on commit via pre-commit:

- `detect-private-key` - Prevents committing private keys
- `bandit` - Runs security scan on Python files

## Related Documentation

- [SECURITY.md](../SECURITY.md) - Security policy and vulnerability reporting
