# Generated by Django 5.1.2 on 2024-11-24 17:16

import django.db.models.deletion
import simple_history.models
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0006_contentequipment_trading_post_available_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ContentWeaponProfile",
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
                ("name", models.CharField(max_length=255)),
                ("Rng S", models.CharField(blank=True, max_length=12, null=True)),
                ("Rng L", models.CharField(blank=True, max_length=12, null=True)),
                ("Acc S", models.CharField(blank=True, max_length=12, null=True)),
                ("Acc L", models.CharField(blank=True, max_length=12, null=True)),
                ("Str", models.CharField(blank=True, max_length=12, null=True)),
                ("Ap", models.CharField(blank=True, max_length=12, null=True)),
                ("D", models.CharField(blank=True, max_length=12, null=True)),
                ("Am", models.CharField(blank=True, max_length=12, null=True)),
            ],
            options={
                "verbose_name": "Content Weapon Profile",
                "verbose_name_plural": "Content Weapon Profiles",
            },
        ),
        migrations.CreateModel(
            name="ContentWeaponTrait",
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
                ("name", models.CharField(max_length=255)),
            ],
            options={
                "verbose_name": "Content Weapon Trait",
                "verbose_name_plural": "Content Weapon Traits",
            },
        ),
        migrations.RemoveField(
            model_name="contentequipment",
            name="trading_post_available",
        ),
        migrations.RemoveField(
            model_name="contentequipment",
            name="trading_post_cost",
        ),
        migrations.RemoveField(
            model_name="historicalcontentequipment",
            name="trading_post_available",
        ),
        migrations.RemoveField(
            model_name="historicalcontentequipment",
            name="trading_post_cost",
        ),
        migrations.AddField(
            model_name="contentequipment",
            name="rarity",
            field=models.CharField(
                blank=True,
                choices=[
                    ("R", "Rare (R)"),
                    ("I", "Illegal (I)"),
                    ("E", "Exclusive (E)"),
                    ("C", "Common (C)"),
                ],
                max_length=1,
            ),
        ),
        migrations.AddField(
            model_name="contentequipment",
            name="rarity_roll",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="historicalcontentequipment",
            name="rarity",
            field=models.CharField(
                blank=True,
                choices=[
                    ("R", "Rare (R)"),
                    ("I", "Illegal (I)"),
                    ("E", "Exclusive (E)"),
                    ("C", "Common (C)"),
                ],
                max_length=1,
            ),
        ),
        migrations.AddField(
            model_name="historicalcontentequipment",
            name="rarity_roll",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="ContentWeaponProfileAssignment",
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
                ("name", models.CharField(blank=True, max_length=255, null=True)),
                ("cost", models.IntegerField(default=0)),
                (
                    "equipment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="content.contentequipment",
                    ),
                ),
                (
                    "profile",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="content.contentweaponprofile",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddField(
            model_name="contentequipment",
            name="weapon_profiles",
            field=models.ManyToManyField(
                blank=True,
                through="content.ContentWeaponProfileAssignment",
                to="content.contentweaponprofile",
            ),
        ),
        migrations.AddField(
            model_name="contentweaponprofile",
            name="traits",
            field=models.ManyToManyField(blank=True, to="content.contentweapontrait"),
        ),
        migrations.CreateModel(
            name="HistoricalContentWeaponProfile",
            fields=[
                (
                    "id",
                    models.UUIDField(db_index=True, default=uuid.uuid4, editable=False),
                ),
                ("created", models.DateTimeField(blank=True, editable=False)),
                ("modified", models.DateTimeField(blank=True, editable=False)),
                ("name", models.CharField(max_length=255)),
                ("Rng S", models.CharField(blank=True, max_length=12, null=True)),
                ("Rng L", models.CharField(blank=True, max_length=12, null=True)),
                ("Acc S", models.CharField(blank=True, max_length=12, null=True)),
                ("Acc L", models.CharField(blank=True, max_length=12, null=True)),
                ("Str", models.CharField(blank=True, max_length=12, null=True)),
                ("Ap", models.CharField(blank=True, max_length=12, null=True)),
                ("D", models.CharField(blank=True, max_length=12, null=True)),
                ("Am", models.CharField(blank=True, max_length=12, null=True)),
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
                "verbose_name": "historical Content Weapon Profile",
                "verbose_name_plural": "historical Content Weapon Profiles",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="HistoricalContentWeaponProfileAssignment",
            fields=[
                (
                    "id",
                    models.UUIDField(db_index=True, default=uuid.uuid4, editable=False),
                ),
                ("created", models.DateTimeField(blank=True, editable=False)),
                ("modified", models.DateTimeField(blank=True, editable=False)),
                ("name", models.CharField(blank=True, max_length=255, null=True)),
                ("cost", models.IntegerField(default=0)),
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
                (
                    "profile",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="content.contentweaponprofile",
                    ),
                ),
            ],
            options={
                "verbose_name": "historical content weapon profile assignment",
                "verbose_name_plural": "historical content weapon profile assignments",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="HistoricalContentWeaponTrait",
            fields=[
                (
                    "id",
                    models.UUIDField(db_index=True, default=uuid.uuid4, editable=False),
                ),
                ("created", models.DateTimeField(blank=True, editable=False)),
                ("modified", models.DateTimeField(blank=True, editable=False)),
                ("name", models.CharField(max_length=255)),
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
                "verbose_name": "historical Content Weapon Trait",
                "verbose_name_plural": "historical Content Weapon Traits",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
    ]
