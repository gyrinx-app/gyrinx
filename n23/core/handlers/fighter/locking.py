"""Row locks shared by fighter death and bulk post-battle updates."""

from n23.core.models.list import List, ListFighter


def lock_list_fighters(*, lst: List) -> None:
    """Lock a gang's fighters in PK order inside the caller's transaction.

    Include the stash and linked fighters, since death can move equipment or
    update their caches. Acquire these locks before writing the parent list.
    """
    list(
        ListFighter.objects.filter(list=lst)
        .order_by("pk")
        .select_for_update(of=("self",), no_key=True)
        .values_list("pk", flat=True)
    )
