"""An asset's income is a contribution to the system Income counter.

The Territory campaign type gains a third built-in: an **Income** counter
in the system pack, at 0, beside Reputation, so every gang in a campaign
has a reading to add to. ``seed_core_campaign`` creates what is missing
and leaves what stands. A built-in added by hand reaches only gangs that
join afterwards, so a propagation pass is filed for the type's set the
way an authoring edit files one — the row alone, since the sweep
publishes any pass left pending — and gangs already at a table receive
the counter when it runs.

Then every asset whose ``income`` column holds a figure gets a modifier
saying the same thing the way the engine reads it: a ``TargetsGang``
scope kept the gang's alone, and a ``ContributesToCounter`` effect adding
that figure to Income, in the asset's own pack and attached to the asset.
An asset already carrying such a contribution is left as it is, so a
database this has been through once is not given a second. The column
itself goes in the next migration, once the figures are safe here.

Reversible: the reverse writes each asset's Income contributions back
into the column as one sum, and deletes the modifiers it made. The seed
is not undone.
"""

from django.db import migrations

from n26.library.core_campaign import CAMPAIGN_TYPE, seed_core_campaign
from n26.library.income import INCOME, income_modifier_name, is_income_counter


def _income_counter(apps):
    Counter = apps.get_model("library", "Counter")
    ContentPack = apps.get_model("library", "ContentPack")
    pack = ContentPack.objects.get(slug=_default_pack_slug())
    return Counter.objects.get(pack=pack, name__iexact=INCOME, qualifier="")


def _default_pack_slug():
    from django.conf import settings

    return settings.DEFAULT_CONTENT_PACK_SLUG


def _contributions(asset):
    """The asset's Income contributions, read off its modifiers."""
    return [
        row
        for row in asset.modifiers.select_related("contributes_to_counter__counter")
        if row.targets_gang_id is not None
        and row.contributes_to_counter_id is not None
        and is_income_counter(row.contributes_to_counter.counter)
    ]


def _file_propagation(apps, lines):
    """One pass for the Territory campaign's built-ins set, only where the
    seed just built Income in: a set nothing changed on owes no pass."""
    if not any(line.startswith(f"built {INCOME}") for line in lines):
        return
    CampaignType = apps.get_model("library", "CampaignType")
    BuiltInPropagationTask = apps.get_model("n26", "BuiltInPropagationTask")
    campaign_type = CampaignType.objects.get(
        pack__slug=_default_pack_slug(), name__iexact=CAMPAIGN_TYPE, qualifier=""
    )
    BuiltInPropagationTask.objects.create(default_set_id=campaign_type.built_ins_id)
    print(f"[core campaign] filed a built-in propagation pass for {CAMPAIGN_TYPE}")


def convert(apps, schema_editor):
    lines = seed_core_campaign(apps)
    for line in lines:
        print(f"[core campaign] {line}")
    _file_propagation(apps, lines)
    Asset = apps.get_model("library", "Asset")
    Modifier = apps.get_model("library", "Modifier")
    TargetsGang = apps.get_model("library", "TargetsGang")
    ContributesToCounter = apps.get_model("library", "ContributesToCounter")
    income = _income_counter(apps)

    converted = skipped = 0
    for asset in Asset.objects.filter(income__gt=0).order_by("name"):
        if _contributions(asset):
            skipped += 1
            continue
        row = Modifier.objects.create(
            pack_id=asset.pack_id,
            name=income_modifier_name(asset, Modifier, asset.pack_id),
            targets_gang=TargetsGang.objects.create(echoes=False),
            contributes_to_counter=ContributesToCounter.objects.create(
                counter=income, amount=asset.income
            ),
        )
        asset.modifiers.add(row)
        converted += 1
    print(
        f"[asset income] {converted} converted to an Income contribution, "
        f"{skipped} already carrying one"
    )


def restore(apps, schema_editor):
    Asset = apps.get_model("library", "Asset")
    for asset in Asset.objects.all():
        rows = _contributions(asset)
        if not rows:
            continue
        asset.income = sum(row.contributes_to_counter.amount for row in rows)
        asset.save(update_fields=["income"])
        for row in rows:
            scope, effect = row.targets_gang, row.contributes_to_counter
            row.delete()
            scope.delete()
            effect.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0084_asset_kind_becomes_asset_type_with_an_ownership"),
        # The propagation task table, so the pass can be filed from here.
        ("n26", "0029_a_set_change_files_a_built_in_propagation_task"),
    ]

    operations = [
        migrations.RunPython(convert, restore),
    ]
