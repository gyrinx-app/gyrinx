# Cost-pinning programme (#1826), Phase 4: declare through models IN PLACE
# on the join tables Django auto-created for the three component M2Ms.
#
# The tables already exist with exactly this shape (BigAuto pk,
# listfighterequipmentassignment_id / content*_id uuid columns, a unique
# constraint on the pair) — so every operation here is STATE-ONLY: Django's
# picture of the schema changes, the database does not. Verified against
# analytics/structure.sql. The pin columns land as real DDL in the next
# migration.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0176_contentmod_unique_constraints"),
        ("core", "0150_gang_skill_constraints"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="ListFighterEquipmentAssignmentAccessory",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "contentweaponaccessory",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="+",
                                to="content.contentweaponaccessory",
                            ),
                        ),
                        (
                            "listfighterequipmentassignment",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="accessory_rows",
                                to="core.listfighterequipmentassignment",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "weapon accessory row",
                        "verbose_name_plural": "weapon accessory rows",
                        "db_table": "core_listfighterequipmentassignment_weapon_accessories_field",
                        "unique_together": {
                            ("listfighterequipmentassignment", "contentweaponaccessory")
                        },
                    },
                ),
                migrations.AlterField(
                    model_name="listfighterequipmentassignment",
                    name="weapon_accessories_field",
                    field=models.ManyToManyField(
                        blank=True,
                        help_text="Select the weapon accessories to assign to this equipment.",
                        related_name="weapon_accessories",
                        through="core.ListFighterEquipmentAssignmentAccessory",
                        to="content.contentweaponaccessory",
                        verbose_name="weapon accessories",
                    ),
                ),
                migrations.CreateModel(
                    name="ListFighterEquipmentAssignmentProfile",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "contentweaponprofile",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="+",
                                to="content.contentweaponprofile",
                            ),
                        ),
                        (
                            "listfighterequipmentassignment",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="profile_rows",
                                to="core.listfighterequipmentassignment",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "weapon profile row",
                        "verbose_name_plural": "weapon profile rows",
                        "db_table": "core_listfighterequipmentassignment_weapon_profiles_field",
                        "unique_together": {
                            ("listfighterequipmentassignment", "contentweaponprofile")
                        },
                    },
                ),
                migrations.AlterField(
                    model_name="listfighterequipmentassignment",
                    name="weapon_profiles_field",
                    field=models.ManyToManyField(
                        blank=True,
                        help_text="Select the costed weapon profiles to assign to this equipment. The standard profiles are automatically included in the cost of the equipment.",
                        related_name="weapon_profiles",
                        through="core.ListFighterEquipmentAssignmentProfile",
                        to="content.contentweaponprofile",
                        verbose_name="weapon profiles",
                    ),
                ),
                migrations.CreateModel(
                    name="ListFighterEquipmentAssignmentUpgrade",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "contentequipmentupgrade",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="+",
                                to="content.contentequipmentupgrade",
                            ),
                        ),
                        (
                            "listfighterequipmentassignment",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="upgrade_rows",
                                to="core.listfighterequipmentassignment",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "equipment upgrade row",
                        "verbose_name_plural": "equipment upgrade rows",
                        "db_table": "core_listfighterequipmentassignment_upgrades_field",
                        "unique_together": {
                            (
                                "listfighterequipmentassignment",
                                "contentequipmentupgrade",
                            )
                        },
                    },
                ),
                migrations.AlterField(
                    model_name="listfighterequipmentassignment",
                    name="upgrades_field",
                    field=models.ManyToManyField(
                        blank=True,
                        help_text="The upgrades that this equipment assignment has.",
                        related_name="fighter_equipment_assignments",
                        through="core.ListFighterEquipmentAssignmentUpgrade",
                        to="content.contentequipmentupgrade",
                    ),
                ),
            ],
        ),
    ]
