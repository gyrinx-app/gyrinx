# Generated by Django 5.1.5 on 2025-01-25 07:24

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0057_contentweaponaccessory_rarity_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contentequipment",
            name="category",
            field=models.CharField(
                choices=[
                    ("AMMO", "Ammo"),
                    ("ARMOR", "Armor"),
                    ("BASIC_WEAPONS", "Basic Weapons"),
                    ("BIONICS", "Bionics"),
                    ("BODY_UPGRADES", "Body Upgrades"),
                    ("CHEMS", "Chems"),
                    ("CLOSE_COMBAT", "Close Combat Weapons"),
                    ("DRIVE_UPGRADES", "Drive Upgrades"),
                    ("ENGINE_UPGRADES", "Engine Upgrades"),
                    ("EQUIPMENT", "Personal Equipment"),
                    ("GRENADES", "Grenades"),
                    ("HARDPOINT_UPGRADES", "Hardpoint Upgrades"),
                    ("HEAVY_WEAPONS", "Heavy Weapons"),
                    ("MOUNTS", "Mounts"),
                    ("PISTOLS", "Pistols"),
                    ("SPECIAL_WEAPONS", "Special Weapons"),
                    ("STATUS_ITEMS", "Status Items"),
                    ("VEHICLE_EQUIPMENT", "Vehicle Wargear"),
                    ("BOOBY_TRAPS", "Booby Traps"),
                    ("GANG_TERRAIN", "Gang Terrain"),
                    ("CHEM_ALCHEMY_ELIXIRS", "Chem-alchemy Elixirs"),
                    ("GENE_SMITHING", "Gene-smithing"),
                    ("CYBERTEKNIKA", "Cyberteknika"),
                    ("FIELD_ARMOUR", "Field Armour"),
                    ("GANG_EQUIPMENT", "Gang Equipment"),
                    ("POWER_PACK_WEAPONS", "Power Pack Weapons"),
                    ("VEHICLES", "Vehicles"),
                    ("RELICS", "Relics"),
                ],
                max_length=255,
            ),
        ),
        migrations.AlterField(
            model_name="historicalcontentequipment",
            name="category",
            field=models.CharField(
                choices=[
                    ("AMMO", "Ammo"),
                    ("ARMOR", "Armor"),
                    ("BASIC_WEAPONS", "Basic Weapons"),
                    ("BIONICS", "Bionics"),
                    ("BODY_UPGRADES", "Body Upgrades"),
                    ("CHEMS", "Chems"),
                    ("CLOSE_COMBAT", "Close Combat Weapons"),
                    ("DRIVE_UPGRADES", "Drive Upgrades"),
                    ("ENGINE_UPGRADES", "Engine Upgrades"),
                    ("EQUIPMENT", "Personal Equipment"),
                    ("GRENADES", "Grenades"),
                    ("HARDPOINT_UPGRADES", "Hardpoint Upgrades"),
                    ("HEAVY_WEAPONS", "Heavy Weapons"),
                    ("MOUNTS", "Mounts"),
                    ("PISTOLS", "Pistols"),
                    ("SPECIAL_WEAPONS", "Special Weapons"),
                    ("STATUS_ITEMS", "Status Items"),
                    ("VEHICLE_EQUIPMENT", "Vehicle Wargear"),
                    ("BOOBY_TRAPS", "Booby Traps"),
                    ("GANG_TERRAIN", "Gang Terrain"),
                    ("CHEM_ALCHEMY_ELIXIRS", "Chem-alchemy Elixirs"),
                    ("GENE_SMITHING", "Gene-smithing"),
                    ("CYBERTEKNIKA", "Cyberteknika"),
                    ("FIELD_ARMOUR", "Field Armour"),
                    ("GANG_EQUIPMENT", "Gang Equipment"),
                    ("POWER_PACK_WEAPONS", "Power Pack Weapons"),
                    ("VEHICLES", "Vehicles"),
                    ("RELICS", "Relics"),
                ],
                max_length=255,
            ),
        ),
    ]
