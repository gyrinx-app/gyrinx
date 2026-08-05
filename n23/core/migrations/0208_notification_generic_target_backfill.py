"""Index the generic relations added in 0207, then backfill them from the old FKs.

Separate from 0207 on purpose — see that migration's docstring for why the
CREATE INDEXes cannot share a transaction with the ADD COLUMNs.
"""

from django.db import migrations, models


def backfill_generic_relations(apps, schema_editor):
    """Copy related_list / related_campaign into the generic columns.

    A gang is the subject when there is one, with its campaign as the surrounding
    scope; a campaign-only notification is its own subject. Mirrors notify().
    """
    Notification = apps.get_model("core", "Notification")
    ContentType = apps.get_model("contenttypes", "ContentType")

    list_ct = ContentType.objects.filter(app_label="core", model="list").first()
    campaign_ct = ContentType.objects.filter(app_label="core", model="campaign").first()

    if list_ct is not None:
        # Gang notifications: the gang is the target, its campaign the scope.
        Notification.objects.filter(related_list__isnull=False).update(
            target_content_type=list_ct,
            target_object_id=models.F("related_list_id"),
            scope_content_type=campaign_ct,
            scope_object_id=models.F("related_campaign_id"),
        )
        # A gang notification with no campaign has no scope; the update above
        # would otherwise leave a content type with no object id.
        Notification.objects.filter(
            related_list__isnull=False, related_campaign__isnull=True
        ).update(scope_content_type=None, scope_object_id=None)

    if campaign_ct is not None:
        # Campaign-only notifications: the campaign is its own target.
        Notification.objects.filter(
            related_campaign__isnull=False, related_list__isnull=True
        ).update(
            target_content_type=campaign_ct,
            target_object_id=models.F("related_campaign_id"),
        )


def unbackfill(apps, schema_editor):
    """Clear the generic columns. The FK columns were never touched."""
    Notification = apps.get_model("core", "Notification")
    Notification.objects.exclude(
        target_content_type__isnull=True, scope_content_type__isnull=True
    ).update(
        target_content_type=None,
        target_object_id=None,
        scope_content_type=None,
        scope_object_id=None,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0207_notification_generic_target"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(
                fields=["target_content_type", "target_object_id", "show_as_banner"],
                name="notif_banner_target_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(
                fields=["scope_content_type", "scope_object_id", "show_as_banner"],
                name="notif_banner_scope_idx",
            ),
        ),
        migrations.RunPython(backfill_generic_relations, unbackfill),
    ]
