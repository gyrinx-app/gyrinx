"""Unify a crew's picks onto CrewMember rows.

Attendance used to live in two places: ``Crew.chosen_fighters`` while the crew
was a draft, and ``CrewMember`` rows once it was locked. Members now exist from
selection time, tagged by how the fighter joined, so every read path is the
same at both stages.

Existing members take their ``source`` from ``was_random``, and draft crews get
member rows built from their picks. Locked crews already have their rows —
creating more would duplicate them and trip ``unique(crew, list_fighter)`` — so
they are left alone. The ``chosen_fighters`` M2M is deliberately left in place
(unread, unwritten) so this is reversible without losing the picks.

The historical rows are copied across too. 0173 drops ``was_random`` from the
historical table as well as the live one, so this is the only chance to carry
the value over: miss it and every past member keeps the ``source`` default and
the history claims for ever that fighters drawn at random were hand-picked.
"""

from django.db import migrations


def backfill_member_source(apps, schema_editor):
    CrewMember = apps.get_model("core", "CrewMember")
    HistoricalCrewMember = apps.get_model("core", "HistoricalCrewMember")
    Crew = apps.get_model("core", "Crew")

    for model in (CrewMember, HistoricalCrewMember):
        model.objects.filter(was_random=True).update(source="random")
        model.objects.filter(was_random=False).update(source="chosen")

    for crew in Crew.objects.filter(status="draft").iterator():
        present = set(crew.members.values_list("list_fighter_id", flat=True))
        CrewMember.objects.bulk_create(
            [
                CrewMember(
                    crew=crew,
                    list_fighter=fighter,
                    equipment_set=None,
                    source="chosen",
                    owner_id=crew.list.owner_id,
                    archived=False,
                )
                for fighter in crew.chosen_fighters.all()
                if fighter.id not in present
            ]
        )


def unbackfill_member_source(apps, schema_editor):
    """Restore ``was_random`` and take draft crews back to having no members —
    the state the old code expects, where a draft's attendance is read from
    ``chosen_fighters`` (still populated) and the lock creates the rows."""
    CrewMember = apps.get_model("core", "CrewMember")
    HistoricalCrewMember = apps.get_model("core", "HistoricalCrewMember")

    for model in (CrewMember, HistoricalCrewMember):
        model.objects.filter(source="random").update(was_random=True)
        model.objects.filter(source="chosen").update(was_random=False)
    CrewMember.objects.filter(crew__status="draft").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0171_crew_member_source"),
    ]

    operations = [
        migrations.RunPython(backfill_member_source, unbackfill_member_source),
    ]
