"""The Territory Selection Table, as the core rulebook prints it.

One asset table of the Territory asset type in the system pack, rolled on
a D66, with an entry per Territory claiming its band of rolls — and the
Territory assets themselves where none stand yet, with no income and no
boons for the content pass that follows to fill in. Creating the table
builds it into the Territory campaign type by the rule every table follows
(``n26/library/tables.py``), so every gang that joins a campaign of that
type holds it and may roll on it; gangs already in such a campaign catch
up through the propagation pass filed here. Idempotent by name and pack
(``n26/library/territory_table.py``).

Reversible as a no-op: the rows made are core content a campaign type
now maintains for itself.
"""

from django.db import migrations

from n26.library.territory_table import seed_territory_table


def seed(apps, schema_editor):
    BuiltInPropagationTask = apps.get_model("n26", "BuiltInPropagationTask")
    lines, made = seed_territory_table(apps)
    for line in lines:
        print(f"[territory table] {line}")
    # One pass per set that gained a member — the row alone, since the
    # sweep publishes any pass left pending.
    for default_set_id in sorted({member.default_set_id for member in made}, key=str):
        BuiltInPropagationTask.objects.create(default_set_id=default_set_id)


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0099_asset_tables_are_held_by_gangs"),
        # The propagation task table, so the pass can be filed from here.
        ("n26", "0063_an_assignment_can_name_an_asset_table"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
