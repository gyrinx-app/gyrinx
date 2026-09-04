"""The N26 core campaign type, its asset kinds, and Reputation.

Reputation becomes a counter in the system pack; the N26 core type
declares Settlement (held one each) and Territory (pooled), offers a
Settlement asset, and gives every member gang Reputation at 0 and the
Settlement through its built-ins. ``n26/library/core_campaign.py``
holds the rows and matches each on its natural key, so a database that
already has any of them is left as it stands.

Nothing is removed in reverse: a campaign founded on the type would be
left standing on nothing.
"""

from django.db import migrations

from n26.library.core_campaign import seed_core_campaign


def seed(apps, schema_editor):
    for line in seed_core_campaign(apps):
        print(f"[core campaign] {line}")


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0080_campaign_type_asset_kind_and_asset"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
