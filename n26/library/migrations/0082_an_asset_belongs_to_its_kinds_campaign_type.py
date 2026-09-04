"""An asset belongs to a campaign type through its kind, and nothing else.

The campaign type's own list of assets goes. An asset names one kind
and a kind names one campaign type, so the list said nothing the kind's
column did not already say, and a second statement of one fact is a
place for the two to disagree. There is no data to carry across: every
asset a type listed was of one of that type's kinds, which is how it
came to be listed, so ``CampaignType.assets`` — now read through the
kinds — answers exactly as the table did.

The asset's kind column also gets the words that say how it is settled;
its shape is unchanged.

Reversible: the table comes back empty, and the seed and the authoring
pages no longer write to it.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0081_the_n26_core_campaign_type"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="campaigntype",
            name="assets",
        ),
        migrations.AlterField(
            model_name="asset",
            name="kind",
            field=models.ForeignKey(
                help_text="Which kind this asset is one of. Settled when the asset is made on its campaign type's page, and never changed afterwards.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="assets",
                to="library.assetkind",
            ),
        ),
    ]
