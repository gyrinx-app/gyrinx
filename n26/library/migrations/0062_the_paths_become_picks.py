# The Cawdor Paths move onto slots and picks — the first converted
# system. The conversion module owns the whole discipline (plan, prove
# the pages unchanged, apply or refuse); this migration only runs it, so
# the rehearsal command and production perform the identical steps. On a
# database that never held the system — a fresh environment — the plan
# says nothing_here and this is a clean no-op.
#
# Deliberately irreversible: the forward run's report (printed to the
# migrate output) records every rewritten pick and retired row, and
# going back is a restore, not a migration.

from django.db import migrations


def convert(apps, schema_editor):
    from n26.library.conversion import apply, plan_paths

    for line in apply(plan_paths()):
        print(line)


class Migration(migrations.Migration):
    # A conversion migration runs live code, so it must order itself
    # after every migration that code's queries need — the heads at the
    # time it was written, not merely the columns it touches. A stale
    # database otherwise runs it too early and crashes mid-graph.
    dependencies = [
        ("library", "0061_reach_is_said_not_implied"),
        ("n26", "0014_the_owner_edits_what_a_model_is"),
    ]

    operations = [
        migrations.RunPython(convert, migrations.RunPython.noop),
    ]
