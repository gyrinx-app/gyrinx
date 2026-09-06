"""Every asset of a Possession asset type is built into the campaign type
that gives it.

A possession — a Settlement — is something every gang in a campaign has
its own of, and the way a campaign type gives anything to every gang is
its built-ins. Creating such an asset now builds it in on its own
(``n26.library.possessions``); this pass does the same for every
possession already standing that no live built-in member names, so a
type authored before the rule reads the same as one authored after.
Which type gives each asset follows the asset's pack: its asset type's
own campaign type, or the additions type of the campaign whose pack it
is in. Nothing is built in twice, so a database this has been through
is left as it is.

A member added by hand reaches only gangs that join afterwards, so one
propagation pass is filed for each set that gained a member — the row
alone, since the sweep publishes any pass left pending — and gangs
already at a table receive the asset when it runs.

Reversible as a no-op: the members made are content a campaign type now
maintains for itself, and taking them out would leave a type that stops
giving its Settlement.
"""

from django.db import migrations

from n26.library.possessions import build_in_missing


def build_in(apps, schema_editor):
    BuiltInPropagationTask = apps.get_model("n26", "BuiltInPropagationTask")
    made = build_in_missing(apps)
    for member in made:
        print(f"[possessions] built {member.asset.name} into {member.default_set.name}")
    for default_set_id in sorted({member.default_set_id for member in made}, key=str):
        BuiltInPropagationTask.objects.create(default_set_id=default_set_id)
    if made:
        sets = len({member.default_set_id for member in made})
        print(f"[possessions] filed a built-in propagation pass for {sets} set(s)")


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0091_staged_content_may_be_opened_early"),
        # A campaign's pack and additions type, so an arbitrator's asset can
        # be given by the campaign it belongs to; and the propagation task
        # table, so the pass can be filed from here.
        ("n26", "0049_a_campaign_always_has_a_type_a_pack_and_additions"),
    ]

    operations = [
        migrations.RunPython(build_in, migrations.RunPython.noop),
    ]
