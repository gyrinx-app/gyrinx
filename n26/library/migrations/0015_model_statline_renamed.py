# The statline shape every model prints in is called "Model", not
# "Model characteristics". A rename rather than a new row: anything
# already pointing at the old one — profile types, and through them
# every profile — keeps working.

from django.db import migrations


def rename_forwards(apps, schema_editor):
    _rename(apps, "Model characteristics", "Model")


def rename_backwards(apps, schema_editor):
    _rename(apps, "Model", "Model characteristics")


def _rename(apps, old, new):
    StatlineType = apps.get_model("library", "StatlineType")
    for shape in StatlineType.objects.filter(name=old):
        # Only if the new name is free in that pack — a library that
        # already has both is one somebody built by hand, and guessing
        # which to keep would be worse than leaving it alone.
        if StatlineType.objects.filter(pack=shape.pack, name=new).exists():
            continue
        shape.name = new
        shape.save(update_fields=["name"])


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0014_profile_type_closed_set"),
    ]

    operations = [
        migrations.RunPython(rename_forwards, rename_backwards),
    ]
