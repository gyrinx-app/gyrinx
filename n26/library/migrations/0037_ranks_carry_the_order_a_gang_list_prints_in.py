from django.db import migrations

#: The order a gang list prints its ranks in, per section. An editorial
#: fact about the game, spelled out rather than derived — a later
#: position edited in the admin is an author saying something this
#: migration should not say again. The first edition's roster order is
#: the reference: leader, champions, prospects, gangers, then the
#: models a fighter brings rather than the gang hires.
PRINTED_RANKS = {
    "Gang List": (
        "Leader",
        "Champion",
        "Prospect",
        "Ganger",
        "Juve",
        "Brute",
        "Pet",
        "Vehicle",
    ),
    "Supplementary Profiles": (
        "Champion",
        "Ganger",
        "Brute",
        "Hanger-on",
        "Pet",
    ),
}


def set_the_printed_order(apps, schema_editor):
    """Give every rank category the place its gang list prints it in.

    Every category carried position 0, so a roster sorted by rank fell
    back to the order the rows happened to be created in — and a gang
    sheet sorted its fighters by nothing at all. Matched by section and
    name across every pack, as the section ordering was: a category is
    the same rank wherever it is authored.
    """
    Category = apps.get_model("library", "Category")
    for section, names in PRINTED_RANKS.items():
        for position, name in enumerate(names):
            Category.objects.filter(section__name=section, name=name).update(
                position=position
            )


def flatten(apps, schema_editor):
    """Back to no order at all, which is what these rows said before."""
    Category = apps.get_model("library", "Category")
    for section, names in PRINTED_RANKS.items():
        Category.objects.filter(section__name=section, name__in=names).update(
            position=0
        )


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0036_a_set_may_offer_one_or_none"),
    ]

    operations = [
        migrations.RunPython(set_the_printed_order, flatten),
    ]
