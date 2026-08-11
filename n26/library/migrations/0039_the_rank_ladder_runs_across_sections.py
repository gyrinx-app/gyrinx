from django.db import migrations

#: One ladder for every rank a model can hold, whichever section its
#: category is filed in: the position is the rank itself, so a
#: supplementary Champion stands with the gang list's Champions and a
#: Hanger-on musters before the Vehicles. An editorial fact about the
#: game, spelled out rather than derived — a later position edited in
#: the admin is an author saying something this migration should not
#: say again. Pets, and anything not named here, sort after everything
#: named.
LADDER = (
    "Leader",
    "Champion",
    "Ganger",
    "Prospect",
    "Juve",
    "Brute",
    "Hanger-on",
    "Vehicle",
    "Pet",
)

#: The two sections whose categories are ranks. Weapon and skill
#: categories share names with nothing here, but scoping the update is
#: what keeps that true forever.
RANK_SECTIONS = ("Gang List", "Supplementary Profiles")

#: The per-section order this replaces, for the way back down.
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


def one_ladder(apps, schema_editor):
    """Rank every rank category on the one ladder.

    The roster sorts by category position alone, so two sections' ranks
    interleave: with per-section numbering a Hanger-on could only ever
    sort where its whole section sorts, which put every one of them
    after the Vehicles.
    """
    Category = apps.get_model("library", "Category")
    for position, name in enumerate(LADDER):
        Category.objects.filter(section__name__in=RANK_SECTIONS, name=name).update(
            position=position
        )


def per_section(apps, schema_editor):
    Category = apps.get_model("library", "Category")
    for section, names in PRINTED_RANKS.items():
        for position, name in enumerate(names):
            Category.objects.filter(section__name=section, name=name).update(
                position=position
            )


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0038_a_menu_collection_prices_nothing"),
    ]

    operations = [
        migrations.RunPython(one_ladder, per_section),
    ]
