"""An asset kind is an asset type, and its mode is its ownership.

The model, its reverse name on the campaign type, the asset's link to it
and the field that says how its assets behave all take the words a reader
meets: an **asset type** with an **ownership** of Possession or Holding.
The stored ownership values stay as they were, so no row is rewritten;
only names change, and the unique constraint is renamed to match.
"""

import django.db.models.deletion
from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0083_the_core_campaign_type_is_the_territory_campaign"),
    ]

    operations = [
        migrations.RenameModel(old_name="AssetKind", new_name="AssetType"),
        migrations.RenameField(
            model_name="assettype", old_name="mode", new_name="ownership"
        ),
        migrations.RenameField(
            model_name="asset", old_name="kind", new_name="asset_type"
        ),
        migrations.AlterModelOptions(
            name="assettype",
            options={
                "ordering": ["campaign_type_id", "position", "label_singular"],
                "verbose_name": "asset type",
                "verbose_name_plural": "asset types",
            },
        ),
        migrations.RemoveConstraint(
            model_name="assettype",
            name="asset_kind_unique_label_per_type",
        ),
        migrations.AlterField(
            model_name="assettype",
            name="campaign_type",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="asset_types",
                to="library.campaigntype",
            ),
        ),
        migrations.AlterField(
            model_name="assettype",
            name="ownership",
            field=models.CharField(
                choices=[("held-one-each", "Possession"), ("pooled", "Holding")],
                help_text="Possession: every gang has its own and keeps it. Holding: one gang holds it at a time, and it can change hands.",
                max_length=20,
                verbose_name="Ownership",
            ),
        ),
        migrations.AlterField(
            model_name="assettype",
            name="position",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Where this asset type sits in the campaign's listing.",
            ),
        ),
        migrations.AlterField(
            model_name="asset",
            name="asset_type",
            field=models.ForeignKey(
                help_text="Which asset type this asset is one of. Settled when the asset is made on its campaign type's page, and never changed afterwards.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="assets",
                to="library.assettype",
                verbose_name="Asset type",
            ),
        ),
        migrations.AddConstraint(
            model_name="assettype",
            constraint=models.UniqueConstraint(
                models.F("campaign_type"),
                Lower("label_singular"),
                name="asset_type_unique_label_per_campaign_type",
            ),
        ),
    ]
