"""A campaign's pool: one CampaignAsset per copy of a pooled asset, naming
the membership that holds it, and a nullable link from a ledger event to
the token it was about, so a grant or a taking away can lead a reader to
the pool. The at-most-one constraint on ledger events widens to cover the
new subject.
"""

import django.db.models.deletion
import ulid
from django.conf import settings
from django.db import migrations, models

import n26.core.fields


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0081_the_n26_core_campaign_type"),
        ("n26", "0049_a_campaign_always_has_a_type_a_pack_and_additions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CampaignAsset",
            fields=[
                (
                    "id",
                    n26.core.fields.ULIDField(
                        default=ulid.ULID,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("modified", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "name",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="A name for this copy. Leave blank to use the asset's name.",
                        max_length=200,
                    ),
                ),
            ],
            options={
                "verbose_name": "campaign asset",
                "verbose_name_plural": "campaign assets",
                "ordering": ["asset__kind__position", "asset__name", "name", "created"],
            },
        ),
        migrations.RemoveConstraint(
            model_name="ledgerevent",
            name="ledger_event_about_at_most_one",
        ),
        migrations.AlterField(
            model_name="campaignevent",
            name="kind",
            field=models.CharField(
                choices=[
                    ("created", "Set up"),
                    ("renamed", "Renamed"),
                    ("budget_set", "Budget set"),
                    ("summary_edited", "Summary edited"),
                    ("archived", "Archived"),
                    ("battle_recorded", "Battle recorded"),
                    ("battle_removed", "Battle removed"),
                    ("invited", "Invited somebody"),
                    ("invite_accepted", "Invitation accepted"),
                    ("invite_declined", "Invitation declined"),
                    ("participant_removed", "Participant removed"),
                    ("asset_added", "Asset added to the pool"),
                    ("asset_dropped", "Asset dropped from the pool"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="campaignasset",
            name="asset",
            field=models.ForeignKey(
                help_text="The asset this is a copy of.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="tokens",
                to="library.asset",
            ),
        ),
        migrations.AddField(
            model_name="campaignasset",
            name="campaign",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="pool",
                to="n26.campaign",
            ),
        ),
        migrations.AddField(
            model_name="campaignasset",
            name="holder",
            field=models.ForeignKey(
                blank=True,
                help_text="The gang holding this copy. Blank when nobody holds it.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="held",
                to="n26.campaignmembership",
            ),
        ),
        migrations.AddField(
            model_name="ledgerevent",
            name="campaign_asset",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="n26.campaignasset",
            ),
        ),
        migrations.AddConstraint(
            model_name="ledgerevent",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("assignment__isnull", True), ("miniature__isnull", True)),
                    models.Q(
                        ("assignment__isnull", True), ("campaign_asset__isnull", True)
                    ),
                    models.Q(
                        ("campaign_asset__isnull", True), ("miniature__isnull", True)
                    ),
                    _connector="OR",
                ),
                name="ledger_event_about_at_most_one",
            ),
        ),
        migrations.AddIndex(
            model_name="campaignasset",
            index=models.Index(
                fields=["campaign", "holder"], name="campaign_asset_pool_idx"
            ),
        ),
    ]
