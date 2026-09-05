"""Every existing campaign is put on a type and given its pack and
additions; every gang playing one is given the two carriers with the
type's built-ins landed.

Campaigns written before types existed are put on the core campaign type,
matched by name in the system pack without regard to case. It is the one
type every install has, and the only thing a campaign could have been
played as before there was a choice; an arbitrator who wants another
type founds a new campaign. ``n26/core/campaign_packs.py`` holds the
logic and creates only what is missing, so it is safe to run again.

Nothing is undone in reverse: the packs, types and assignments written
here are ordinary rows that the columns' own removal leaves standing,
and a gang would otherwise be left holding grants whose cause had been
deleted from under them.
"""

from django.db import migrations

from n26.core.campaign_packs import give_campaigns_their_packs


def forwards(apps, schema_editor):
    for line in give_campaigns_their_packs(apps):
        print(f"[campaign packs] {line}")


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0081_the_n26_core_campaign_type"),
        ("n26", "0047_a_campaign_is_founded_on_a_type_with_a_pack_and_additions"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
