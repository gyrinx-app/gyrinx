"""
Signal handlers for content model cost changes.

This module contains:
- Pre-save handlers that detect cost changes and mark objects dirty
- Post-save handlers that create CONTENT_COST_CHANGE actions
- Helper function for creating cost change actions
"""

import logging

from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from gyrinx.content.signals import MISSING, get_new_cost, get_old_cost, get_old_field
from gyrinx.models import format_cost_display
from gyrinx.tracing import traced

from .equipment import (
    AUTO_EQUIPMENT_CATEGORY_BY_FIGHTER_CATEGORY,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentUpgrade,
)
from .equipment_list import (
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListUpgrade,
    ContentFighterEquipmentListWeaponAccessory,
)
from .expansion import ContentEquipmentListExpansionItem
from .fighter import ContentFighter
from .house import ContentFighterHouseOverride
from .weapon import ContentWeaponAccessory, ContentWeaponProfile

logger = logging.getLogger(__name__)


# =============================================================================
# Pre-save signal handlers
#
# These signals detect when cost fields change on content models and mark
# affected core objects (assignments, fighters, lists) as dirty.
# =============================================================================


@receiver(
    pre_save, sender=ContentEquipment, dispatch_uid="content_equipment_cost_change"
)
@traced("signal_content_equipment_cost_change")
def handle_equipment_cost_change(sender, instance, **kwargs):
    """
    Mark affected assignments dirty when ContentEquipment.cost changes.
    """
    old_cost = get_old_cost(sender, instance, "cost")
    if old_cost is None:
        return  # New instance, no existing assignments

    new_cost = get_new_cost(instance, "cost")
    if old_cost != new_cost:
        instance._cost_changed = True  # Flag for post_save to create actions
        # The pre-change value rides to the async task: amount-snapshot
        # (DERIVED) receipts are maintained by delta, which needs it.
        instance._old_cost_for_propagation = old_cost
        instance.set_dirty()


@receiver(
    pre_save, sender=ContentFighter, dispatch_uid="content_fighter_base_cost_change"
)
@traced("signal_content_fighter_base_cost_change")
def handle_fighter_base_cost_change(sender, instance, **kwargs):
    """
    Mark affected list fighters dirty when ContentFighter.base_cost changes.
    """
    old_cost = get_old_cost(sender, instance, "base_cost")
    if old_cost is None:
        return  # New instance, no existing list fighters

    new_cost = get_new_cost(instance, "base_cost")
    if old_cost != new_cost:
        instance._cost_changed = True  # Flag for post_save to create actions
        # The pre-change value rides to the async task: amount-snapshot
        # (DERIVED) receipts are maintained by delta, which needs it.
        instance._old_cost_for_propagation = old_cost
        instance.set_dirty()


@receiver(
    pre_save, sender=ContentWeaponProfile, dispatch_uid="content_profile_cost_change"
)
@traced("signal_content_profile_cost_change")
def handle_profile_cost_change(sender, instance, **kwargs):
    """
    Mark affected assignments dirty when ContentWeaponProfile.cost changes.
    """
    old_cost = get_old_cost(sender, instance, "cost")
    if old_cost is None:
        return  # New instance, no existing assignments

    new_cost = get_new_cost(instance, "cost")
    if old_cost != new_cost:
        instance._cost_changed = True  # Flag for post_save to create actions
        # The pre-change value rides to the async task: amount-snapshot
        # (DERIVED) receipts are maintained by delta, which needs it.
        instance._old_cost_for_propagation = old_cost
        instance.set_dirty()


@receiver(
    pre_save,
    sender=ContentWeaponAccessory,
    dispatch_uid="content_accessory_cost_change",
)
@traced("signal_content_accessory_cost_change")
def handle_accessory_cost_change(sender, instance, **kwargs):
    """
    Mark affected assignments dirty when ContentWeaponAccessory.cost or
    cost_expression changes.
    """
    old_cost = get_old_cost(sender, instance, "cost")
    if old_cost is None:
        return  # New instance, no existing assignments

    new_cost = get_new_cost(instance, "cost")
    changed = old_cost != new_cost
    if not changed:
        # A cost_expression edit reprices every assignment carrying this
        # accessory just as surely as a flat-cost edit, but was previously
        # unwatched: nothing went dirty and no audit action was recorded.
        old_expression = get_old_field(sender, instance, "cost_expression")
        changed = (
            old_expression is not MISSING and old_expression != instance.cost_expression
        )

    if changed:
        instance._cost_changed = True  # Flag for post_save to create actions
        # The pre-change value rides to the async task: amount-snapshot
        # (DERIVED) receipts are maintained by delta, which needs it.
        instance._old_cost_for_propagation = old_cost
        instance.set_dirty()


