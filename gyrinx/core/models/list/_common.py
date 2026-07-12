import logging

from django.core.exceptions import ValidationError

from gyrinx.models import (
    FighterCategoryChoices,
)

logger = logging.getLogger(__name__)
pylist = list


# Define allowed category overrides
ALLOWED_CATEGORY_OVERRIDES = [
    FighterCategoryChoices.LEADER,
    FighterCategoryChoices.CHAMPION,
    FighterCategoryChoices.GANGER,
    FighterCategoryChoices.JUVE,
    FighterCategoryChoices.PROSPECT,
    FighterCategoryChoices.SPECIALIST,
]


def validate_category_override(value):
    """Validator to ensure category_override is in allowed list."""
    if value and value not in ALLOWED_CATEGORY_OVERRIDES:
        raise ValidationError(
            f"Category override must be one of: {', '.join([c.label for c in ALLOWED_CATEGORY_OVERRIDES])}"
        )


def bulk_mark_assignments_dirty(assignments) -> None:
    """Mark a set of assignments, their fighters, and those fighters' lists dirty.

    Equivalent in effect to calling ``assignment.set_dirty(save=True)`` on every
    assignment in ``assignments`` (which propagates assignment -> fighter -> list),
    but using three bulk ``UPDATE``s instead of O(rows) individual statements.

    This is the hot path for content-cost-change fan-out: a popular base item can
    have tens of thousands of assignments, and the per-row chain issued up to
    ~3 UPDATEs each. ``QuerySet.update()`` bypasses signals/history exactly like
    the per-instance ``set_dirty`` did, so semantics are preserved.

    ``assignments`` may be any queryset of ListFighterEquipmentAssignment; the
    caller is responsible for the ``archived=False`` (and any other) filtering.
    """
    from gyrinx.core.models.list.fighter import ListFighter
    from gyrinx.core.models.list.list import List

    # Capture ids before any UPDATE so the membership snapshots are stable.
    fighter_ids = set(assignments.values_list("list_fighter_id", flat=True))
    list_ids = set(
        ListFighter.objects.filter(pk__in=fighter_ids).values_list("list_id", flat=True)
    )
    assignments.update(dirty=True)
    ListFighter.objects.filter(pk__in=fighter_ids).update(dirty=True)
    List.objects.filter(pk__in=list_ids).update(dirty=True)


def bulk_mark_fighters_dirty(fighters) -> None:
    """Mark a set of fighters and their lists dirty.

    Equivalent to calling ``fighter.set_dirty(save=True)`` on every fighter in
    ``fighters`` (which propagates fighter -> list), using two bulk ``UPDATE``s.

    ``fighters`` may be any queryset of ListFighter; the caller is responsible
    for the ``archived=False`` (and any other) filtering.
    """
    from gyrinx.core.models.list.fighter import ListFighter
    from gyrinx.core.models.list.list import List

    fighter_ids = set(fighters.values_list("pk", flat=True))
    list_ids = set(
        ListFighter.objects.filter(pk__in=fighter_ids).values_list("list_id", flat=True)
    )
    ListFighter.objects.filter(pk__in=fighter_ids).update(dirty=True)
    List.objects.filter(pk__in=list_ids).update(dirty=True)
