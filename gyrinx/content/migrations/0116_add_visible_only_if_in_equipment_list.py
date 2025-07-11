# Generated by Django 5.2.4 on 2025-07-08 06:20

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0115_add_legacy_flag_to_contenthouse"),
    ]

    operations = [
        migrations.AddField(
            model_name="contentequipmentcategory",
            name="visible_only_if_in_equipment_list",
            field=models.BooleanField(
                default=False,
                help_text="If True, this category will only be visible on fighter cards if the fighter has equipment in this category in their equipment list.",
            ),
        ),
        migrations.AddField(
            model_name="historicalcontentequipmentcategory",
            name="visible_only_if_in_equipment_list",
            field=models.BooleanField(
                default=False,
                help_text="If True, this category will only be visible on fighter cards if the fighter has equipment in this category in their equipment list.",
            ),
        ),
    ]