@receiver(
    pre_save, sender=ContentEquipmentUpgrade, dispatch_uid="content_upgrade_cost_change"
)
@traced("signal_content_upgrade_cost_change")
def handle_upgrade_cost_change(sender, instance, **kwargs):
    """
    Mark affected assignments dirty when ContentEquipmentUpgrade.cost changes.
    """
    old_cost = get_old_cost(sender, instance, "cost")
    if old_cost is None:
        return  # New instance, no existing assignments

    new_cost = get_new_cost(instance, "cost")
    if old_cost != new_cost:
        instance._cost_changed = True  # Flag for post_save to create actions
        # The pre-change value rides to the async task: amount-snapshot
        # (DERIVED) receipts are maintained by delta, which needs it.
        instance._old_cost_for_propagation = old_cost
        instance.set_dirty()


@receiver(
    pre_save,
    sender=ContentFighterEquipmentListItem,
    dispatch_uid="content_equipment_list_item_cost_change",
)
@traced("signal_content_equipment_list_item_cost_change")
def handle_equipment_list_item_cost_change(sender, instance, **kwargs):
    """
    Mark affected assignments dirty when ContentFighterEquipmentListItem.cost changes.

    This model provides cost overrides for equipment on specific fighter types.
    """
    old_cost = get_old_cost(sender, instance, "cost")
    if old_cost is None:
        return  # New instance, no existing assignments

    new_cost = get_new_cost(instance, "cost")
    if old_cost != new_cost:
        instance._cost_changed = True  # Flag for post_save to create actions
        # The pre-change value rides to the async task: amount-snapshot
        # (DERIVED) receipts are maintained by delta, which needs it.
        instance._old_cost_for_propagation = old_cost
        instance.set_dirty()


@receiver(
    pre_save,
    sender=ContentFighterEquipmentListWeaponAccessory,
    dispatch_uid="content_equipment_list_accessory_cost_change",
)
@traced("signal_content_equipment_list_accessory_cost_change")
def handle_equipment_list_accessory_cost_change(sender, instance, **kwargs):
    """
    Mark affected assignments dirty when ContentFighterEquipmentListWeaponAccessory.cost changes.

    This model provides cost overrides for weapon accessories on specific fighter types.
    """
    old_cost = get_old_cost(sender, instance, "cost")
    if old_cost is None:
        return  # New instance, no existing assignments

    new_cost = get_new_cost(instance, "cost")
    if old_cost != new_cost:
        instance._cost_changed = True  # Flag for post_save to create actions
        # The pre-change value rides to the async task: amount-snapshot
        # (DERIVED) receipts are maintained by delta, which needs it.
        instance._old_cost_for_propagation = old_cost
        instance.set_dirty()


@receiver(
    pre_save,
    sender=ContentFighterEquipmentListUpgrade,
    dispatch_uid="content_equipment_list_upgrade_cost_change",
)
@traced("signal_content_equipment_list_upgrade_cost_change")
def handle_equipment_list_upgrade_cost_change(sender, instance, **kwargs):
    """
    Mark affected assignments dirty when ContentFighterEquipmentListUpgrade.cost changes.

    This model provides cost overrides for equipment upgrades on specific fighter types.
    """
    old_cost = get_old_cost(sender, instance, "cost")
    if old_cost is None:
        return  # New instance, no existing assignments

    new_cost = get_new_cost(instance, "cost")
    if old_cost != new_cost:
        instance._cost_changed = True  # Flag for post_save to create actions
        # The pre-change value rides to the async task: amount-snapshot
        # (DERIVED) receipts are maintained by delta, which needs it.
        instance._old_cost_for_propagation = old_cost
        instance.set_dirty()


@receiver(
    pre_save,
    sender=ContentFighterHouseOverride,
    dispatch_uid="content_fighter_house_override_cost_change",
)
@traced("signal_content_fighter_house_override_cost_change")
def handle_fighter_house_override_cost_change(sender, instance, **kwargs):
    """
    Mark affected fighters dirty when ContentFighterHouseOverride.cost changes.

    This model provides cost overrides for fighters in specific houses.
    """
    old_cost = get_old_cost(sender, instance, "cost")
    if old_cost is None:
        return  # New instance, no existing fighters

    new_cost = get_new_cost(instance, "cost")
    if old_cost != new_cost:
        instance._cost_changed = True  # Flag for post_save to create actions
        # The pre-change value rides to the async task: amount-snapshot
        # (DERIVED) receipts are maintained by delta, which needs it.
        instance._old_cost_for_propagation = old_cost
        instance.set_dirty()


@receiver(
    pre_save,
    sender=ContentEquipmentListExpansionItem,
    dispatch_uid="content_expansion_item_cost_change",
)
@traced("signal_content_expansion_item_cost_change")
def handle_expansion_item_cost_change(sender, instance, **kwargs):
    """
    Mark affected assignments dirty when ContentEquipmentListExpansionItem.cost changes.

    This model provides cost overrides for equipment in expansion lists.
    """
    old_cost = get_old_cost(sender, instance, "cost")
    if old_cost is None:
        return  # New instance, no existing assignments

    new_cost = get_new_cost(instance, "cost")
    changed = old_cost != new_cost
    if not changed:
        # The int helpers coerce None to 0, but on expansion items None means
        # "use the base price" and 0 means "free" — a 0 <-> None edit DOES
        # reprice and must sweep. Compare the raw values to catch it.
        old_raw = get_old_field(sender, instance, "cost")
        changed = old_raw is not MISSING and old_raw != instance.cost

    if changed:
        instance._cost_changed = True  # Flag for post_save to create actions
        # The pre-change value rides to the async task: amount-snapshot
        # (DERIVED) receipts are maintained by delta, which needs it.
        instance._old_cost_for_propagation = old_cost
        instance.set_dirty()


