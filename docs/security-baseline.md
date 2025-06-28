# Security Baseline - Bandit Analysis

This document establishes the baseline security findings from the initial Bandit scan of the Gyrinx codebase. This baseline was created on 2025-06-28 and will be used to track improvements over time.

## Summary

- **Total Lines of Code**: 13,662
- **Total Issues Found**: 31
- **High Severity**: 3
- **Medium Severity**: 10
- **Low Severity**: 18

## High Severity Issues

### 1. Weak Hash Functions (CWE-327)
- **B324**: Use of weak MD5 hash in `gyrinx/content/management/utils.py:125`
  - Purpose: Generating stable UUIDs from strings
  - Risk: MD5 is cryptographically broken and should not be used for security purposes

- **B324**: Use of weak SHA1 hash in `gyrinx/core/templatetags/custom_tags.py:164,170`
  - Purpose: Cache key generation
  - Risk: SHA1 is deprecated for security use

## Medium Severity Issues

### 1. Potential XSS Vulnerabilities (CWE-79/80)
- **B703/B308**: Multiple uses of Django's `mark_safe()` function
  - Locations:
    - `gyrinx/core/templatetags/color_tags.py:19,42,44`
    - `gyrinx/core/templatetags/custom_tags.py:204`
    - `gyrinx/pages/templatetags/pages.py:235`
  - Risk: May expose cross-site scripting vulnerabilities if user input is not properly sanitized

## Low Severity Issues

### 1. Weak Random Number Generation (CWE-330)
- **B311**: Use of standard `random` module for:
  - Dice rolling in games (`core/forms/advancement.py:266`, `core/models/campaign.py:269`)
  - Random skill selection (`core/views/list.py:2783`)
  - Game mechanics (`core/views/__init__.py:131-133`, `core/views/list.py:2299-2300,3178`)
  - Note: These are all game-related, not security-critical

### 2. Subprocess Security (CWE-78)
- **B404**: Import of subprocess module in:
  - `gyrinx/core/management/commands/update_claude_secrets.py`
  - `scripts/screenshot.py`

- **B607**: Starting processes with partial paths:
  - `security` command for keychain access
  - `git` command for repository operations
  - `gh` command for GitHub CLI operations
  - `playwright` command for browser automation

### 3. Error Handling
- **B110**: Try/except/pass blocks in `gyrinx/pages/views.py:50,93`
  - Risk: Silent error handling may hide important issues

## Excluded Findings

The following Bandit checks are excluded in our configuration:
- **B101**: Use of assert statements (needed for tests)
- **B601**: Paramiko calls (not used in this project)
- **B603**: Subprocess without shell=True (reviewed case-by-case)

## Recommendations for Future PRs

1. **High Priority**:
   - Replace MD5 with SHA256 for UUID generation (with backwards compatibility)
   - Replace SHA1 with SHA256 for cache keys
   - Review all `mark_safe()` usage to ensure proper input sanitization

2. **Medium Priority**:
   - Use `secrets` module instead of `random` for any security-sensitive randomization
   - Add full paths for subprocess commands or validate environment
   - Improve error handling to log exceptions instead of silently passing

3. **Low Priority**:
   - Document why certain `mark_safe()` usages are safe
   - Add security comments for subprocess usage explaining safety measures

## Next Steps

This baseline establishes our current security posture. Future pull requests should:
1. Not introduce new security issues
2. Gradually address existing issues based on priority
3. Update this document when issues are resolved

## Running Bandit

To run Bandit and compare against this baseline:

```bash
# Install dependencies
pip install "bandit[toml]"

# Run scan
bandit -c pyproject.toml -r .

# Generate reports
bandit -c pyproject.toml -r . -f json -o bandit-report.json
bandit -c pyproject.toml -r . -f txt -o bandit-report.txt
```
