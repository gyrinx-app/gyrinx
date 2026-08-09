from django.db import migrations, models

import gyrinx.analytics.nouns

# Which edition each noun already in the table belongs to. Spelled out here
# rather than read from the registry so that re-running this migration on an
# old database keeps giving the same answer as it did the first time,
# whatever the registry has grown into since.
#
# Not every row is one edition's: signing in and dismissing a site banner
# happen on the way to both, and account events are the second-largest group
# in the table. Filing them under a game would have overstated that game's
# activity by about a fifth.
PLATFORM_NOUNS = ("user", "banner")


def edition_for_existing_noun(noun):
    """The edition to record against a row written before the column existed.

    Only two products had written events by then: the platform and n23.
    """
    return "platform" if noun in PLATFORM_NOUNS else "n23"


def backfill_edition(apps, schema_editor):
    """Give every existing row an edition.

    Two statements, not a walk: the table holds hundreds of thousands of rows
    and each one's answer depends on nothing but its noun.
    """
    Event = apps.get_model("analytics", "Event")
    Event.objects.filter(noun__in=PLATFORM_NOUNS).update(edition="platform")
    Event.objects.exclude(noun__in=PLATFORM_NOUNS).update(edition="n23")


def unset_edition(apps, schema_editor):
    Event = apps.get_model("analytics", "Event")
    Event.objects.update(edition="unknown")


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0001_move_event_to_analytics"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="edition",
            field=models.CharField(
                choices=[
                    ("platform", "Platform"),
                    ("n23", "N23"),
                    ("n26", "N26"),
                    ("unknown", "Unknown"),
                ],
                db_index=True,
                default="unknown",
                help_text="The edition (or the platform) the action happened in",
                max_length=20,
            ),
        ),
        migrations.RunPython(backfill_edition, unset_edition),
        migrations.AlterField(
            model_name="event",
            name="noun",
            field=models.CharField(
                choices=gyrinx.analytics.nouns.noun_choices,
                help_text="The type of object being acted upon",
                max_length=50,
            ),
        ),
    ]
