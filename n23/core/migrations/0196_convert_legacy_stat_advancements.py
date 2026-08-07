"""Move stat advancements off the legacy override fields onto the mod system.

Two disjoint passes, both keyed on (fighter, stat):

1. **Convert** — where legacy advancements exist, the override field holds the
   value they wrote. Clearing it and flipping the rows to the mod system leaves
   the displayed statline unchanged, provided the modifiers recompute exactly
   what the override held.

2. **Repair** — where *no* legacy advancement exists but the override matches
   what the modifiers produce anyway, the override and the advancements both
   apply and the improvement is counted twice. Clearing the override drops the
   duplicate. This state is produced by ``ListFighter.copy_attributes_to()``,
   which carried the override across while letting the copied advancement
   default onto the mod system.

Anything else is left alone and reported.

Both passes gate on what the mod system will actually compute — never on a
re-derivation of what the legacy code would have written. The two disagree.
The legacy path read the base from the fighter's stat columns and decided
direction and formatting from the *shape* of that string, so a Ballistic Skill
stored as "4" was "improved" to "5". The mod system reads the base from the
fighter's statline, which for a custom statline is a different value entirely
("4+"), and classifies the stat from its ``ContentStat`` row, giving "3+".
Gating on the legacy formula therefore passed fighters whose displayed stat
would move — the exact thing these passes exist to prevent.
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


def _shadowed_by_stat_override(StatOverride):
    """(fighter_id, stat) pairs whose legacy override field is not being read.

    A fighter on a custom statline reads its per-stat overrides from
    ``ListFighterStatOverride`` instead of the legacy ``*_override`` field.
    Where such a row exists the legacy override is inert, and so is the
    advancement that wrote it — converting would start applying an improvement
    that currently does nothing, moving the fighter's displayed stat.
    """
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
    # Deliberately uses the live models rather than the historical ones this
    # migration is handed. The question being asked — "will this fighter's card
    # still show the same value afterwards?" — is answered by how the app
    # computes a statline today: which base it reads, and how it classifies the
    # stat. Re-deriving that here is precisely what an earlier revision of this
    # migration got wrong.
    from n23.content.models.statline import ContentStat
    from n23.core.models.list import ListFighter, ListFighterStatOverride
    from n23.core.models.list.advancement import (
        AdvancementStatMod,
        ListFighterAdvancement,
    )
    from n23.core.models.util import ModContext

    grouped = _advancements_by_fighter_stat(ListFighterAdvancement)
    shadowed = _shadowed_by_stat_override(ListFighterStatOverride)
    fighter_ids = {fighter_id for fighter_id, _ in grouped}

    mod_ctx = ModContext(
        all_stats={
            stat["field_name"]: stat for stat in ContentStat.objects.all().values()
        }
    )

    def after_advancements(stat, base_value, count):
        """What the mod system shows for ``count`` advancements on ``base_value``.

        Returns None if the value cannot be modified. Stats are free text and
        production holds malformed ones (a stray underscore, say), which makes
        applying a modifier raise. That must not abort the deploy — an
        unusable value simply means this pair cannot be verified.
        """
        mod = AdvancementStatMod(stat)
        value = base_value
        try:
            for _ in range(count):
                value = mod.apply(value, mod_ctx)
        except ValueError, TypeError:
            return None
        return value

    converted_keys = []
    repaired = []
    left_alone = []

    fighters = ListFighter.objects.filter(id__in=fighter_ids).select_related(
        "content_fighter"
    )
    for fighter in fighters.iterator():
        statline_base = {
            stat["field_name"]: stat["value"]
            for stat in fighter.content_fighter_statline
        }
        cleared = {}

        for stat in STAT_FIELDS:
            counts = grouped.get((fighter.id, stat))
            if counts is None:
                continue
            legacy_count, mod_count = counts

            if (fighter.id, stat) in shadowed:
                left_alone.append((fighter.id, stat, None, "shadowed-by-stat-override"))
                continue

            override = getattr(fighter, f"{stat}_override", None)
            base = statline_base.get(stat)
            if base is None:
                left_alone.append((fighter.id, stat, override, "stat-not-in-statline"))
                continue

            if legacy_count:
                if override in (None, ""):
                    left_alone.append((fighter.id, stat, override, "no-override"))
                    continue
                expected = after_advancements(stat, base, legacy_count)
                if expected is None:
                    left_alone.append(
                        (fighter.id, stat, override, "unmodifiable-value")
                    )
                    continue
                if override != expected:
                    left_alone.append((fighter.id, stat, override, "mismatch"))
                    continue
                cleared[f"{stat}_override"] = None
                converted_keys.append((fighter.id, stat))
            elif mod_count and override not in (None, ""):
                if override == after_advancements(stat, base, mod_count):
                    cleared[f"{stat}_override"] = None
                    repaired.append((fighter.id, stat, override, base))
                else:
                    # Still worth reporting: an override sitting alongside
                    # mod-system advancements is being applied on top of them,
                    # so the stat may be inflated even though we cannot prove
                    # by how much.
                    left_alone.append(
                        (fighter.id, stat, override, "override-over-mod-advancements")
                    )

        if cleared:
            # Written with an UPDATE rather than save(): saving a fighter fires
            # post_save receivers that materialise child fighters and bump the
            # parent list's modified timestamp. Neither belongs in a migration
            # that is only clearing a stat field, and the timestamp churn would
            # reorder every affected gang for its owner.
            ListFighter.objects.filter(pk=fighter.pk).update(**cleared)

    # Flip only the advancements whose override was successfully cleared.
    for fighter_id, stat in converted_keys:
        ListFighterAdvancement.objects.filter(
            fighter_id=fighter_id,
            stat_increased=stat,
            advancement_type="stat",
            archived=False,
            uses_mod_system=False,
        ).update(uses_mod_system=True)

    # Archived legacy rows never reach the statline, so they carry no override
    # implication and can move across wholesale.
    archived_flipped = ListFighterAdvancement.objects.filter(
        uses_mod_system=False, archived=True
    ).update(uses_mod_system=True)

    print(
        f"\n  converted {len(converted_keys)} fighter/stat pairs to the mod system"
        f"\n  repaired {len(repaired)} double-counted stats"
        f"\n  flipped {archived_flipped} archived legacy advancements"
        f"\n  left {len(left_alone)} pairs alone"
    )
    for fighter_id, stat, override, base in repaired:
        print(
            f"  repaired: fighter={fighter_id} stat={stat} was={override!r} base={base!r}"
        )
    for fighter_id, stat, override, reason in left_alone:
        print(
            f"  left alone: fighter={fighter_id} stat={stat} override={override!r} ({reason})"
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
        # Stat classification is read from ContentStat rows, which this content
        # migration guarantees. Without the dependency the ordering is only
        # incidental, and running first would leave every stat unclassified.
        ("content", "0148_ensure_contentstat_entries_exist"),
    ]

    operations = [
        migrations.RunPython(convert, unconvert),
    ]
