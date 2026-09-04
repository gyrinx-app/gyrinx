"""The three founding columns become required, now that every campaign
has a value for each.

Its own migration rather than the tail of the data migration before it:
altering a table in the same transaction as rows written to it is
refused by the database while those writes' triggers are pending.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("n26", "0048_existing_campaigns_get_a_type_a_pack_and_carriers"),
    ]

    operations = [
        migrations.AlterField(
            model_name="campaign",
            name="campaign_type",
            field=models.ForeignKey(
                help_text=(
                    "The campaign type this campaign was founded on. Every gang "
                    "that joins gets this type and everything that comes with it."
                ),
                on_delete=django.db.models.deletion.PROTECT,
                related_name="campaigns",
                to="library.campaigntype",
            ),
        ),
        migrations.AlterField(
            model_name="campaign",
            name="pack",
            field=models.OneToOneField(
                help_text=(
                    "The pack holding what the arbitrator creates for this campaign."
                ),
                on_delete=django.db.models.deletion.PROTECT,
                related_name="campaign",
                to="library.contentpack",
            ),
        ),
        migrations.AlterField(
            model_name="campaign",
            name="additions",
            field=models.OneToOneField(
                help_text=(
                    "This campaign's own campaign type, holding what the "
                    "arbitrator adds on top of the type the campaign was founded on."
                ),
                on_delete=django.db.models.deletion.PROTECT,
                related_name="additions_to",
                to="library.campaigntype",
            ),
        ),
    ]
