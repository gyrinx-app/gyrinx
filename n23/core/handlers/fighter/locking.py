"""Row locks shared by fighter and equipment writes."""

from n23.core.models.list import List, ListFighter, ListFighterEquipmentAssignment
from n23.core.models.list.locking import lock_fighter_rows_for_lists


def lock_list_fighters(*, lst: List) -> None:
    """Lock a gang's fighters in PK order inside the caller's transaction.

    Include the stash and linked fighters, since death can move equipment or
    update their caches. Acquire these locks before writing the parent list.
    """
    lock_fighter_rows_for_lists(list_ids=[lst.pk])


def lock_list_for_fighter_write(*, lst: List) -> None:
    """Lock the roster before its parent, then refresh the gang's balances."""
    lock_list_fighters(lst=lst)
    lst.refresh_from_db(
        from_queryset=List.objects.select_for_update(of=("self",), no_key=True)
    )


def prepare_equipment_write(
    *, lst: List, fighter: ListFighter, assignment: ListFighterEquipmentAssignment
) -> tuple[ListFighter, ListFighterEquipmentAssignment]:
    """Refresh equipment-write inputs after acquiring the shared row locks."""
    lock_list_for_fighter_write(lst=lst)
    assignment = ListFighterEquipmentAssignment.objects.with_related_data().get(
        pk=assignment.pk
    )
    fighter = ListFighter.objects.get(pk=fighter.pk, list=lst)
    assignment.list_fighter = fighter
    return fighter, assignment