# =============================================================================
# Post-save signal handlers
#
# These handlers run after content models are saved. If the pre_save handler
# detected a cost change (via _cost_changed flag), they create ListAction
# records for affected lists.
# =============================================================================


def _affected_list_ids(instance, include_archived: bool = False) -> list:
    """Return the distinct ids of lists affected by a content cost change.

    Shared by the synchronous enqueue path (which snapshots each affected list's
    pre-change costs) and the async task (which recalculates and records actions),
    so both agree on exactly which lists a content instance touches. Returns an
    empty list for unknown model types.

    ``include_archived`` widens the set to lists reachable only through
    archived rows — the amount-rewriting sweep domain (#1826 §4.7: archived
    rows are swept too, or a later unarchive resurrects a stale amount).
    The default (live rows only) is the action/dirty domain and stays in
    lockstep with the model set_dirty() filters.
    """
    from gyrinx.core.models.list import (
        ListFighter,
        ListFighterEquipmentAssignment,
    )

    model_name = instance.__class__.__name__
    live = {} if include_archived else {"archived": False}

    if model_name == "ContentEquipment":
        # Equipment directly assigned to fighters
        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(
                content_equipment=instance, **live
            )
            .values_list("list_fighter__list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentWeaponProfile":
        # Weapon profiles on assignments
        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(
                weapon_profiles_field=instance, **live
            )
            .values_list("list_fighter__list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentWeaponAccessory":
        # Weapon accessories on assignments
        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(
                weapon_accessories_field=instance, **live
            )
            .values_list("list_fighter__list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentEquipmentUpgrade":
        # Equipment upgrades on assignments. SINGLE stacks reprice this rung
        # and every higher rung (mirror of ContentEquipmentUpgrade.set_dirty).
        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(
                upgrades_field__in=instance.same_stack_from_position(),
                **live,
            )
            .values_list("list_fighter__list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentFighter":
        # Fighter templates used by list fighters (including legacy)
        list_ids = (
            ListFighter.objects.filter(
                Q(content_fighter=instance) | Q(legacy_content_fighter=instance),
                **live,
            )
            .values_list("list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentFighterHouseOverride":
        # Fighter house overrides - find fighters using this override's fighter in this house
        list_ids = (
            ListFighter.objects.filter(
                Q(content_fighter=instance.fighter)
                | Q(legacy_content_fighter=instance.fighter),
                list__content_house=instance.house,
                **live,
            )
            .values_list("list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentFighterEquipmentListItem":
        # Equipment list items - cost overrides for equipment on specific
        # fighter types, plus rows pinned to this item (base or profile),
        # mirroring ContentFighterEquipmentListItem.set_dirty exactly.
        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(
                Q(
                    Q(list_fighter__content_fighter=instance.fighter)
                    | Q(list_fighter__legacy_content_fighter=instance.fighter)
                    | Q(list_fighter__promoted_content_fighter=instance.fighter),
                    content_equipment=instance.equipment,
                )
                | Q(pinned_equipment_list_item=instance)
                | Q(profile_rows__pinned_equipment_list_item=instance),
                **live,
            )
            .values_list("list_fighter__list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentFighterEquipmentListWeaponAccessory":
        # Weapon accessory cost overrides on specific fighter types, plus
        # accessory rows pinned to this override (mirror of its set_dirty).
        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(
                Q(
                    Q(list_fighter__content_fighter=instance.fighter)
                    | Q(list_fighter__legacy_content_fighter=instance.fighter)
                    | Q(list_fighter__promoted_content_fighter=instance.fighter),
                    weapon_accessories_field=instance.weapon_accessory,
                )
                | Q(accessory_rows__pinned_equipment_list_accessory=instance),
                **live,
            )
            .values_list("list_fighter__list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentFighterEquipmentListUpgrade":
        # Equipment upgrade cost overrides on specific fighter types —
        # applied per rung in SINGLE-stack cumulative pricing, so this rung
        # and every higher one — plus upgrade rows pinned to this override
        # (mirror of its set_dirty).
        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(
                Q(
                    Q(list_fighter__content_fighter=instance.fighter)
                    | Q(list_fighter__legacy_content_fighter=instance.fighter)
                    | Q(list_fighter__promoted_content_fighter=instance.fighter),
                    upgrades_field__in=instance.upgrade.same_stack_from_position(),
                )
                | Q(upgrade_rows__pinned_equipment_list_upgrade=instance),
                **live,
            )
            .values_list("list_fighter__list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentEquipmentListExpansionItem":
        # Expansion items - conservatively mark all assignments with this
        # equipment, plus rows pinned to this expansion item (base or
        # profile), mirroring its set_dirty exactly.
        expansion_q = Q(content_equipment=instance.equipment)
        if instance.weapon_profile is not None:
            expansion_q &= Q(weapon_profiles_field=instance.weapon_profile)

        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(
                expansion_q
                | Q(pinned_expansion_item=instance)
                | Q(profile_rows__pinned_expansion_item=instance),
                **live,
            )
            .values_list("list_fighter__list_id", flat=True)
            .distinct()
        )
    else:
        # Unknown model type
        logger.warning(f"Unknown model type for cost change action: {model_name}")
        return []

    return list(set(list_ids))


def _snapshot_list_costs(list_ids) -> dict:
    """Snapshot the current cached costs of the given lists.

    Captured synchronously (pre-commit) at enqueue time so the async task has a
    reliable pre-change baseline even if a list is viewed (and lazily recalculated)
    before the task runs. Keys are stringified list ids for JSON-serialisable task
    payloads.
    """
    from gyrinx.core.models.list import List

    return {
        str(lid): [rating, stash]
        for lid, rating, stash in List.objects.filter(id__in=list_ids).values_list(
            "id", "rating_current", "stash_current"
        )
    }


def _instance_display_name(instance) -> str:
    """Human-readable name for a content instance in action descriptions.

    Most models have a name field/method, but some need special handling.
    """
    model_name = instance.__class__.__name__
    if model_name == "ContentFighterEquipmentListItem":
        return instance.equipment.name
    elif model_name == "ContentFighterEquipmentListWeaponAccessory":
        return instance.weapon_accessory.name
    elif model_name == "ContentFighterEquipmentListUpgrade":
        return instance.upgrade.name
    elif model_name == "ContentEquipmentListExpansionItem":
        return instance.equipment.name
    elif hasattr(instance, "equipment"):
        # Generic equipment reference (e.g. ContentWeaponProfile,
        # ContentEquipmentUpgrade)
        return instance.equipment.name
    elif hasattr(instance, "name"):
        return instance.name() if callable(instance.name) else instance.name
    return str(instance)


def _create_content_cost_change_actions(instance, before_snapshots=None, old_cost=None):
    """
    Create CONTENT_COST_CHANGE actions for all lists affected by a content cost change.

    This function:
    1. Finds all affected lists via the instance's set_dirty relationships
    2. For each list, recalculates costs via facts_from_db(update=True)
    3. Creates a CONTENT_COST_CHANGE action with the rating/stash deltas
    4. In campaign mode, applies credits_delta (charges for increases, refunds decreases)

    Args:
        instance: The content model instance that had its cost changed
        before_snapshots: Optional ``{str(list_id): [rating_current, stash_current]}``
            map of pre-change costs captured synchronously at enqueue time. Used as
            the delta baseline so a lazy recalc-on-view between commit and this task
            running can't zero out the delta. When omitted, the live cached values
            are used (correct for synchronous/direct callers).
    """
    from gyrinx.core.cost.pin_sweep import rewrite_pinned_amounts_for_list
    from gyrinx.core.models.action import ListAction, ListActionType
    from gyrinx.core.models.list import List
    from gyrinx.core.tasks import refresh_list_facts

    # Find affected lists based on the model type. The rewrite domain also
    # includes lists reachable only through archived rows (their amounts are
    # rewritten so an unarchive can't resurrect a stale price); actions and
    # snapshots stay scoped to the live set.
    list_ids = _affected_list_ids(instance)
    rewrite_list_ids = _affected_list_ids(instance, include_archived=True)

    if not rewrite_list_ids:
        return  # No affected lists

    live_list_ids = set(list_ids)
    instance_name = _instance_display_name(instance)

    # For each list: rewrite pinned amounts, recalculate, create action.
    # Each list is processed in its own transaction for consistency:
    # either all changes succeed (amounts rewritten, facts updated, action
    # created, credits applied) or none do (transaction rolls back, list stays
    # dirty — and unrewritten — for a later redelivery).
    for list_id in rewrite_list_ids:
        try:
            with transaction.atomic():
                # Lock the list row for the duration of this per-list
                # transaction. This task is at-least-once and can be delivered
                # to two workers concurrently; without the lock, both pass the
                # ListAction.exists() idempotency guard below (and both read the
                # pre-rewrite pinned amounts) before either commits, so both
                # create an action and both apply_credit_delta — double-charging
                # campaign credits. The lock serialises concurrent deliveries so
                # the second one sees the first's committed action/amounts and
                # skips. Mirrors reconcile_list's select_for_update pattern.
                lst = List.objects.select_for_update().get(id=list_id)

                # Rewrite pinned amounts FIRST (#1826 §4.7 ordering): any
                # recompute — the facts_from_db below or a later lazy
                # view recalc — must sum already-updated amounts. Rewriting
                # after would snap the caches back to the old amounts or
                # double-count the correction on the next recompute.
                sweep = rewrite_pinned_amounts_for_list(
                    instance, lst, old_cost=old_cost
                )

                # Archived-only lists get the rewrite but no action
                # processing — nothing cache-visible moved, and the snapshot
                # fallback has no baseline for them.
                if list_id not in live_list_ids:
                    continue

                if sweep.use_row_deltas:
                    # Per-row amount deltas: Σ(new − old pinned amount) over
                    # the rows the sweep rewrote. Unlike the snapshot fallback
                    # below, this is independent of anything else landing on
                    # the list between enqueue and this task running — a
                    # racing user purchase used to be folded into this
                    # action's delta and double-charged in campaign credits.
                    # Redelivery is naturally idempotent: the second rewrite
                    # produces a zero delta and skips out here.
                    facts = lst.facts_from_db(update=True)
                    rating_delta = sweep.rating_delta
                    stash_delta = sweep.stash_delta
                    total_delta = rating_delta + stash_delta
                    # Check each delta, not the sum: +N rating / -N stash
                    # cancels to zero while both books moved, and skipping
                    # here (after facts committed the movement) would break
                    # the action chain.
                    if rating_delta == 0 and stash_delta == 0:
                        continue
                    # Chain the action off the recomputed head so anything
                    # that landed in the window keeps its own audit trail.
                    old_rating = facts.rating - rating_delta
                    old_stash = facts.stash - stash_delta
                else:
                    # Snapshot fallback: UNPINNED rows reprice live, so their
                    # movement only exists as recompute-vs-baseline. This is
                    # today's machinery, race included; it retires per-list as
                    # the Phase 8 backfill pins rows.
                    #
                    # Capture before state.
                    #
                    # This task runs asynchronously (after commit), so a user may view
                    # the affected list before it runs. Viewing a dirty list lazily
                    # recalculates and writes the *new* values into rating_current/
                    # stash_current (via get_clean_list_or_404 -> facts_from_db) WITHOUT
                    # recording an action — which would make the live rating_current a
                    # zero-delta baseline here, silently dropping the action (and, in
                    # campaign mode, the credit adjustment). So prefer the pre-change
                    # snapshot captured synchronously at enqueue time; fall back to the
                    # live value only when no snapshot was supplied (e.g. direct calls).
                    snapshot = (
                        before_snapshots.get(str(list_id)) if before_snapshots else None
                    )
                    if snapshot is not None:
                        old_rating, old_stash = snapshot
                    else:
                        old_rating = lst.rating_current
                        old_stash = lst.stash_current

                    # Idempotency: if this exact change was already recorded for this
                    # list (same content subject + same pre-change baseline), don't
                    # duplicate it. With a frozen snapshot a redelivery would otherwise
                    # recompute a non-zero delta and double-charge campaign credits.
                    if ListAction.objects.filter(
                        list=lst,
                        action_type=ListActionType.CONTENT_COST_CHANGE,
                        subject_id=instance.pk,
                        rating_before=old_rating,
                        stash_before=old_stash,
                    ).exists():
                        continue

                    # Recalculate with the new content costs (clears dirty flags on list and children)
                    facts = lst.facts_from_db(update=True)

                    # Compute deltas
                    rating_delta = facts.rating - old_rating
                    stash_delta = facts.stash - old_stash
                    total_delta = rating_delta + stash_delta

                    # Skip if no actual cost change (e.g., override in place)
                    # This happens when a base cost changes but a fighter-specific
                    # override (ContentFighterEquipmentListItem, etc.) takes
                    # precedence. Check each delta, not the sum — +N rating /
                    # -N stash cancels while both books moved.
                    if rating_delta == 0 and stash_delta == 0:
                        continue

                # In campaign mode, adjust credits (charge more or refund)
                # Positive delta = cost increased = charge credits (negative)
                # Negative delta = cost decreased = refund credits (positive)
                is_campaign = lst.is_campaign_mode
                credits_delta = -total_delta if is_campaign else 0

                # Format the cost change for the description
                cost_change_str = format_cost_display(total_delta, show_sign=True)

                # Record the action — facts_from_db already updated the
                # rating/stash caches, and create_action is a pure record.
                # The campaign credit adjustment is applied
                # explicitly afterwards, inside the same per-list transaction
                # and behind the same idempotency guards above, so a
                # redelivery can't double-charge.
                lst.create_action(
                    action_type=ListActionType.CONTENT_COST_CHANGE,
                    description=f"{instance_name} changed cost ({cost_change_str})",
                    # Record the content instance as the subject so the task can
                    # detect (and skip) an already-recorded change on redelivery.
                    subject_app=instance._meta.app_label,
                    subject_type=instance._meta.model_name,
                    subject_id=instance.pk,
                    rating_before=old_rating,
                    stash_before=old_stash,
                    rating_delta=rating_delta,
                    stash_delta=stash_delta,
                    credits_delta=credits_delta,
                )
                if is_campaign:
                    lst.apply_credit_delta(credits_delta)
        except List.DoesNotExist:
            continue
        except Exception as e:
            # Log error but continue processing other lists. The per-list
            # transaction rolled back, so the amount rewrite was undone and
            # no action was recorded.
            logger.error(
                f"Failed to create CONTENT_COST_CHANGE action for list {list_id}: {e}"
            )
            # Index pages show last-good numbers and never recompute, so give
            # the failed list a background heal rather than waiting for a
            # detail-page view. The heal clears dirty but recomputes against
            # the UNREWRITTEN (pre-correction) amounts, and the audit action
            # is still missing — a task redelivery is the real recovery, and
            # it works regardless of the dirty flag (the sweep re-runs the
            # rewrite and recompute unconditionally).
            try:
                refresh_list_facts.enqueue(list_id=str(list_id))
            except Exception:
                logger.warning(
                    f"Failed to enqueue facts refresh for list {list_id}",
                    exc_info=True,
                )


# Post-save signal handlers that create actions after content saves


def _enqueue_content_cost_propagation(instance):
    """Enqueue async recalculation/action-creation for a content cost change.

    The fan-out (recalculating facts and creating CONTENT_COST_CHANGE actions
    for every affected list) used to run synchronously in the request that saved
    the content object. For a popular item that could mean a multi-minute,
    many-thousand-query request. Instead we enqueue the
    ``propagate_content_cost_change`` task and let it run off the request thread.

    The dirty flags were already set synchronously in the pre_save handler, so
    anyone reading an affected list between commit and task completion sees a
    dirty cache and recalculates lazily via ``get_clean_list_or_404``. That lazy
    recalc updates the list's cached rating/stash WITHOUT recording an action,
    so we must capture each affected list's pre-change costs *now* (synchronously,
    before commit, while rating_current still holds the old value) and hand them
    to the task as the delta baseline. Otherwise a view racing ahead of the task
    would zero out the delta and the audit action (and campaign credit
    adjustment) would be silently dropped.

    Enumerating the affected lists + snapshotting their cached costs is cheap
    (indexed lookups, no per-list facts recalculation); the expensive fan-out
    stays in the task.

    Deferred to ``transaction.on_commit``: the worker runs in a separate process
    (prod Pub/Sub backend) and must see the committed new cost, and must not run
    for a save that ends up rolled back. Under the test/dev ImmediateBackend the
    task runs inline when the on_commit callbacks fire.
    """
    from django.contrib.contenttypes.models import ContentType

    from gyrinx.core.tasks import propagate_content_cost_change

    content_type_id = ContentType.objects.get_for_model(instance.__class__).id
    object_id = str(instance.pk)
    old_cost = getattr(instance, "_old_cost_for_propagation", None)

    # Capture pre-change cost baselines synchronously (pre-commit). pre_save has
    # marked these lists dirty but has not recalculated them, so rating_current /
    # stash_current still hold the old values here.
    before_snapshots = _snapshot_list_costs(_affected_list_ids(instance))

    def _enqueue():
        try:
            propagate_content_cost_change.enqueue(
                content_type_id=content_type_id,
                object_id=object_id,
                before_snapshots=before_snapshots,
                old_cost=old_cost,
            )
        except Exception:
            logger.exception(
                "Failed to enqueue content cost propagation for %s %s",
                content_type_id,
                object_id,
            )

    transaction.on_commit(_enqueue)


@receiver(
    post_save, sender=ContentEquipment, dispatch_uid="content_equipment_cost_action"
)
@traced("signal_content_equipment_cost_action")
def create_equipment_cost_action(sender, instance, created, **kwargs):
    """Create CONTENT_COST_CHANGE actions after equipment cost change."""
    if created or not getattr(instance, "_cost_changed", False):
        return
    _enqueue_content_cost_propagation(instance)
    instance._cost_changed = False  # Clear flag


@receiver(post_save, sender=ContentFighter, dispatch_uid="content_fighter_cost_action")
@traced("signal_content_fighter_cost_action")
def create_fighter_cost_action(sender, instance, created, **kwargs):
    """Create CONTENT_COST_CHANGE actions after fighter base cost change."""
    if created or not getattr(instance, "_cost_changed", False):
        return
    _enqueue_content_cost_propagation(instance)
    instance._cost_changed = False


@receiver(
    post_save,
    sender=ContentFighter,
    dispatch_uid="content_fighter_sync_auto_equipment_cost",
)
@traced("signal_content_fighter_sync_auto_equipment_cost")
def sync_auto_equipment_cost(sender, instance, created, **kwargs):
    """Keep a vehicle/exotic-beast pack fighter's companion equipment in sync.

    When a VEHICLE / EXOTIC_BEAST pack fighter is saved, the companion
    equipment row (created by the pack flow) must mirror the fighter's
    ``type``, ``base_cost`` and ``category`` (in case the user converted
    between VEHICLE and EXOTIC_BEAST).

    Looks up via the canonical ``auto_companion_for_fighter`` FK so the
    target is unambiguous. Short-circuits for non-auto-equipment categories
    so a category change away (e.g. VEHICLE → GANGER) leaves the
    companion alone — see #1725-related discussion in the PR for the
    follow-up form-level guard.
    """
    if kwargs.get("raw"):
        # Fixture loading (loaddata / loaddata_overwrite): the fixture already
        # carries consistent companion rows, and writing mid-import could
        # collide with rows the fixture inserts later.
        return
    if instance.category not in AUTO_EQUIPMENT_CATEGORY_BY_FIGHTER_CATEGORY:
        return

    equipment = (
        ContentEquipment.objects.all_content()
        .filter(auto_companion_for_fighter=instance)
        .first()
    )
    if equipment is None:
        # No companion yet — the create flow owns initial creation.
        return

    cat_name, cat_group = AUTO_EQUIPMENT_CATEGORY_BY_FIGHTER_CATEGORY[instance.category]
    target_category, _ = ContentEquipmentCategory.objects.get_or_create(
        name=cat_name, defaults={"group": cat_group}
    )

    changed = False
    if equipment.name != instance.type:
        equipment.name = instance.type
        changed = True
    if equipment.cost != str(instance.base_cost):
        equipment.cost = str(instance.base_cost)
        changed = True
    if equipment.category_id != target_category.pk:
        equipment.category = target_category
        changed = True
    if changed:
        equipment.save()


@receiver(
    post_save, sender=ContentWeaponProfile, dispatch_uid="content_profile_cost_action"
)
@traced("signal_content_profile_cost_action")
def create_profile_cost_action(sender, instance, created, **kwargs):
    """Create CONTENT_COST_CHANGE actions after weapon profile cost change."""
    if created or not getattr(instance, "_cost_changed", False):
        return
    _enqueue_content_cost_propagation(instance)
    instance._cost_changed = False


@receiver(
    post_save,
    sender=ContentWeaponAccessory,
    dispatch_uid="content_accessory_cost_action",
)
@traced("signal_content_accessory_cost_action")
def create_accessory_cost_action(sender, instance, created, **kwargs):
    """Create CONTENT_COST_CHANGE actions after weapon accessory cost change."""
    if created or not getattr(instance, "_cost_changed", False):
        return
    _enqueue_content_cost_propagation(instance)
    instance._cost_changed = False


@receiver(
    post_save,
    sender=ContentEquipmentUpgrade,
    dispatch_uid="content_upgrade_cost_action",
)
@traced("signal_content_upgrade_cost_action")
def create_upgrade_cost_action(sender, instance, created, **kwargs):
    """Create CONTENT_COST_CHANGE actions after equipment upgrade cost change."""
    if created or not getattr(instance, "_cost_changed", False):
        return
    _enqueue_content_cost_propagation(instance)
    instance._cost_changed = False


@receiver(
    post_save,
    sender=ContentFighterEquipmentListItem,
    dispatch_uid="content_equipment_list_item_cost_action",
)
@traced("signal_content_equipment_list_item_cost_action")
def create_equipment_list_item_cost_action(sender, instance, created, **kwargs):
    """Create CONTENT_COST_CHANGE actions after equipment list item cost change."""
    if created or not getattr(instance, "_cost_changed", False):
        return
    _enqueue_content_cost_propagation(instance)
    instance._cost_changed = False


@receiver(
    post_save,
    sender=ContentFighterEquipmentListWeaponAccessory,
    dispatch_uid="content_equipment_list_accessory_cost_action",
)
@traced("signal_content_equipment_list_accessory_cost_action")
def create_equipment_list_accessory_cost_action(sender, instance, created, **kwargs):
    """Create CONTENT_COST_CHANGE actions after equipment list accessory cost change."""
    if created or not getattr(instance, "_cost_changed", False):
        return
    _enqueue_content_cost_propagation(instance)
    instance._cost_changed = False


@receiver(
    post_save,
    sender=ContentFighterEquipmentListUpgrade,
    dispatch_uid="content_equipment_list_upgrade_cost_action",
)
@traced("signal_content_equipment_list_upgrade_cost_action")
def create_equipment_list_upgrade_cost_action(sender, instance, created, **kwargs):
    """Create CONTENT_COST_CHANGE actions after equipment list upgrade cost change."""
    if created or not getattr(instance, "_cost_changed", False):
        return
    _enqueue_content_cost_propagation(instance)
    instance._cost_changed = False


@receiver(
    post_save,
    sender=ContentFighterHouseOverride,
    dispatch_uid="content_fighter_house_override_cost_action",
)
@traced("signal_content_fighter_house_override_cost_action")
def create_fighter_house_override_cost_action(sender, instance, created, **kwargs):
    """Create CONTENT_COST_CHANGE actions after fighter house override cost change."""
    if created or not getattr(instance, "_cost_changed", False):
        return
    _enqueue_content_cost_propagation(instance)
    instance._cost_changed = False


@receiver(
    post_save,
    sender=ContentEquipmentListExpansionItem,
    dispatch_uid="content_expansion_item_cost_action",
)
@traced("signal_content_expansion_item_cost_action")
def create_expansion_item_cost_action(sender, instance, created, **kwargs):
    """Create CONTENT_COST_CHANGE actions after expansion item cost change."""
    if created or not getattr(instance, "_cost_changed", False):
        return
    _enqueue_content_cost_propagation(instance)
    instance._cost_changed = False


# =============================================================================
# Delete-side handlers: orphan pins when a price source is deleted
# =============================================================================


def _orphan_pinned_rows(instance):
    """Flip rows pinned to a deleted price source to ORPHANED (#1826 §4.7).

    The amounts stand — nothing changes price, so there is no cache movement
    and no dirty-marking — but the attribution is gone, and ORPHANED is what
    keeps every later amount-rewriting sweep's hands off these rows. An audit
    action records the attribution loss per affected list.

    Runs in pre_delete so the rows are still findable by pin-FK equality (the
    FKs are SET_NULL); the handler clears the FKs itself, making the delete
    collector's SET_NULL a no-op for these rows. The pin edges are walked via
    introspection so a future pin FK is orphaned without new wiring here.

    NOTE (Phase 8): the per-list audit fan-out below runs synchronously in
    the deleting request. Harmless while pins are sparse; once the backfill
    pins everything, deleting a popular source touches many lists — flip the
    states synchronously but move the audit fan-out to a task then.
    """
    from gyrinx.core.models.action import ListActionType
    from gyrinx.core.models.list import (
        List,
        ListFighterEquipmentAssignment,
        PinState,
    )

    orphaned_by_list: dict = {}
    for rel in type(instance)._meta.related_objects:
        if not rel.field.name.startswith("pinned_"):
            continue
        model = rel.related_model
        if model._meta.model_name.startswith("historical"):
            continue
        is_base = model is ListFighterEquipmentAssignment
        state_field = "pinned_base_state" if is_base else "pin_state"
        amount_field = "pinned_base_amount" if is_base else "pinned_amount"
        list_path = (
            "list_fighter__list_id"
            if is_base
            else "listfighterequipmentassignment__list_fighter__list_id"
        )
        rows = model.objects.filter(**{rel.field.name: instance})
        for lid in rows.values_list(list_path, flat=True):
            orphaned_by_list[lid] = orphaned_by_list.get(lid, 0) + 1
        # Rows with an amount keep it and become ORPHANED; a half-written row
        # without one (which nothing should produce) just loses the FK.
        rows.filter(**{f"{amount_field}__isnull": False}).update(
            **{rel.field.name: None, state_field: PinState.ORPHANED}
        )
        rows.filter(**{f"{amount_field}__isnull": True}).update(
            **{rel.field.name: None}
        )

    if not orphaned_by_list:
        return

    # Capture plain values now — the instance is gone by the time the audit
    # runs.
    name = _instance_display_name(instance)
    subject_app = instance._meta.app_label
    subject_type = instance._meta.model_name
    subject_id = instance.pk

    def _write_orphan_audits():
        for list_id, count in orphaned_by_list.items():
            try:
                with transaction.atomic():
                    lst = List.objects.get(id=list_id)
                    components = "component" if count == 1 else "components"
                    lst.create_action(
                        action_type=ListActionType.CONTENT_COST_CHANGE,
                        description=(
                            f"{name}: price source deleted; {count} pinned "
                            f"{components} keep their amounts, attribution cleared"
                        ),
                        subject_app=subject_app,
                        subject_type=subject_type,
                        subject_id=subject_id,
                        rating_delta=0,
                        stash_delta=0,
                        credits_delta=0,
                    )
            except List.DoesNotExist:
                continue  # itself deleted in the same cascade
            except Exception:
                logger.exception("Failed to record pin-orphaning for list %s", list_id)

    # Deferred past commit: the delete collector fires every pre_delete
    # BEFORE deleting anything, so writing a ListAction here for a list
    # that is itself in the same cascade (deleting a ContentHouse cascades
    # to its fighters' price rows AND to its lists) would insert a row
    # referencing a doomed List — an IntegrityError at commit that rolls
    # the whole deletion back. After commit, cascade-deleted lists simply
    # no longer exist and are skipped.
    transaction.on_commit(_write_orphan_audits)


@receiver(
    pre_delete,
    sender=ContentFighterEquipmentListItem,
    dispatch_uid="orphan_pins_equipment_list_item_delete",
)
@traced("signal_orphan_pins_equipment_list_item_delete")
def orphan_pins_on_equipment_list_item_delete(sender, instance, **kwargs):
    _orphan_pinned_rows(instance)


@receiver(
    pre_delete,
    sender=ContentFighterEquipmentListWeaponAccessory,
    dispatch_uid="orphan_pins_equipment_list_accessory_delete",
)
@traced("signal_orphan_pins_equipment_list_accessory_delete")
def orphan_pins_on_equipment_list_accessory_delete(sender, instance, **kwargs):
    _orphan_pinned_rows(instance)


@receiver(
    pre_delete,
    sender=ContentFighterEquipmentListUpgrade,
    dispatch_uid="orphan_pins_equipment_list_upgrade_delete",
)
@traced("signal_orphan_pins_equipment_list_upgrade_delete")
def orphan_pins_on_equipment_list_upgrade_delete(sender, instance, **kwargs):
    _orphan_pinned_rows(instance)


@receiver(
    pre_delete,
    sender=ContentEquipmentListExpansionItem,
    dispatch_uid="orphan_pins_expansion_item_delete",
)
@traced("signal_orphan_pins_expansion_item_delete")
def orphan_pins_on_expansion_item_delete(sender, instance, **kwargs):
    _orphan_pinned_rows(instance)
