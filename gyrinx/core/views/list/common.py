"""Common utilities for list views."""

from django.shortcuts import get_object_or_404

from gyrinx.core.models.list import List


def get_clean_list_or_404(model_or_queryset, *args, **kwargs):
    """
    Get a List object and ensure its cached facts are fresh.

    If the list is marked as dirty (e.g., due to content cost changes),
    this function will refresh the cached facts before returning.

    When passed the List model class directly, this function automatically
    applies the with_latest_actions() prefetch to enable the facts system
    for consistent rating display across all views.

    Args:
        model_or_queryset: A model class (List) or queryset to filter
        *args, **kwargs: Additional arguments passed to get_object_or_404

    Returns:
        List: The list object with fresh cached facts

    Usage:
        get_clean_list_or_404(List, id=id, owner=request.user)
        get_clean_list_or_404(List.objects.filter(...), id=id)
    """
    # If passed the List model directly, apply with_latest_actions() prefetch
    # to enable can_use_facts for consistent rating display
    if model_or_queryset is List:
        model_or_queryset = List.objects.with_latest_actions()

    obj = get_object_or_404(model_or_queryset, *args, **kwargs)

    if obj.dirty:
        obj.facts_from_db(update=True)

    return obj
