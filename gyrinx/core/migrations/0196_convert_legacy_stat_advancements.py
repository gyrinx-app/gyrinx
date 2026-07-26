"""Move stat advancements off the legacy override fields onto the mod system.

Two disjoint passes, both keyed on (fighter, stat):

1. **Convert** — where legacy advancements exist, the override field holds the
   value they wrote. Clearing it and flipping the rows to the mod system leaves
   the displayed statline unchanged, because the mods then recompute exactly
   what the override held.

2. **Repair** — where *no* legacy advancement exists but the override still
   matches what one would have written, the override and the mod-system
   advancements both apply and the improvement is counted twice. Clearing the
   override drops the duplicate. This state is produced by
   ``ListFighter.copy_attributes_to()``, which carried the override across
   while letting the copied advancement default onto the mod system.

Rows whose override cannot be explained by their advancements are left alone
and reported — they are manual stat edits, not advancement output.
"""

from django.db import migrations

STAT_FIELDS = [
    "movement",
    "weapon_skill",
    "ballistic_skill",
    "strength",
    "toughness",
    "wounds",
    "initiative",
    "attacks",
    "leadership",
    "cool",
    "willpower",
    "intelligence",
]


def improved(base_value, count):
    """The value the legacy path would have written after ``count`` improvements.

    Mirrors the arithmetic in the (now removed) legacy branch of
    ``ListFighterAdvancement.apply_advancement``. Returns None when the base
    cannot be parsed, which means the override cannot be attributed and the
    row must be left alone.
    """
    if not base_value or count < 1:
        return None

    # Target rolls improve downwards: "4+" -> "3+"
    if "+" in base_value:
        try:
            return f"{int(base_value.replace('+', '')) - count}+"
        except ValueError:
            return None

    try:
        value = str(int(base_value.replace('"', "")) + count)
    except ValueError:
        return None

    # Distances keep their quote mark: '4"' -> '5"'
    if '"' in base_value:
        return f'{value}"'
    return value


def _shadowed_by_stat_override(apps):
    """(fighter_id, stat) pairs whose legacy override field is not being read.

    A fighter on a custom statline reads its per-stat overrides from
    ``ListFighterStatOverride`` instead of the legacy ``*_override`` field.
    Where such a row exists the legacy override is inert, and so is the
    advancement that wrote it — converting it to a modifier would start
    applying an improvement that currently does nothing, moving the fighter's
    displayed stat. These carry an override in both stores and need
    reconciling by hand.
    """
    StatOverride = apps.get_model("core", "ListFighterStatOverride")
    return {
        (fighter_id, field_name)
        for fighter_id, field_name in StatOverride.objects.values_list(
            "list_fighter_id", "content_stat__stat__field_name"
        )
    }


def _advancements_by_fighter_stat(Advancement):
    """Live stat advancements grouped as {(fighter_id, stat): [legacy, mod]}."""
    grouped = {}
    rows = Advancement.objects.filter(
        advancement_type="stat", archived=False
    ).values_list("fighter_id", "stat_increased", "uses_mod_system")
    for fighter_id, stat, uses_mod_system in rows:
        if not stat:
            continue
        counts = grouped.setdefault((fighter_id, stat), [0, 0])
        counts[1 if uses_mod_system else 0] += 1
    return grouped


def convert(apps, schema_editor):
    Advancement = apps.get_model("core", "ListFighterAdvancement")
    ListFighter = apps.get_model("core", "ListFighter")

    grouped = _advancements_by_fighter_stat(Advancement)
    shadowed = _shadowed_by_stat_override(apps)
    fighter_ids = {fighter_id for fighter_id, _ in grouped}

    converted_keys = []
    repaired = []
    unattributed = []

    fighters = ListFighter.objects.filter(id__in=fighter_ids).select_related(
        "content_fighter"
    )
    for fighter in fighters.iterator():
        dirty = False
        for stat in STAT_FIELDS:
            counts = grouped.get((fighter.id, stat))
            if counts is None:
                continue
            legacy_count, mod_count = counts

            if (fighter.id, stat) in shadowed:
                unattributed.append(
                    (fighter.id, stat, None, None, "shadowed-by-stat-override")
                )
                continue

            override = getattr(fighter, f"{stat}_override", None)
            base = getattr(fighter.content_fighter, stat, None)

            if legacy_count:
                # Pass 1: the override is this fighter's legacy advancement
                # output. Only clear it if the arithmetic agrees — otherwise
                # something else wrote the value and converting would move the
                # displayed stat.
                if override in (None, ""):
                    unattributed.append(
                        (fighter.id, stat, override, base, "no-override")
                    )
                    continue
                if override != improved(base, legacy_count):
                    unattributed.append((fighter.id, stat, override, base, "mismatch"))
                    continue
                setattr(fighter, f"{stat}_override", None)
                dirty = True
                converted_keys.append((fighter.id, stat))
            elif mod_count and override not in (None, ""):
                # Pass 2: no legacy advancement, yet the override looks exactly
                # like advancement output — the improvement is being applied
                # twice. Anything else is a manual edit and stays.
                if override == improved(base, mod_count):
                    setattr(fighter, f"{stat}_override", None)
                    dirty = True
                    repaired.append((fighter.id, stat, override, base, mod_count))

        if dirty:
            fighter.save()

    # Flip only the advancements whose override was successfully cleared.
    for fighter_id, stat in converted_keys:
        Advancement.objects.filter(
            fighter_id=fighter_id,
            stat_increased=stat,
            advancement_type="stat",
            archived=False,
            uses_mod_system=False,
        ).update(uses_mod_system=True)

    # Archived legacy rows never reach the statline, so they carry no override
    # implication and can move across wholesale.
    archived_flipped = Advancement.objects.filter(
        uses_mod_system=False, archived=True
    ).update(uses_mod_system=True)

    print(
        f"\n  converted {len(converted_keys)} fighter/stat pairs to the mod system"
        f"\n  repaired {len(repaired)} double-counted stats"
        f"\n  flipped {archived_flipped} archived legacy advancements"
        f"\n  left {len(unattributed)} unattributed overrides untouched"
    )
    for row in repaired:
        print(
            f"  repaired: fighter={row[0]} stat={row[1]} was={row[2]!r} base={row[3]!r}"
        )
    for row in unattributed:
        print(
            f"  unattributed: fighter={row[0]} stat={row[1]} override={row[2]!r} base={row[3]!r} ({row[4]})"
        )


def unconvert(apps, schema_editor):
    """Deliberately does nothing.

    Nothing records which advancements this migration flipped, so a reverse
    pass cannot tell them apart from the majority that were already on the mod
    system. Flipping every stat advancement back to the legacy system would
    corrupt those, which is far worse than being unable to reverse. Restore
    from a backup if this genuinely needs undoing.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0195_crew_credits_owed"),
    ]

    operations = [
        migrations.RunPython(convert, unconvert),
    ]
