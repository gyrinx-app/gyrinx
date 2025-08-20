"""Test utilities for optimizing test performance."""

from contextlib import contextmanager
from unittest.mock import patch


@contextmanager
def disable_cost_cache_updates():
    """
    Disable expensive cost cache updates during tests.

    The cost cache updates are expensive operations that recalculate
    the entire list cost on every save. This is unnecessary for most
    tests and significantly slows down test execution.
    """
    with patch("gyrinx.core.models.list.List.update_cost_cache"):
        yield


@contextmanager
def fast_test_mode():
    """
    Enable fast test mode that disables expensive operations.

    This combines multiple optimizations:
    - Disables cost cache updates
    - Could be extended with other optimizations as needed
    """
    with disable_cost_cache_updates():
        yield
