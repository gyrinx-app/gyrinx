# Generated by Django 5.1.7 on 2025-04-18 16:07

from django.db import migrations

from gyrinx.core.models import (
    ListFighterEquipmentAssignment as ListFighterEquipmentAssignmentModel,
)


def do_migration(apps, schema_editor):
    ListFighterEquipmentAssignment: type[ListFighterEquipmentAssignmentModel] = (
        apps.get_model("core", "ListFighterEquipmentAssignment")
    )

    for assignment in ListFighterEquipmentAssignment.objects.all():
        if assignment.upgrade:
            assignment.upgrades_field.add(assignment.upgrade)
            assignment.upgrade = None
            assignment.save()


def undo_migration(apps, schema_editor):
    ListFighterEquipmentAssignment: type[ListFighterEquipmentAssignmentModel] = (
        apps.get_model("core", "ListFighterEquipmentAssignment")
    )

    for assignment in ListFighterEquipmentAssignment.objects.all():
        if assignment.upgrades_field.exists():
            assignment.upgrade = assignment.upgrades_field.first()
            assignment.upgrades_field.clear()
            assignment.save()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0038_listfighterequipmentassignment_upgrades_field"),
    ]

    operations = [migrations.RunPython(do_migration, undo_migration)]
