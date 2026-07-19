from django.db import migrations


def backfill_recorded_winners(apps, schema_editor):
    """Ended battles that already have winners had their result recorded.

    ``0169`` deliberately left ``result`` blank for every existing row so that
    battles nobody ever filled in read as "no result recorded" rather than being
    retroactively called a draw. But an ended battle that *does* have winners is
    not unrecorded — somebody set them through the edit form — and leaving it
    blank would show "No result was recorded" next to the winner's trophy.

    Battles with no winners are deliberately left blank: we cannot tell a real
    draw from one nobody filled in, and guessing either way would invent history.
    """
    Battle = apps.get_model("core", "Battle")
    ids = list(
        Battle.objects.filter(status="post_battle", winners__isnull=False)
        .values_list("pk", flat=True)
        .distinct()
    )
    if ids:
        Battle.objects.filter(pk__in=ids).update(result="winners")


class Migration(migrations.Migration):
    """Reversing is a no-op, deliberately.

    Nothing records which rows this backfill touched, so a reverse could only
    guess from the same "post-battle and has winners" shape — which by then also
    matches every battle ended *after* this ran, whose result was recorded
    properly. Clearing those would destroy real data to undo a backfill, so
    going back simply leaves the values in place. The column itself only
    disappears when 0169 is reversed.
    """

    dependencies = [
        ("core", "0175_crew_loadout_overrides"),
    ]

    operations = [
        migrations.RunPython(backfill_recorded_winners, migrations.RunPython.noop),
    ]
