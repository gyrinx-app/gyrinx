# CI Test Performance Configuration

## GitHub Actions Configuration

To enable parallel test execution in CI, update your workflow file:

```yaml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: |
        pip install --editable .
    
    - name: Run tests in parallel
      run: |
        # Run tests with parallelization
        pytest -n auto --durations=20 -v
```

## Timeout Configuration

Since parallel tests should run faster, you can set appropriate timeouts:

```yaml
    - name: Run tests
      timeout-minutes: 10  # Adjust based on your test suite
      run: |
        pytest -n auto --durations=20 -v
```

## Database Configuration for CI

For CI environments without Docker, consider using SQLite:

```yaml
    - name: Run tests with SQLite
      env:
        DJANGO_SETTINGS_MODULE: gyrinx.test_settings
      run: |
        pytest -n auto
```