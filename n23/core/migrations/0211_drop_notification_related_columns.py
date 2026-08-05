from django.db import migrations


class Migration(migrations.Migration):
    """Drop the superseded related_list / related_campaign FK columns.

    0209/0210 added the generic `target` / `scope` relations, backfilled them and
    moved every read onto them, but kept writing these two columns so instances
    still serving the previous revision kept working through that rollout. That
    revision is now live everywhere, so the columns can go — which is also what
    frees the model to move to the platform, since a platform model cannot hold a
    ForeignKey to an edition table.
    """

    dependencies = [
        ("core", "0210_notification_generic_target_backfill"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="notification",
            name="related_list",
        ),
        migrations.RemoveField(
            model_name="notification",
            name="related_campaign",
        ),
    ]
