"""Promote Campaign.packs to a through-model so packs can be flagged as required.

The existing implicit M2M join table (`core_campaign_packs`) keeps its data —
state-only operations introduce the through model and rewire `Campaign.packs`,
while the database is only altered to add the new `required` column.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0142_add_featured_fields_to_custom_content_pack"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="CampaignContentPack",
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
                            "required",
                            models.BooleanField(
                                default=False,
                                help_text=(
                                    "If true, every list in this campaign must "
                                    "be subscribed to this pack."
                                ),
                            ),
                        ),
                        (
                            "campaign",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="pack_links",
                                to="core.campaign",
                            ),
                        ),
                        (
                            "pack",
                            models.ForeignKey(
                                db_column="customcontentpack_id",
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="campaign_links",
                                to="core.customcontentpack",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "core_campaign_packs",
                        "unique_together": {("campaign", "pack")},
                    },
                ),
                migrations.AlterField(
                    model_name="campaign",
                    name="packs",
                    field=models.ManyToManyField(
                        blank=True,
                        help_text=(
                            "Content packs allowed for this campaign. "
                            "Empty means no restrictions."
                        ),
                        related_name="campaigns",
                        through="core.CampaignContentPack",
                        to="core.customcontentpack",
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE core_campaign_packs "
                        "ADD COLUMN required boolean NOT NULL DEFAULT false;"
                    ),
                    reverse_sql=(
                        "ALTER TABLE core_campaign_packs DROP COLUMN required;"
                    ),
                ),
            ],
        ),
    ]
