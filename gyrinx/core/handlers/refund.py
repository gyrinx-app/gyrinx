"""Shared refund calculation utilities for handlers."""

from gyrinx.core.models.list import List


def calculate_refund_credits(
    *,
    lst: List,
    cost: int,
    request_refund: bool,
) -> tuple[int, bool]:
    """
    Calculate credits delta based on refund request and campaign mode.

    Refunds are ONLY allowed in campaign mode.

    Args:
        lst: The list
        cost: The item cost being removed
        request_refund: Whether user requested refund

    Returns:
        Tuple of (credits_delta, refund_applied)
    """
    refund_applied = request_refund and lst.is_campaign_mode
    credits_delta = cost if refund_applied else 0
    return credits_delta, refund_applied
