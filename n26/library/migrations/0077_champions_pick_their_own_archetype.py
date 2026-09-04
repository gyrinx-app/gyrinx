"""The Champion's Archetype choice gets pickables of its own.

One picklist served both the gang's Archetype and the Champion's, so one
pickable carried both readings of the same archetype and its modifiers
could be scoped correctly for only one of them. This builds the Champion
a picklist of five pickables of its own, hands each the modifiers that
were only ever the Champion's, and points the Champion's slot at the new
list. ``n26/library/champion_archetypes.py`` states the rules and holds
the ids.

A library without the Outcast content — a fresh database, anyone's
checkout before the content is loaded — is left exactly as it stands.
Nothing is unpicked in reverse: the pickables the Champion's picks now
name would be deleted out from under them.
"""

from django.db import migrations

from n26.library.champion_archetypes import make_champion_archetypes


def split_the_archetypes(apps, schema_editor):
    for line in make_champion_archetypes(apps):
        print(f"[archetypes] {line}")


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0076_contributes_to_counter_and_counter_drawn"),
    ]

    operations = [
        migrations.RunPython(split_the_archetypes, migrations.RunPython.noop),
    ]
