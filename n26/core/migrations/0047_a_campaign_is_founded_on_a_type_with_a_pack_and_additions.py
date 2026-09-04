"""A campaign names the type it was founded on, its own pack, and its
additions type; a membership points at the gang's two carriers.

The three campaign columns arrive nullable here and are made required
in a later migration, once the data migration between them has given
every existing campaign a value for each. Adding them required at once
would need a default, and there is no campaign type or pack that could
honestly stand in for every campaign.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0081_the_n26_core_campaign_type"),
        ("n26", "0045_an_assignment_can_name_a_campaign_type_or_an_asset"),
    ]

    operations = [
        migrations.AddField(
            model_name="campaign",
            name="campaign_type",
            field=models.ForeignKey(
                help_text=(
                    "The campaign type this campaign was founded on. Every gang "
                    "that joins gets this type and everything that comes with it."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="campaigns",
                to="library.campaigntype",
            ),
        ),
        migrations.AddField(
            model_name="campaign",
            name="pack",
            field=models.OneToOneField(
                help_text=(
                    "The pack holding what the arbitrator creates for this campaign."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="campaign",
                to="library.contentpack",
            ),
        ),
        migrations.AddField(
            model_name="campaign",
            name="additions",
            field=models.OneToOneField(
                help_text=(
                    "This campaign's own campaign type, holding what the "
                    "arbitrator adds on top of the type the campaign was founded on."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="additions_to",
                to="library.campaigntype",
            ),
        ),
        migrations.AddField(
            model_name="campaignmembership",
            name="type_carrier",
            field=models.OneToOneField(
                blank=True,
                help_text=(
                    "The gang's assignment of the campaign's type. The type's "
                    "built-ins on this gang are caused by it."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="type_carrier_of",
                to="n26.assignment",
            ),
        ),
        migrations.AddField(
            model_name="campaignmembership",
            name="additions_carrier",
            field=models.OneToOneField(
                blank=True,
                help_text=(
                    "The gang's assignment of the campaign's additions type. What "
                    "the arbitrator adds to this campaign is caused by it."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="additions_carrier_of",
                to="n26.assignment",
            ),
        ),
    ]
