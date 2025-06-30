# Test Performance Improvements with pytest-xdist

## Overview

This document outlines the performance improvements achieved by introducing `pytest-xdist` for parallel test execution in the Gyrinx project.

## Current State Analysis

- **Total tests**: 451 test cases
- **Test distribution**:
  - Core app: 45 test files
  - Content app: 14 test files  
  - Pages app: 1 test file
  - API app: 1 test file
- **Current execution**: Sequential (one test at a time)
- **Parallelization**: None configured

## Changes Implemented

### 1. Added pytest-xdist to requirements.txt

```txt
pytest-xdist==3.6.1
```

### 2. Parallel Test Execution

With pytest-xdist installed, you can now run tests in parallel:

```bash
# Use all available CPU cores
pytest -n auto

# Use specific number of workers (e.g., 4)
pytest -n 4

# Use number of workers equal to CPU count
pytest -n $(nproc)
```

## Expected Performance Improvements

Based on typical Django test suite characteristics:

- **Sequential execution**: All 451 tests run one after another
- **Parallel execution (4 cores)**: ~3-4x speedup expected
- **Parallel execution (8 cores)**: ~5-6x speedup expected

The actual speedup depends on:
- Number of CPU cores available
- Test isolation and database transaction overhead
- Amount of I/O-bound vs CPU-bound operations

## Additional Optimizations

### 1. Database Reuse (pytest-django feature)

Since `pytest-django==4.11.1` is already installed, you can also use:

```bash
# Reuse test database between runs
pytest --reuse-db

# Create new database only when needed
pytest --reuse-db --create-db
```

### 2. Combined Usage

For maximum performance:

```bash
# Parallel execution + database reuse
pytest -n auto --reuse-db

# Run specific app tests in parallel
pytest -n auto gyrinx/core/tests/
```

## CI/CD Configuration

For GitHub Actions or other CI systems:

```yaml
# Example GitHub Actions configuration
- name: Run tests
  run: |
    pytest -n auto --durations=20 -v
```

## Monitoring Test Performance

Use pytest's built-in duration reporting:

```bash
# Show 20 slowest tests
pytest --durations=20

# Show all test durations
pytest --durations=0
```

## Best Practices

1. **Ensure test isolation**: Tests must not depend on execution order
2. **Use transactions**: Django's TestCase handles this automatically
3. **Avoid shared state**: Don't use module-level variables that tests modify
4. **Monitor resource usage**: More workers isn't always better

## Troubleshooting

If tests fail with parallel execution:

1. Run tests sequentially to isolate the issue:
   ```bash
   pytest -n 0  # or just pytest
   ```

2. Run specific test in isolation:
   ```bash
   pytest path/to/test_file.py::test_function -vv
   ```

3. Check for test interdependencies or shared state issues

## Conclusion

Adding pytest-xdist enables significant test performance improvements through parallel execution. Combined with database reuse, this can reduce test execution time by 60-80% on multi-core systems.