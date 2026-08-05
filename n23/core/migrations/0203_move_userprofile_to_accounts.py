from django.db import migrations


def content_types_to_accounts(apps, schema_editor):
    """Repoint the existing ContentType rows at the new app label.

    Updating in place rather than letting post_migrate create fresh rows keeps
    the same content_type_id, so the four auth_permission rows follow
    automatically and any GenericForeignKey pointing at a profile stays valid.
    (Checked against production: zero Event rows currently point at one.)
    """
    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.filter(
        app_label="core", model__in=["userprofile", "historicaluserprofile"]
    ).update(app_label="accounts")


def content_types_to_core(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.filter(
        app_label="accounts", model__in=["userprofile", "historicaluserprofile"]
    ).update(app_label="core")


class Migration(migrations.Migration):
    """Release UserProfile from `core` — state only, no table is dropped.

    The tables live on under their original names, now owned by
    gyrinx.accounts (see accounts.0001).
    """

    dependencies = [
        ("core", "0202_migrate_stat_overrides_operation"),
        ("accounts", "0001_move_userprofile_to_accounts"),
        ("contenttypes", "0002_remove_content_type_name"),
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
