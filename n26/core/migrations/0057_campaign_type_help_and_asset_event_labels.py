"""The words on a campaign's type and on the two asset-copy event kinds.

Help text and choice labels only; no column changes shape and no row is
touched. The event kinds' labels stop naming a pool: a campaign keeps
copies of its assets, and the labels say so.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0083_the_core_campaign_type_is_the_territory_campaign"),
        ("n26", "0056_a_roll_on_a_table_is_put_on_the_record"),
    ]

    operations = [
        migrations.AlterField(
            model_name="campaign",
            name="campaign_type",
            field=models.ForeignKey(
                help_text="The campaign type this campaign was founded on. Every gang that joins is assigned this type and is given its built-ins.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="campaigns",
                to="library.campaigntype",
            ),
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
                    ("asset_added", "Asset copy added"),
                    ("asset_dropped", "Asset copy dropped"),
                ],
                max_length=20,
            ),
        ),
    ]
