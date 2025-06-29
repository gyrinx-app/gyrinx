# Generated by Django 5.2.2 on 2025-06-10 22:07

import django.db.models.deletion
import simple_history.models
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0107_update_injury_phase_to_default_outcome"),
        ("core", "0061_add_xp_tracking_to_listfighter"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="HistoricalListFighterAdvancement",
            fields=[
                ("archived", models.BooleanField(default=False)),
                ("archived_at", models.DateTimeField(blank=True, null=True)),
                (
                    "id",
                    models.UUIDField(db_index=True, default=uuid.uuid4, editable=False),
                ),
                ("created", models.DateTimeField(blank=True, editable=False)),
                ("modified", models.DateTimeField(blank=True, editable=False)),
                (
                    "advancement_type",
                    models.CharField(
                        choices=[
                            ("stat", "Characteristic Increase"),
                            ("skill", "New Skill"),
                        ],
                        help_text="The type of advancement purchased.",
                        max_length=10,
                    ),
                ),
                (
                    "stat_increased",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("movement", "Movement"),
                            ("weapon_skill", "Weapon Skill"),
                            ("ballistic_skill", "Ballistic Skill"),
                            ("strength", "Strength"),
                            ("toughness", "Toughness"),
                            ("wounds", "Wounds"),
                            ("initiative", "Initiative"),
                            ("attacks", "Attacks"),
                            ("leadership", "Leadership"),
                            ("cool", "Cool"),
                            ("willpower", "Willpower"),
                            ("intelligence", "Intelligence"),
                        ],
                        help_text="For stat increases, which characteristic was improved.",
                        max_length=20,
                        null=True,
                    ),
                ),
                (
                    "xp_cost",
                    models.PositiveIntegerField(
                        help_text="The XP cost of this advancement."
                    ),
                ),
                (
                    "cost_increase",
                    models.IntegerField(
                        default=0,
                        help_text="The increase in fighter cost from this advancement.",
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
                    "campaign_action",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        help_text="The campaign action recording the dice roll for this advancement.",
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="core.campaignaction",
                    ),
                ),
                (
                    "fighter",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        help_text="The fighter who purchased this advancement.",
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="core.listfighter",
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
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "skill",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        help_text="For skill advancements, which skill was gained.",
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="content.contentskill",
                    ),
                ),
            ],
            options={
                "verbose_name": "historical Fighter Advancement",
                "verbose_name_plural": "historical Fighter Advancements",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="ListFighterAdvancement",
            fields=[
                ("archived", models.BooleanField(default=False)),
                ("archived_at", models.DateTimeField(blank=True, null=True)),
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
                (
                    "advancement_type",
                    models.CharField(
                        choices=[
                            ("stat", "Characteristic Increase"),
                            ("skill", "New Skill"),
                        ],
                        help_text="The type of advancement purchased.",
                        max_length=10,
                    ),
                ),
                (
                    "stat_increased",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("movement", "Movement"),
                            ("weapon_skill", "Weapon Skill"),
                            ("ballistic_skill", "Ballistic Skill"),
                            ("strength", "Strength"),
                            ("toughness", "Toughness"),
                            ("wounds", "Wounds"),
                            ("initiative", "Initiative"),
                            ("attacks", "Attacks"),
                            ("leadership", "Leadership"),
                            ("cool", "Cool"),
                            ("willpower", "Willpower"),
                            ("intelligence", "Intelligence"),
                        ],
                        help_text="For stat increases, which characteristic was improved.",
                        max_length=20,
                        null=True,
                    ),
                ),
                (
                    "xp_cost",
                    models.PositiveIntegerField(
                        help_text="The XP cost of this advancement."
                    ),
                ),
                (
                    "cost_increase",
                    models.IntegerField(
                        default=0,
                        help_text="The increase in fighter cost from this advancement.",
                    ),
                ),
                (
                    "campaign_action",
                    models.OneToOneField(
                        blank=True,
                        help_text="The campaign action recording the dice roll for this advancement.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="advancement",
                        to="core.campaignaction",
                    ),
                ),
                (
                    "fighter",
                    models.ForeignKey(
                        help_text="The fighter who purchased this advancement.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="advancements",
                        to="core.listfighter",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "skill",
                    models.ForeignKey(
                        blank=True,
                        help_text="For skill advancements, which skill was gained.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="content.contentskill",
                    ),
                ),
            ],
            options={
                "verbose_name": "Fighter Advancement",
                "verbose_name_plural": "Fighter Advancements",
                "ordering": ["fighter", "created"],
            },
        ),
    ]
