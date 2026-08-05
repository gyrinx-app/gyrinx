"""Give Notification generic `target` / `scope` relations in place of its two
fixed FKs to List and Campaign.

The FK columns stay for now: dropping them in the same deploy that adds these
would break any instance still serving the previous revision. They go in the
follow-up that moves the model to the platform (#2093).

The indexes and the backfill are in 0210, not here. Adding a column with a
foreign key to a table that already has rows leaves pending trigger events for
the constraint check, and Postgres refuses CREATE INDEX on the same table in the
same transaction ("cannot CREATE INDEX ... because it has pending trigger
events"). Splitting them puts the ADD COLUMNs in their own transaction. Nothing
in the test suite catches this — it runs --nomigrations — and it does not
reproduce on an empty table.

Production shape at the time of writing: 3,832 notifications, of which 42 have
either FK set (all 42 have both), and none has show_as_banner=True.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("core", "0208_retire_statline_maintenance_operations"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="notification",
            name="notif_banner_list_idx",
        ),
        migrations.RemoveIndex(
            model_name="notification",
            name="notif_banner_camp_idx",
        ),
        migrations.AddField(
            model_name="notification",
            name="scope_content_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="notification_scopes",
                to="contenttypes.contenttype",
            ),
        ),
        migrations.AddField(
            model_name="notification",
            name="scope_object_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="notification",
            name="target_content_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="notification_targets",
                to="contenttypes.contenttype",
            ),
        ),
        migrations.AddField(
            model_name="notification",
            name="target_object_id",
            field=models.UUIDField(blank=True, null=True),
        ),
    ]
