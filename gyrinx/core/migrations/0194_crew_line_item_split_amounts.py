from django.db import migrations, models


def split_amounts(apps, schema_editor):
    """Give existing line items the two amounts they now carry separately.

    Until now ``cost`` meant "credits value", and every entry's value counted
    towards the crew's rating regardless of how it was paid for. So the rating
    contribution of an existing row is its old cost.

    What it *paid* is the same number, except for free entries: those were
    recorded at their worth, and the whole point of the split is that a free
    thing is worth something but costs nothing.
    """
    for model_name in ("CrewLineItem", "HistoricalCrewLineItem"):
        # The history table gets the same treatment as the live one. Left
        # alone, every pre-existing history row would claim the item was worth
        # nothing, and reverting one through django-simple-history would write
        # that zero onto the live item.
        model = apps.get_model("core", model_name)
        model.objects.update(rating_value=models.F("cost"))
        model.objects.filter(payment="free").update(cost=0)


def unsplit_amounts(apps, schema_editor):
    """Fold the two amounts back into one. A free entry recovers its worth from
    rating_value, which is where it moved."""
    for model_name in ("CrewLineItem", "HistoricalCrewLineItem"):
        model = apps.get_model("core", model_name)
        model.objects.filter(payment="free").update(cost=models.F("rating_value"))


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0193_crew_line_item_rating_value"),
    ]

    operations = [
        migrations.RunPython(split_amounts, unsplit_amounts),
    ]
