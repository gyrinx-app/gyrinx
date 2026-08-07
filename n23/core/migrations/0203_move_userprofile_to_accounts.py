from django.db import migrations

_MOVED = ["userprofile", "historicaluserprofile"]


def _move_content_types(apps, from_label, to_label, models):
    """Carry ContentType rows between app labels, in place and idempotently.

    In place so the id survives: every permission grant and generic reference
    points at that id, and minting a new row would orphan them.

    The stray-clearing step is what makes a rollback survivable. Unapplying this
    migration leaves the model in the migration state, so post_migrate mints a
    fresh row under the label we are moving *to*; without clearing it first, the
    update below collides on the (app_label, model) unique constraint the next
    time this runs. Its permissions are auto-created and referenced by nothing —
    the real grants hang off the original row — so they go with it.
    """
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")

    for model in models:
        original = ContentType.objects.filter(app_label=from_label, model=model).first()
        if original is None:
            continue  # already moved, or never existed — nothing to carry

        stray = ContentType.objects.filter(app_label=to_label, model=model).exclude(
            pk=original.pk
        )
        Permission.objects.filter(content_type__in=stray).delete()
        stray.delete()

        ContentType.objects.filter(pk=original.pk).update(app_label=to_label)


def content_types_to_accounts(apps, schema_editor):
    """Repoint the existing ContentType rows at the new app label.

    Updating in place rather than letting post_migrate create fresh rows keeps
    the same content_type_id, so the four auth_permission rows follow
    automatically and any GenericForeignKey pointing at a profile stays valid.
    (Checked against production: zero Event rows currently point at one.)
    """
    _move_content_types(apps, "core", "accounts", _MOVED)


def content_types_to_core(apps, schema_editor):
    _move_content_types(apps, "accounts", "core", _MOVED)


class Migration(migrations.Migration):
    """Release UserProfile from `core` — state only, no table is dropped.

    The tables live on under their original names, now owned by
    gyrinx.accounts (see accounts.0001).
    """

    dependencies = [
        ("core", "0202_migrate_stat_overrides_operation"),
        ("accounts", "0001_move_userprofile_to_accounts"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name="userprofile", name="user"),
                migrations.DeleteModel(name="HistoricalUserProfile"),
                migrations.DeleteModel(name="UserProfile"),
            ],
            database_operations=[],
        ),
        migrations.RunPython(content_types_to_accounts, content_types_to_core),
    ]
