# Generated by Django 5.1.7 on 2025-03-27 07:09

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0080_contentequipmentupgrade_modifiers"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contentequipment",
            name="rarity",
            field=models.CharField(
                blank=True,
                choices=[
                    ("R", "Rare (R)"),
                    ("I", "Illegal (I)"),
                    ("E", "Exclusive (E)"),
                    ("U", "Unique (U)"),
                    ("C", "Common (C)"),
                ],
                default="C",
                help_text="Use 'E' to exclude this equipment from the Trading Post. Use 'U' for equipment that is unique to a fighter.",
                max_length=1,
                verbose_name="Availability",
            ),
        ),
        migrations.AlterField(
            model_name="historicalcontentequipment",
            name="rarity",
            field=models.CharField(
                blank=True,
                choices=[
                    ("R", "Rare (R)"),
                    ("I", "Illegal (I)"),
                    ("E", "Exclusive (E)"),
                    ("U", "Unique (U)"),
                    ("C", "Common (C)"),
                ],
                default="C",
                help_text="Use 'E' to exclude this equipment from the Trading Post. Use 'U' for equipment that is unique to a fighter.",
                max_length=1,
                verbose_name="Availability",
            ),
        ),
    ]
