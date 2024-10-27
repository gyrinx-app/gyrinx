# Generated by Django 5.1.2 on 2024-10-27 09:57

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0010_alter_contentfighterequipment_unique_together"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="contentimportversion",
            name="version",
        ),
        migrations.AlterField(
            model_name="contentcategory",
            name="name",
            field=models.CharField(
                choices=[
                    ("NONE", "None"),
                    ("LEADER", "Leader"),
                    ("CHAMPION", "Champion"),
                    ("GANGER", "Ganger"),
                    ("JUVE", "Juve"),
                    ("CREW", "Crew"),
                    ("EXOTIC_BEAST", "Exotic Beast"),
                    ("HANGER_ON", "Hanger-on"),
                    ("BRUTE", "Brute"),
                    ("HIRED_GUN", "Hired Gun"),
                    ("BOUNTY_HUNTER", "Bounty Hunter"),
                    ("HOUSE_AGENT", "House Agent"),
                    ("HIVE_SCUM", "Hive Scum"),
                    ("DRAMATIS_PERSONAE", "Dramatis Personae"),
                ],
                max_length=255,
            ),
        ),
        migrations.AlterField(
            model_name="contentcategory",
            name="version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="core.contentimportversion",
            ),
        ),
        migrations.AlterField(
            model_name="contentequipment",
            name="version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="core.contentimportversion",
            ),
        ),
        migrations.AlterField(
            model_name="contentequipmentcategory",
            name="name",
            field=models.CharField(
                choices=[
                    ("NONE", "None"),
                    ("AMMO", "Ammo"),
                    ("ARMOR", "Armor"),
                    ("BASIC_WEAPONS", "Basic Weapons"),
                    ("BIONICS", "Bionics"),
                    ("BODY_UPGRADES", "Body Upgrades"),
                    ("CHEMS", "Chems"),
                    ("CLOSE_COMBAT", "Close Combat"),
                    ("DRIVE_UPGRADES", "Drive Upgrades"),
                    ("ENGINE_UPGRADES", "Engine Upgrades"),
                    ("EQUIPMENT", "Equipment"),
                    ("GRENADES", "Grenades"),
                    ("HARDPOINT_UPGRADES", "Hardpoint Upgrades"),
                    ("HEAVY_WEAPONS", "Heavy Weapons"),
                    ("MOUNTS", "Mounts"),
                    ("PISTOLS", "Pistols"),
                    ("SPECIAL_WEAPONS", "Special Weapons"),
                    ("STATUS_ITEMS", "Status Items"),
                    ("VEHICLE_EQUIPMENT", "Vehicle Equipment"),
                ],
                max_length=255,
            ),
        ),
        migrations.AlterField(
            model_name="contentequipmentcategory",
            name="version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="core.contentimportversion",
            ),
        ),
        migrations.AlterField(
            model_name="contentfighter",
            name="version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="core.contentimportversion",
            ),
        ),
        migrations.AlterField(
            model_name="contentfighterequipment",
            name="version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="core.contentimportversion",
            ),
        ),
        migrations.AlterField(
            model_name="contenthouse",
            name="version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="core.contentimportversion",
            ),
        ),
        migrations.AlterField(
            model_name="contentpolicy",
            name="version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="core.contentimportversion",
            ),
        ),
        migrations.AlterField(
            model_name="contentskill",
            name="version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="core.contentimportversion",
            ),
        ),
    ]
