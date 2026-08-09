# Hand-written: a data-only step, no schema change.
#
# A choice slot's label is stored the way a card shows it — first
# character capitalised, the rest left as the author typed it. Labels
# written before that rule are brought into line here; canonicalising on
# save only reaches rows that are saved again.

from django.db import migrations
from django.utils.text import capfirst


def labels_read_as_labels(apps, schema_editor):
    OffersChoice = apps.get_model("library", "OffersChoice")
    for pk, label in OffersChoice.objects.exclude(label="").values_list("pk", "label"):
        capitalised = capfirst(label)
        if capitalised != label:
            OffersChoice.objects.filter(pk=pk).update(label=capitalised)


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0026_gang_type_icon_url"),
    ]

    operations = [
        migrations.RunPython(labels_read_as_labels, migrations.RunPython.noop),
    ]
