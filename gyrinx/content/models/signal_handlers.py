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

from .equipment import ContentEquipment, ContentEquipmentUpgrade
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


def _create_content_cost_change_actions(instance):
    """
    Create CONTENT_COST_CHANGE actions for all lists affected by a content cost change.

    This function:
    1. Finds all affected lists via the instance's set_dirty relationships
    2. For each list, recalculates costs via facts_from_db(update=True)
    3. Creates a CONTENT_COST_CHANGE action with the rating/stash deltas
    4. In campaign mode, applies credits_delta (charges for increases, refunds decreases)

    Args:
        instance: The content model instance that had its cost changed
    """
    from gyrinx.core.models.action import ListActionType
    from gyrinx.core.models.list import (
        List,
        ListFighter,
        ListFighterEquipmentAssignment,
    )

    # Find affected lists based on the model type
    model_name = instance.__class__.__name__

    if model_name == "ContentEquipment":
        # Equipment directly assigned to fighters
        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(
                content_equipment=instance, archived=False
            )
            .select_related("list_fighter__list")
            .values_list("list_fighter__list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentWeaponProfile":
        # Weapon profiles on assignments
        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(
                weapon_profiles_field=instance, archived=False
            )
            .select_related("list_fighter__list")
            .values_list("list_fighter__list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentWeaponAccessory":
        # Weapon accessories on assignments
        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(
                weapon_accessories_field=instance, archived=False
            )
            .select_related("list_fighter__list")
            .values_list("list_fighter__list_id", flat=True)
            .distinct()
        )
    elif model_name == "ContentEquipmentUpgrade":
        # Equipment upgrades on assignments
        list_ids = (
            ListFighterEquipmentAssignment.objects.filter(
                upgrades_field=instance, archived=False
            )
            .select_related("list_fighter__list")
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
            .select_related("list_fighter__list")
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
            .select_related("list_fighter__list")
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
            .select_related("list_fighter__list")
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
            .select_related("list_fighter__list")
            .values_list("list_fighter__list_id", flat=True)
            .distinct()
        )
    else:
        # Unknown model type
        logger.warning(f"Unknown model type for cost change action: {model_name}")
        return

    # Get the distinct list IDs
    list_ids = list(set(list_ids))

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

                # Capture before state
                old_rating = lst.rating_current
                old_stash = lst.stash_current

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


@receiver(
    post_save, sender=ContentEquipment, dispatch_uid="content_equipment_cost_action"
)
@traced("signal_content_equipment_cost_action")
def create_equipment_cost_action(sender, instance, created, **kwargs):
    """Create CONTENT_COST_CHANGE actions after equipment cost change."""
    if created or not getattr(instance, "_cost_changed", False):
        return
    _create_content_cost_change_actions(instance)
    instance._cost_changed = False  # Clear flag


@receiver(post_save, sender=ContentFighter, dispatch_uid="content_fighter_cost_action")
@traced("signal_content_fighter_cost_action")
def create_fighter_cost_action(sender, instance, created, **kwargs):
    """Create CONTENT_COST_CHANGE actions after fighter base cost change."""
    if created or not getattr(instance, "_cost_changed", False):
        return
    _create_content_cost_change_actions(instance)
    instance._cost_changed = False


@receiver(
    post_save, sender=ContentWeaponProfile, dispatch_uid="content_profile_cost_action"
)
@traced("signal_content_profile_cost_action")
def create_profile_cost_action(sender, instance, created, **kwargs):
    """Create CONTENT_COST_CHANGE actions after weapon profile cost change."""
    if created or not getattr(instance, "_cost_changed", False):
        return
    _create_content_cost_change_actions(instance)
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
    _create_content_cost_change_actions(instance)
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
    _create_content_cost_change_actions(instance)
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
    _create_content_cost_change_actions(instance)
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
    _create_content_cost_change_actions(instance)
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
    _create_content_cost_change_actions(instance)
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
    _create_content_cost_change_actions(instance)
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
    _create_content_cost_change_actions(instance)
    instance._cost_changed = False
