"""Test utilities for optimizing test performance."""

from contextlib import contextmanager
from unittest.mock import patch

from django.db.models import signals


@contextmanager
def disable_signals_for_model(model_class):
    """
    Temporarily disable all signals for a given model class.

    This is useful in tests to avoid expensive signal handlers
    that aren't relevant to the test being run.
    """
    # Store original receivers
    original_receivers = {}
    signal_types = [
        signals.pre_save,
        signals.post_save,
        signals.pre_delete,
        signals.post_delete,
        signals.m2m_changed,
    ]

    for signal in signal_types:
        original_receivers[signal] = signal.receivers[:]
        # Remove receivers for this model
        signal.receivers = [
            r
            for r in signal.receivers
            if not (hasattr(r[1], "__self__") and r[1].__self__ == model_class)
        ]

    try:
        yield
    finally:
        # Restore original receivers
        for signal, receivers in original_receivers.items():
            signal.receivers = receivers


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
