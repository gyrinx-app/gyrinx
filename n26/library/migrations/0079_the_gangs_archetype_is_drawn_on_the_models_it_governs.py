from django.db import migrations

from n26.library.archetype_display import MODIFIER_NAME, draw_gang_archetypes


def draw_it(apps, schema_editor):
    draw_gang_archetypes(apps)


def stop_drawing_it(apps, schema_editor):
    """Take the modifier off the archetypes and delete it.

    Its scope and effect go with it: both cascade from the columns
    holding them.
    """
    Modifier = apps.get_model("library", "Modifier")
    for row in Modifier.objects.filter(name__iexact=MODIFIER_NAME):
        scope, effect = row.targets_miniature, row.draws_pick
        row.delete()
        if scope is not None:
            scope.delete()
        if effect is not None:
            effect.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0078_a_pick_can_be_drawn_on_the_cards_it_reaches"),
    ]

    operations = [
        migrations.RunPython(draw_it, stop_drawing_it),
    ]
