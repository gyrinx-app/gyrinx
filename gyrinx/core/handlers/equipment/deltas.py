"""Shared delta arithmetic for equipment component handlers.

Part of the cost-pinning programme (#1826); fixes #1925.
"""

from gyrinx.core.models.list import ListFighterEquipmentAssignment


def component_delta(
    assignment: ListFighterEquipmentAssignment, raw_component_delta: int
) -> int:
    """The assignment-level book delta for a component add/remove/change.

    Definitionally equal to ``assignment.cost_int()`` after the mutation minus
    ``assignment.cost_int()`` before it — computed without a second,
    staleness-prone ``cost_int()`` call:

    - With no ``total_cost_override``, ``cost_int()`` is the sum of the
      components, so changing one component moves it by exactly that
      component's delta.
    - With a ``total_cost_override`` set, ``cost_int()`` ignores components
      entirely, so the true book delta is **zero** (#1925): propagating the
      raw component cost would move the caches while a recompute snaps them
      back to the override, silently discarding value.

    Credits are a separate, real transaction and are NOT gated by this —
    a user who buys an accessory onto a fixed-total assignment still pays for
    it; the fixed total simply doesn't move until they update it.
    """
    return 0 if assignment.has_total_cost_override() else raw_component_delta
