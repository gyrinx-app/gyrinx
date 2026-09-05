"""The ``income`` column comes off the asset.

Every figure it held is an Income contribution on the asset's modifiers
after the previous migration, and ``Asset.income`` now reads that. The
reverse puts the column back at 0; the previous migration's reverse
fills it in.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0086_income_is_a_counter_that_assets_contribute_to"),
    ]

    operations = [
        migrations.RemoveField(model_name="asset", name="income"),
    ]
