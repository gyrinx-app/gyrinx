from django.db import migrations

#: The order the book prints them in, which is the order a reader looks for
#: them in. Spelled out here rather than derived: it is an editorial fact
#: about the game, and a later position edited in the admin is an author
#: saying something this migration should not say again.
PRINTED_ORDER = (
    "Ranged weapons",
    "Close combat weapons",
    "Wargear",
    "Gang List",
    "Vehicle weapons",
    "Skills",
    "Wyrd Powers",
    "Supplementary Profiles",
)


def set_the_printed_order(apps, schema_editor):
    """Give every section the place it holds in the book.

    Nearly every section carried position 0, so a listing's tabs fell in
    whatever order their names happened to sort — close combat weapons
    ahead of ranged ones, which is not how anybody reads the book. A
    position is what the field is for; it had simply never been set.

    Matched by name across every pack: a section is the same heading
    wherever it is authored, and two packs both calling something
    "Wargear" mean the same thing by it.
    """
    Section = apps.get_model("library", "Section")
    for position, name in enumerate(PRINTED_ORDER):
        Section.objects.filter(name=name).update(position=position)


def flatten(apps, schema_editor):
    """Back to no order at all, which is what these rows said before."""
    Section = apps.get_model("library", "Section")
    Section.objects.filter(name__in=PRINTED_ORDER).update(position=0)


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0032_modifiers_can_grant_a_weapon"),
    ]

    operations = [
        migrations.RunPython(set_the_printed_order, flatten),
    ]
