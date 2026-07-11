"""Handler for fighter kill operations in campaign mode."""

from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from gyrinx.core.cost.pinning import pin_assignment
from gyrinx.core.cost.propagation import Delta, propagate_from_fighter
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
)
from gyrinx.tracing import traced


@dataclass
class FighterKillResult:
    """Result of killing a fighter in campaign mode."""

    fighter: ListFighter
    fighter_cost_before: int
    equipment_count: int
    persistent_count: int
    list_action: Optional[ListAction]
    campaign_action: Optional[CampaignAction]
    description: str


@traced("handle_fighter_kill")
@transaction.atomic
def handle_fighter_kill(
    *,
    user,
    lst: List,
    fighter: ListFighter,
) -> FighterKillResult:
    """
    Handle fighter death in campaign mode.

    This handler performs the following operations atomically:
    1. Captures before values for ListAction
    2. Finds stash fighter
    3. Transfers non-persistent equipment to stash by cloning each item with
       its acquisition receipt (pins) intact, so the gear keeps its price in
       the stash's context rather than re-pricing at catalog (#1826 Phase 9)
    4. Deletes the transferred (non-persistent) assignments
    5. Marks fighter as DEAD
    6. Sets fighter cost_override = 0
    7. Creates UPDATE_FIGHTER ListAction for death
    8. Creates CampaignAction if in campaign

    The fighter's cost goes from X to 0, reducing rating by X.
    Equipment transfers from fighter to stash don't change overall wealth,
    but equipment is preserved in the stash for potential re-use.

    Equipment in a category flagged ``persistent`` (see
    ``ContentEquipmentCategory.persistent``) is the exception: it stays
    attached to the dead fighter rather than transferring to the stash. It is
    neither moved nor refunded — its value is absorbed into the rating
    reduction (the dead fighter contributes 0 via ``should_have_zero_cost``).

    Args:
        user: User performing the kill
        lst: List containing the fighter
        fighter: Fighter being killed (must not be stash, must be campaign mode)

    Returns:
        FighterKillResult with all operation details

    Raises:
        ValueError: If fighter is stash or list is not in campaign mode
    """
    # Validate preconditions
    if not lst.is_campaign_mode:
        raise ValueError("Fighters can only be killed in campaign mode")

    if fighter.is_stash:
        raise ValueError("Cannot kill the stash")

    # Capture BEFORE values for ListAction
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Calculate fighter cost before death (includes equipment). Fetch
    # pack-aware: cost_int() on a plain instance resolves accessories/profiles/
    # upgrades through the default (pack-excluding) managers and would drop
    # pack-scoped components (#1933), so the reduction below would leave the
    # dead fighter's cache non-zero. with_related_data() prefetches via
    # all_content(), matching the cache the propagation deltas maintained.
    fighter_cost_before = (
        ListFighter.objects.with_related_data().get(pk=fighter.pk).cost_int()
    )

    # Find the stash fighter for this list
    stash_fighter = lst.listfighter_set.filter(content_fighter__is_stash=True).first()

    # Partition equipment: non-persistent gear transfers to the stash for
    # re-use, while equipment in a persistent category stays attached to the
    # (now dead) fighter. Persistent equipment is conceptually tied to the
    # fighter it was issued to (e.g. Impressive Leadership) — it neither moves
    # to the stash nor is refunded as credits; it simply remains on the corpse.
    equipment_assignments = list(fighter.listfighterequipmentassignment_set.all())

    def _is_persistent(assignment):
        # category is nullable; equipment with no category is never persistent.
        category = assignment.content_equipment.category
        return bool(category and category.persistent)

    def _is_linked_child(assignment):
        # Assignments auto-created from an equipment-equipment link (the child
        # half of e.g. "Magic Lamp brings a Genie"). They must NOT be moved
        # independently: transferring the parent re-creates the child on the
        # stash via the create_related_objects post-save signal. Moving the
        # child as well would duplicate it, and because the copy doesn't carry
        # linked_equipment_parent it loses its structural zero-cost and reprices
        # to catalog — inflating stash wealth. ListFighter.clone() skips these
        # for exactly the same reason. Deleting the parent below cascades to the
        # original child (delete_related_objects_pre_delete), so nothing is
        # stranded on the corpse.
        return assignment.linked_equipment_parent_id is not None

    # Persistent gear stays on the fighter regardless of whether a stash
    # exists. Non-persistent gear can only be transferred if there is a stash
    # to receive it; without one nothing moves (matching the original
    # no-stash behaviour), so transferred_count reflects actual transfers.
    # Linked children are never transferred directly (see _is_linked_child).
    persistent_count = sum(1 for a in equipment_assignments if _is_persistent(a))
    to_transfer = (
        [
            a
            for a in equipment_assignments
            if not _is_persistent(a) and not _is_linked_child(a)
        ]
        if stash_fighter
        else []
    )
    transferred_count = len(to_transfer)

    equipment_cost = 0
    if to_transfer:
        # Move each item to the stash by cloning it with its acquisition
        # receipt intact (#1826 Phase 9). Two steps per item:
        #
        #   1. Belt-and-braces: pin any row still UNPINNED, resolving at the
        #      DYING fighter's prices — the last moment this acquisition
        #      context exists. After the Phase 8 backfill this is a no-op, but
        #      it makes the ordering non-load-bearing.
        #   2. Clone from a fresh refetch (so the copy carries the just-written
        #      receipt, not the stale pre-pin instance state). clone() copies
        #      the amount, attribution, and state verbatim — plus cost/total
        #      overrides and every component through-row, pack-scoped included.
        #
        # Because the receipt travels with the gear, it prices identically on
        # the stash without any blanket total freeze, so the #1826
        # death-repricing bug cannot recur.
        clones = []
        for assignment in to_transfer:
            pin_assignment(assignment)
            source = ListFighterEquipmentAssignment.objects.get(pk=assignment.pk)
            clones.append(
                source.clone(
                    list_fighter=stash_fighter,
                    preserve_from_default_assignment=True,
                )
            )

        # The stash gains exactly what its new rows cache. clone() recomputes
        # each in the stash context pack-aware (reading the copied receipts), so
        # this total equals what a later recompute produces. With pins it also
        # equals the dying fighter's valuation of the same gear, so the transfer
        # is wealth-neutral. Persistent items are NOT here: their value is
        # absorbed into the rating reduction below.
        equipment_cost = sum(clone.rating_current for clone in clones)

        # Delete only the transferred assignments from the dead fighter;
        # persistent assignments stay attached and remain visible on the card.
        ListFighterEquipmentAssignment.objects.filter(
            id__in=[a.id for a in to_transfer]
        ).delete()

    # Mark fighter as dead and set cost to 0
    fighter.injury_state = ListFighter.DEAD
    fighter.cost_override = 0
    fighter.save(update_fields=["injury_state", "cost_override"])

    # Propagate the cost reduction (fighter_cost_before → 0)
    propagate_from_fighter(fighter, Delta(delta=-fighter_cost_before, list=lst))

    # Bump the stash fighter's cached rating (and the list's stash book) by
    # the equipment value we just moved into it. Without this the stash
    # fighter's rating_current stays stale, and any later reassignment-out
    # from the stash drives it negative — which then 500s the next refresh
    # because list.stash_current is a PositiveIntegerField.
    if stash_fighter and equipment_cost:
        propagate_from_fighter(stash_fighter, Delta(delta=equipment_cost, list=lst))

    # Build description. Persistent equipment stays with the fighter and is
    # called out separately so the user can see what did and didn't move.
    if transferred_count and persistent_count:
        equipment_desc = (
            f" {transferred_count} equipment transferred to stash,"
            f" {persistent_count} stayed with the fighter."
        )
    elif transferred_count:
        equipment_desc = " All equipment transferred to stash."
    elif persistent_count:
        equipment_desc = (
            f" {persistent_count} equipment stayed with the fighter."
            if persistent_count > 1
            else " Equipment stayed with the fighter."
        )
    else:
        equipment_desc = " No equipment to transfer."
    description = f"{fighter.name} was killed ({fighter_cost_before}¢).{equipment_desc}"

    # Create UPDATE_FIGHTER ListAction for death
    # Rating decreases by fighter's full cost (base + equipment)
    # Stash increases by equipment value (transferred there)
    # Net wealth change = -fighter_base_cost (equipment preserved in stash)
    list_action = lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=fighter.id,
        description=description,
        list_fighter=fighter,
        rating_delta=-fighter_cost_before,
        stash_delta=equipment_cost,
        credits_delta=0,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
    )

    # Create CampaignAction if this list is part of a campaign
    campaign_action = None
    if lst.campaign:
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            description=f"Death: {fighter.name} was killed",
            outcome=f"{fighter.name} is permanently dead.{equipment_desc}",
        )

    return FighterKillResult(
        fighter=fighter,
        fighter_cost_before=fighter_cost_before,
        equipment_count=transferred_count,
        persistent_count=persistent_count,
        list_action=list_action,
        campaign_action=campaign_action,
        description=description,
    )
