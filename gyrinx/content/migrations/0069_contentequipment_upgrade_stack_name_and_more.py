# Generated by Django 5.1.5 on 2025-02-10 21:30

import django.db.models.deletion
import simple_history.models
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0068_alter_contentfighterhouseoverride_unique_together"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="contentequipment",
            name="upgrade_stack_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="If applicable, the name of the stack of upgrades for this equipment (e.g. Upgrade or Augmentation). Use the singular form.",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="historicalcontentequipment",
            name="upgrade_stack_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="If applicable, the name of the stack of upgrades for this equipment (e.g. Upgrade or Augmentation). Use the singular form.",
                max_length=255,
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="ContentEquipmentUpgrade",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("modified", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=255, unique=True)),
                (
                    "position",
                    models.IntegerField(
                        default=0,
                        help_text="The position in which this upgrade sits in the stack.",
                    ),
                ),
                (
                    "cost",
                    models.IntegerField(
                        default=0,
                        help_text="The credit cost of the equipment upgrade. Costs are cumulative based on position.",
                    ),
                ),
                (
                    "equipment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="upgrades",
                        to="content.contentequipment",
                    ),
                ),
            ],
            options={
                "verbose_name": "Equipment Upgrade",
                "verbose_name_plural": "Equipment Upgrades",
                "ordering": ["equipment__name", "name"],
            },
        ),
        migrations.CreateModel(
            name="HistoricalContentEquipmentUpgrade",
            fields=[
                (
                    "id",
                    models.UUIDField(db_index=True, default=uuid.uuid4, editable=False),
                ),
                ("created", models.DateTimeField(blank=True, editable=False)),
                ("modified", models.DateTimeField(blank=True, editable=False)),
                ("name", models.CharField(db_index=True, max_length=255)),
                (
                    "position",
                    models.IntegerField(
                        default=0,
                        help_text="The position in which this upgrade sits in the stack.",
                    ),
                ),
                (
                    "cost",
                    models.IntegerField(
                        default=0,
                        help_text="The credit cost of the equipment upgrade. Costs are cumulative based on position.",
                    ),
                ),
                ("history_id", models.AutoField(primary_key=True, serialize=False)),
                ("history_date", models.DateTimeField(db_index=True)),
                ("history_change_reason", models.CharField(max_length=100, null=True)),
                (
                    "history_type",
                    models.CharField(
                        choices=[("+", "Created"), ("~", "Changed"), ("-", "Deleted")],
                        max_length=1,
                    ),
                ),
                (
                    "equipment",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="content.contentequipment",
                    ),
                ),
                (
                    "history_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "historical Equipment Upgrade",
                "verbose_name_plural": "historical Equipment Upgrades",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
    ]
