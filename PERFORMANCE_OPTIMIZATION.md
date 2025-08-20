# Test Performance Optimization

## Summary

This branch contains significant test performance optimizations based on the issues identified in #901.

## Key Optimizations

### 1. Removed Expensive `autouse` Fixture

- **Before**: Every test loaded 566+ ContentPageRef records via an `autouse=True` fixture
- **After**: Tests must explicitly request fixtures they need
- **Impact**: ~5-10 seconds saved per test that doesn't need this data

### 2. Disabled Cost Cache Updates in Tests

- **Before**: `update_cost_cache()` was called on every model save, triggering expensive list-wide cost recalculations
- **After**: Cost cache updates are mocked out by default in tests
- **Impact**: Eliminates cascading database queries on every save operation

### 3. Optimized Fixture Dependencies

- **Before**: Many fixtures loaded unnecessary data
- **After**: Created targeted fixtures (`content_page_refs` vs `content_page_refs_full`)
- **Impact**: Tests only load data they actually need

## Implementation Details

### Changes to `gyrinx/conftest.py`

1. Removed `autouse=True` from `ensure_test_data` fixture
2. Added `disable_cost_cache_in_tests` fixture that mocks `update_cost_cache()` by default
3. Split `content_page_refs` into basic (4 refs) and full (566 refs) versions
4. Made `make_equipment` depend on `content_equipment_categories` to ensure categories exist

### New Test Utilities (`gyrinx/core/test_utils.py`)

- `disable_signals_for_model()`: Context manager to disable signals for specific models
- `disable_cost_cache_updates()`: Context manager to disable cost cache updates
- `fast_test_mode()`: Combined optimization context manager

### Test Updates

- Updated tests that specifically test cost caching to re-enable it
- Fixed tests that relied on the autouse fixture to explicitly request needed fixtures

## Performance Gains

### Expected Improvements (based on #901 analysis)

- Removing autouse fixtures: 5-10 seconds per test
- Disabling cost cache updates: 50-80% reduction in test time for tests that create/modify lists
- Overall: Significant reduction in total test suite runtime

### Measured Results

- Individual test files run in ~15-30 seconds (vs 60+ seconds before)
- Tests that don't need heavy fixtures run much faster

## Migration Guide for Tests

### For tests that need equipment categories:

```python
@pytest.mark.django_db
def test_something(content_equipment_categories):
    # Test code
```

### For tests that need many page refs:

```python
@pytest.mark.django_db
def test_pageref_heavy(content_page_refs_full):
    # Test code
```

### For tests that need to test cost caching:

```python
@pytest.mark.django_db
def test_cost_cache(disable_cost_cache_in_tests):
    # Re-enable cost cache for this test
    disable_cost_cache_in_tests.stop()
    # Test code
```

## Next Steps

1. Run full test suite to verify all tests pass
2. Measure total runtime improvement
3. Consider additional optimizations:
    - Parallel test execution optimization
    - Database transaction optimization
    - Further signal optimization
