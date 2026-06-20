import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver

from gyrinx.content.models import (
    ContentEquipmentEquipmentProfile,
    ContentEquipmentFighterProfile,
    ContentFighterDefaultAssignment,
)
from gyrinx.core.models.list.assignment import ListFighterEquipmentAssignment
from gyrinx.core.models.list.fighter import (
    ListFighter,
    _materialise_child_fighter_defaults,
)
from gyrinx.core.models.list.list import List
from gyrinx.core.tasks import (
    propagate_default_child_fighter_assignment,
)
from gyrinx.tracing import traced

logger = logging.getLogger(__name__)
pylist = list


@receiver(post_save, sender=ListFighter, dispatch_uid="create_linked_objects")
@traced("signal_create_linked_objects")
def create_linked_objects(sender, instance, **kwargs):
    _materialise_child_fighter_defaults(instance)


@receiver(
    post_save,
    sender=ContentFighterDefaultAssignment,
    dispatch_uid="propagate_default_child_fighter_assignment",
)
@traced("signal_propagate_default_child_fighter_assignment")
def enqueue_propagate_default_child_fighter_assignment(
    sender, instance, created, **kwargs
):
    """Propagate a newly-created child-spawning default to existing gangs.

    When a pack author adds a ``ContentFighterDefaultAssignment`` whose
    equipment spawns a child fighter (a vehicle / exotic beast), existing gangs
    subscribed to the pack should also get the child materialised — not just
    gangs created after the change (issue #1725).

    Only fires for newly-created defaults whose equipment actually spawns a
    child fighter; ordinary gear/weapon defaults are virtual at display time
    and need no materialisation. The work is offloaded to a task because it can
    touch many list-fighters across all subscribed gangs.
    """
    if not created:
        return
    if not instance.equipment.contentequipmentfighterprofile_set.exists():
        return

    default_assignment_id = str(instance.pk)

    def _enqueue():
        try:
            propagate_default_child_fighter_assignment.enqueue(
                default_assignment_id=default_assignment_id
            )
        except Exception as e:
            logger.warning(
                f"Failed to enqueue propagation for default assignment "
                f"{default_assignment_id}: {e}"
            )

    # Defer until the surrounding transaction commits: the worker runs in a
    # separate process (prod Pub/Sub backend) and must not race the commit or
    # run for an assignment that ends up rolled back.
    transaction.on_commit(_enqueue)


@receiver(
    post_save,
    sender=ListFighter,
    dispatch_uid="touch_list_modified_on_fighter_save",
)
def touch_list_modified_on_fighter_save(sender, instance, **kwargs):
    """Bump the parent list's modified timestamp when any fighter is saved."""
    from django.utils import timezone

    List.objects.filter(pk=instance.list_id).update(modified=timezone.now())


@receiver(
    post_save,
    sender=ListFighterEquipmentAssignment,
    dispatch_uid="create_related_objects",
)
@traced("signal_create_related_objects")
def create_related_objects(sender, instance, **kwargs):
    equipment_fighter_profile = ContentEquipmentFighterProfile.objects.filter(
        equipment=instance.content_equipment,
    )
    # If there is a profile and we aren't already linked
    if equipment_fighter_profile.exists() and not instance.child_fighter:
        if equipment_fighter_profile.count() > 1:
            raise ValueError(
                f"Equipment {instance.content_equipment} has multiple fighter profiles"
            )

        profile = equipment_fighter_profile.first()

        if profile.content_fighter == instance.list_fighter.content_fighter:
            raise ValueError(
                f"Equipment {instance.content_equipment} has a fighter profile for the same fighter"
            )

        lf = ListFighter.objects.create(
            name=profile.content_fighter.type,
            content_fighter=profile.content_fighter,
            list=instance.list_fighter.list,
            owner=instance.list_fighter.list.owner,
        )
        # Establish the link FIRST so is_child_fighter returns True
        instance.child_fighter = lf
        instance.save()
        # NOW cost_int() returns 0 (child fighters don't contribute to list cost)
        lf.facts_from_db(update=True)

    equipment_equipment_profile = ContentEquipmentEquipmentProfile.objects.filter(
        equipment=instance.content_equipment,
    )
    existing_linked_assignments = ListFighterEquipmentAssignment.objects.filter(
        linked_equipment_parent=instance
    )
    for profile in equipment_equipment_profile:
        equip_to_create = profile.linked_equipment
        # Don't allow us to create ourselves again
        if equip_to_create == instance.content_equipment:
            raise ValueError(
                f"Equipment {instance.content_equipment} has a equipment profile for the same equipment"
            )

        # Check if the profile is already linked to this assignment
        if existing_linked_assignments.filter(
            content_equipment=equip_to_create
        ).exists():
            continue

        ListFighterEquipmentAssignment.objects.create_with_facts(
            list_fighter=instance.list_fighter,
            content_equipment=equip_to_create,
            linked_equipment_parent=instance,
        )


@receiver(
    pre_delete,
    sender=ListFighterEquipmentAssignment,
    dispatch_uid="delete_related_objects_pre_delete",
)
@traced("signal_delete_related_objects_pre_delete")
def delete_related_objects_pre_delete(sender, instance, **kwargs):
    for child in instance.linked_equipment_children.all():
        child.delete()


@receiver(
    post_delete,
    sender=ListFighterEquipmentAssignment,
    dispatch_uid="delete_related_objects_post_delete",
)
@traced("signal_delete_related_objects_post_delete")
def delete_related_objects_post_delete(sender, instance, **kwargs):
    if instance.child_fighter:
        instance.child_fighter.delete()


@receiver(
    [post_delete, post_save],
    sender=ListFighterEquipmentAssignment,
    dispatch_uid="clear_fighter_cached_properties_for_assignment",
)
@traced("signal_clear_fighter_cached_properties_for_assignment")
def clear_fighter_cached_properties_for_assignment(
    sender, instance: ListFighterEquipmentAssignment, **kwargs
):
    """Clear the fighter's cached properties that depend on assignments."""
    fighter = instance.list_fighter
    for prop in ["cost_int_cached", "assignments_cached", "_mods"]:
        if prop in fighter.__dict__:
            del fighter.__dict__[prop]
    # Also clear list's cached property
    if "cost_int_cached" in fighter.list.__dict__:
        del fighter.list.__dict__["cost_int_cached"]
