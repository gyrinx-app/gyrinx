"""Ensure the 'Fighter' ContentStatlineType and its stats exist.

Custom fighters created in Content Packs need a statline type to attach
their stats to. This migration guarantees the type and all standard
fighter stats exist.
"""

from django.db import migrations

# Standard fighter stats in display order.
_FIGHTER_STATS = [
    # (field_name, short_name, full_name, position, is_highlighted, is_first_of_group)
    ("movement", "M", "Movement", 1, False, False),
    ("weapon_skill", "WS", "Weapon Skill", 2, False, False),
    ("ballistic_skill", "BS", "Ballistic Skill", 3, False, False),
    ("strength", "S", "Strength", 4, False, False),
    ("toughness", "T", "Toughness", 5, False, False),
    ("wounds", "W", "Wounds", 6, False, False),
    ("initiative", "I", "Initiative", 7, False, False),
    ("attacks", "A", "Attacks", 8, False, False),
    ("leadership", "Ld", "Leadership", 9, True, True),
    ("cool", "Cl", "Cool", 10, True, False),
    ("willpower", "Wil", "Willpower", 11, True, False),
    ("intelligence", "Int", "Intelligence", 12, True, False),
]


def ensure_fighter_statline_type(apps, schema_editor):
    ContentStatlineType = apps.get_model("content", "ContentStatlineType")
    ContentStat = apps.get_model("content", "ContentStat")
    ContentStatlineTypeStat = apps.get_model("content", "ContentStatlineTypeStat")

    statline_type, _ = ContentStatlineType.objects.get_or_create(name="Fighter")

    for (
        field_name,
        short_name,
        full_name,
        position,
        highlighted,
        first_of_group,
    ) in _FIGHTER_STATS:
        stat, _ = ContentStat.objects.get_or_create(
            field_name=field_name,
            defaults={"short_name": short_name, "full_name": full_name},
        )
        ContentStatlineTypeStat.objects.get_or_create(
            statline_type=statline_type,
            stat=stat,
            defaults={
                "position": position,
                "is_highlighted": highlighted,
                "is_first_of_group": first_of_group,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0155_add_description_to_contentrule"),
    ]

    operations = [
        migrations.RunPython(
            ensure_fighter_statline_type,
            migrations.RunPython.noop,
        ),
    ]
