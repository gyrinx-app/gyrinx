"""
Shared utilities for content model cost change signals.

These helpers are used by signal handlers in models.py and models_/expansion.py
to detect cost changes and mark affected lists as dirty.
"""

from gyrinx.models import is_int


def get_old_cost(model_class, instance, cost_field="cost"):
    """
    Get the old cost value for an instance being updated.

    Args:
        model_class: The Django model class to query.
        instance: The model instance being saved.
        cost_field: The name of the cost field (default: "cost").

    Returns:
        The old cost as an integer, or None if this is a new instance.
        CharField cost values are converted to integers using is_int().
    """
    if instance._state.adding or not instance.pk:
        return None

    # Use all_content() where available so pack-scoped rows still resolve —
    # the default ContentManager excludes pack items, and treating a pack row
    # as DoesNotExist here made every cost-change signal think it was a new
    # instance, so pack price corrections never swept (#1930). Mirrors the
    # same fallback in gyrinx/core/tasks.propagate_content_cost_change.
    manager = model_class._default_manager
    base_qs = (
        manager.all_content() if hasattr(manager, "all_content") else manager.all()
    )

    try:
        old_instance = base_qs.only(cost_field).get(pk=instance.pk)
        old_value = getattr(old_instance, cost_field)
        # Handle CharField cost fields (e.g., ContentEquipment)
        if isinstance(old_value, str):
            return int(old_value) if is_int(old_value) else 0
        return old_value or 0
    except model_class.DoesNotExist:
        return None


def get_new_cost(instance, cost_field="cost"):
    """
    Get the new cost value for an instance being saved.

    Args:
        instance: The model instance being saved.
        cost_field: The name of the cost field (default: "cost").

    Returns:
        The new cost as an integer. CharField cost values are converted
        to integers using is_int().
    """
    new_value = getattr(instance, cost_field)
    # Handle CharField cost fields (e.g., ContentEquipment)
    if isinstance(new_value, str):
        return int(new_value) if is_int(new_value) else 0
    return new_value or 0
