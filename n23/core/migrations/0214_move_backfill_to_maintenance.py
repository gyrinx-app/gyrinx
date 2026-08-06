from django.db import migrations

# Moving a model between apps means carrying its ContentType row over *in
# place*, so its id — and therefore every permission grant and generic
# reference pointing at it — survives. Renaming is only half the job, though:
# unapplying this migration leaves `maintenance.Backfill` in the migration
# state, so post_migrate's create_contenttypes mints a fresh, unreferenced
# `maintenance | backfill` row. A plain rename would then collide with it on
# the (app_label, model) unique constraint when rolling forward again — which
# is exactly what a rollback-and-retry deploy does. So each direction clears
# any stray duplicate before renaming, and no-ops if the move already happened.


def _move(apps, from_label, to_label):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")

    original = ContentType.objects.filter(
        app_label=from_label, model="backfill"
    ).first()
    if original is None:
        return  # already moved — nothing to carry over

    stray = ContentType.objects.filter(app_label=to_label, model="backfill").exclude(
        pk=original.pk
    )
    # Auto-created and referenced by nothing (the real grants hang off
    # `original`), so its permissions go with it.
    Permission.objects.filter(content_type__in=stray).delete()
    stray.delete()

    ContentType.objects.filter(pk=original.pk).update(app_label=to_label)


def content_type_to_maintenance(apps, schema_editor):
    _move(apps, "core", "maintenance")


def content_type_to_core(apps, schema_editor):
    _move(apps, "maintenance", "core")


class Migration(migrations.Migration):
    """Release Backfill from `core` — state only, table and indexes untouched."""

    dependencies = [
        ("core", "0213_document_pre_mod_advancement_flag"),
        ("maintenance", "0001_move_backfill_to_maintenance"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(
                    name="Backfill",
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(content_type_to_maintenance, content_type_to_core),
    ]
