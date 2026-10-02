"""Shared row-lock order for gang fighter and cache writes."""

from collections.abc import Iterable
from uuid import UUID


def lock_fighter_rows_for_lists(*, list_ids: Iterable[UUID]) -> None:
    """Lock complete rosters in gang/PK order within the caller's transaction."""
    from n23.core.models.list.fighter import ListFighter

    list(
        ListFighter.objects.filter(list_id__in=list_ids)
        .order_by("list_id", "pk")
        .select_for_update(of=("self",), no_key=True)
        .values_list("pk", flat=True)
    )


def lock_lists_for_fighter_write(*, list_ids: Iterable[UUID]) -> None:
    """Lock rosters before their parent rows; keep foreign-key inserts compatible."""
    from n23.core.models.list.list import List

    list_ids = tuple(list_ids)
    lock_fighter_rows_for_lists(list_ids=list_ids)
    list(
        List.objects.filter(pk__in=list_ids)
        .order_by("pk")
        .select_for_update(of=("self",), no_key=True)
        .values_list("pk", flat=True)
    )
