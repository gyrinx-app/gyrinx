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
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from gyrinx.content.signals import get_new_cost, get_old_cost
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
        instance.set_dirty()


@receiver(
    pre_save,
    sender=ContentWeaponAccessory,
    dispatch_uid="content_accessory_cost_change",
)
@traced("signal_content_accessory_cost_change")
def handle_accessory_cost_change(sender, instance, **kwargs):
    """
    Mark affected assignments dirty when ContentWeaponAccessory.cost changes.
    """
    old_cost = get_old_cost(sender, instance, "cost")
    if old_cost is None:
        return  # New instance, no existing assignments

    new_cost = get_new_cost(instance, "cost")
    if old_cost != new_cost:
        instance._cost_changed = True  # Flag for post_save to create actions
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
    if old_cost != new_cost:
        instance._cost_changed = True  # Flag for post_save to create actions
        instance.set_dirty()


# =============================================================================
# Post-save signal handlers
#
# These handlers run after content models are saved. If the pre_save handler
# detected a cost change (via _cost_changed flag), they create ListAction
# records for affected lists.
# =============================================================================


def _affected_list_ids(instance) -> list:
    """Return the distinct ids of lists affected by a content cost change.

    Shared by the synchronous enqueue path (which snapshots each affected list's
    pre-change costs) and the async task (which recalculates and records actions),
    so both agree on exactly which lists a content instance touches. Returns an
    empty list for unknown model types.
    """
    from gyrinx.core.models.list import (
        ListFighter,
        ListFighterEquipmentAssignment,
    )

    model_name = instance.__class__.__name__

    if model_name == "ContentEquipment":
        # Equipment directly assigned to fighters
        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(
                content_equipment=instance, archived=False
            )
            .values_list("list_fighter__list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentWeaponProfile":
        # Weapon profiles on assignments
        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(
                weapon_profiles_field=instance, archived=False
            )
            .values_list("list_fighter__list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentWeaponAccessory":
        # Weapon accessories on assignments
        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(
                weapon_accessories_field=instance, archived=False
            )
            .values_list("list_fighter__list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentEquipmentUpgrade":
        # Equipment upgrades on assignments
        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(
                upgrades_field=instance, archived=False
            )
            .values_list("list_fighter__list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentFighter":
        # Fighter templates used by list fighters (including legacy)
        list_ids = (
            ListFighter.objects.filter(
                Q(content_fighter=instance) | Q(legacy_content_fighter=instance),
                archived=False,
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
                archived=False,
            )
            .values_list("list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentFighterEquipmentListItem":
        # Equipment list items - cost overrides for equipment on specific fighter types
        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(
                Q(list_fighter__content_fighter=instance.fighter)
                | Q(list_fighter__legacy_content_fighter=instance.fighter),
                content_equipment=instance.equipment,
                archived=False,
            )
            .values_list("list_fighter__list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentFighterEquipmentListWeaponAccessory":
        # Weapon accessory cost overrides on specific fighter types
        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(
                Q(list_fighter__content_fighter=instance.fighter)
                | Q(list_fighter__legacy_content_fighter=instance.fighter),
                weapon_accessories_field=instance.weapon_accessory,
                archived=False,
            )
            .values_list("list_fighter__list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentFighterEquipmentListUpgrade":
        # Equipment upgrade cost overrides on specific fighter types
        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(
                Q(list_fighter__content_fighter=instance.fighter)
                | Q(list_fighter__legacy_content_fighter=instance.fighter),
                upgrades_field=instance.upgrade,
                archived=False,
            )
            .values_list("list_fighter__list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentEquipmentListExpansionItem":
        # Expansion items - conservatively mark all assignments with this equipment
        filter_kwargs = {
            "content_equipment": instance.equipment,
            "archived": False,
        }
        if instance.weapon_profile is not None:
            filter_kwargs["weapon_profiles_field"] = instance.weapon_profile

        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(**filter_kwargs)
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


def _create_content_cost_change_actions(instance, before_snapshots=None):
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
    from gyrinx.core.models.action import ListAction, ListActionType
    from gyrinx.core.models.list import List

    # Find affected lists based on the model type
    model_name = instance.__class__.__name__
    list_ids = _affected_list_ids(instance)

    if not list_ids:
        return  # No affected lists

    # Get the instance name for the action description
    # Most models have a name field/method, but some need special handling
    if model_name == "ContentFighterEquipmentListItem":
        # This model has equipment FK
        instance_name = instance.equipment.name
    elif model_name == "ContentFighterEquipmentListWeaponAccessory":
        # This model has weapon_accessory FK
        instance_name = instance.weapon_accessory.name
    elif model_name == "ContentFighterEquipmentListUpgrade":
        # This model has upgrade FK
        instance_name = instance.upgrade.name
    elif model_name == "ContentEquipmentListExpansionItem":
        # This model has equipment FK
        instance_name = instance.equipment.name
    elif hasattr(instance, "equipment"):
        # Generic equipment reference (e.g., ContentWeaponProfile, ContentEquipmentUpgrade)
        instance_name = instance.equipment.name
    elif hasattr(instance, "name"):
        instance_name = instance.name() if callable(instance.name) else instance.name
    else:
        instance_name = str(instance)

    # For each list, recalculate and create action
    # Each list is processed in its own transaction for consistency:
    # either all changes succeed (facts updated, action created, credits applied)
    # or none do (transaction rolls back, list stays dirty for later recalculation)
    for list_id in list_ids:
        try:
            with transaction.atomic():
                lst = List.objects.get(id=list_id)

                # Only create actions for lists that have an initial action
                # Lists without latest_action will have dirty flag set via set_dirty()
                # and will be recalculated when viewed
                if not lst.latest_action:
                    continue

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
                if (
                    ListAction.objects.filter(
                        list=lst,
                        action_type=ListActionType.CONTENT_COST_CHANGE,
                        subject_id=instance.pk,
                        rating_before=old_rating,
                        stash_before=old_stash,
                    )
                    .exclude(applied=False)
                    .exists()
                ):
                    continue

                # Recalculate with the new content costs (clears dirty flags on list and children)
                facts = lst.facts_from_db(update=True)

                # Compute deltas
                rating_delta = facts.rating - old_rating
                stash_delta = facts.stash - old_stash
                total_delta = rating_delta + stash_delta

                # Skip if no actual cost change (e.g., override in place)
                # This happens when a base cost changes but a fighter-specific
                # override (ContentFighterEquipmentListItem, etc.) takes precedence
                if total_delta == 0:
                    continue

                # In campaign mode, adjust credits (charge more or refund)
                # Positive delta = cost increased = charge credits (negative)
                # Negative delta = cost decreased = refund credits (positive)
                is_campaign = lst.is_campaign_mode
                credits_delta = -total_delta if is_campaign else 0

                # Format the cost change for the description
                cost_change_str = format_cost_display(total_delta, show_sign=True)

                # Create the action. Skip applying rating/stash deltas since facts_from_db
                # already updated those values. Credits delta is still applied.
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
                    update_credits=is_campaign,
                    skip_apply=["rating", "stash"],
                )
        except List.DoesNotExist:
            continue
        except Exception as e:
            # Log error but continue processing other lists
            # The failed list will remain dirty and be recalculated on next view
            logger.error(
                f"Failed to create CONTENT_COST_CHANGE action for list {list_id}: {e}"
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
