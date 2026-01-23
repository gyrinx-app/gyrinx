"""Shared refund calculation utilities for handlers."""

from django.core.exceptions import ValidationError

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

    For negative-cost equipment (e.g., gene-smithing), removing it will cost
    credits (the inverse of the gain received when adding it). This requires
    having enough credits available.

    Args:
        lst: The list
        cost: The item cost being removed (can be negative for items that grant credits)
        request_refund: Whether user requested refund

    Returns:
        Tuple of (credits_delta, refund_applied)

    Raises:
        ValidationError: If removing negative-cost equipment and insufficient credits
    """
    if not lst.is_campaign_mode:
        return 0, False

    # For negative-cost equipment, removing it costs credits (the gain must be paid back)
    if cost < 0:
        # Removing negative-cost equipment costs |cost| credits
        removal_cost = abs(cost)
        if lst.credits_current < removal_cost:
            raise ValidationError(
                f"Insufficient credits to remove this equipment. "
                f"Removing it will cost {removal_cost}¢, "
                f"but you only have {lst.credits_current}¢ available."
            )
        # credits_delta is negative because we're deducting credits
        return -removal_cost, True

    # For normal positive-cost equipment, refund if requested
    refund_applied = request_refund
    credits_delta = cost if refund_applied else 0
    return credits_delta, refund_applied
