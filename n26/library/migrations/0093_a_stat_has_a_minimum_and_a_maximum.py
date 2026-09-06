"""A stat carries the rulebook's minimum and maximum.

A characteristic is never worsened past its minimum or improved past its
maximum (core rules: characteristics and profiles); the part of a change
that would take it there is disregarded. Until now nothing on a stat
said where those limits were, so a third Spinal Injury took a Strength
of 3 to 0 and a fourth to -1.

The two fields are added blank, then filled for the thirteen model
characteristics in every pack, matched on the internal field name the
seed derives from the full name. A stat an author has already given a
limit keeps it. Weapon characteristics have no limits in the book and
are left blank; Strength is one definition shared by both shapes, so a
weapon's Strength stops at the same 1 and 10 a fighter's does.

Reversible: the fields go, and the values with them.
"""

from django.db import migrations, models

#: ``field_name: (minimum, maximum)``, as the number a cell stops at. A
#: roll target's limits read as its number, so a Save's minimum is 6 (6+)
#: and its maximum 3 (3+).
LIMITS = {
    "movement": (1, 12),
    "weapon_skill": (6, 2),
    "ballistic_skill": (6, 2),
    "strength": (1, 10),
    "toughness": (1, 10),
    "wounds": (0, 10),
    "initiative": (1, 10),
    "attacks": (1, 10),
    "save": (6, 3),
    "leadership": (4, 10),
    "cool": (4, 10),
    "willpower": (4, 10),
    "intelligence": (4, 10),
}


def fill_limits(apps, schema_editor):
    Stat = apps.get_model("library", "Stat")
    for field_name, (minimum, maximum) in LIMITS.items():
        filled = Stat.objects.filter(
            field_name__iexact=field_name, minimum__isnull=True, maximum__isnull=True
        ).update(minimum=minimum, maximum=maximum)
        if filled:
            print(
                f"[stat limits] {field_name}: {minimum}..{maximum} on {filled} row(s)"
            )


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0092_a_possession_is_built_into_its_campaign_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="stat",
            name="maximum",
            field=models.PositiveIntegerField(
                blank=True,
                help_text=(
                    "The value a change stops at when it improves this stat, "
                    "e.g. 10 for Strength, 2 for a 2+ Weapon Skill. Blank means "
                    "no limit."
                ),
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="stat",
            name="minimum",
            field=models.PositiveIntegerField(
                blank=True,
                help_text=(
                    "The value a change stops at when it worsens this stat, "
                    "e.g. 1 for Strength, 6 for a 6+ Save. Blank means no limit."
                ),
                null=True,
            ),
        ),
        migrations.RunPython(fill_limits, migrations.RunPython.noop),
    ]
