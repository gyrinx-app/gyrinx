"""Delete the stray `core | notification` ContentType row left in production.

`Notification` moved from `core` to `gyrinxsite` in 0212. Production ended up
with *both* rows: 224 (gyrinxsite, the real one, id preserved along with its
permissions) and 248 (core, a duplicate minted by post_migrate's
create_contenttypes while the migration state still said `core`). 0212 has since
been taught to clear strays in both directions, but that only protects future
runs — the row already exists and no migration will remove it on its own.

Checked against production before writing this, across every column in the
schema that references django_content_type:

    auth_permission                                             4
    django_admin_log                                            0
    content_contentequipmentlistexpansionrule.polymorphic_ctype 0
    content_contentmod.polymorphic_ctype                        0
    content_contentmodapplication.target_content_type           0
    core_customcontentpackitem.content_type                     0
    core_event.object_type                                      0
    core_notification.scope_content_type                        0
    core_notification.target_content_type                       0

The four permissions are the auto-created add/change/delete/view set, and no
user and no group holds any of them — the grants people actually have hang off
224. So nothing references this row and deleting it changes no behaviour; it
only stops the admin's permission picker listing "notification" twice.

Written as a migration rather than a Backfill because it repairs migration
bookkeeping, is a single idempotent delete, and needs no preview or progress
reporting. Matched on (app_label, model), never on the id.
"""

from django.db import migrations

STRAY = {"app_label": "core", "model": "notification"}
REAL = {"app_label": "gyrinxsite", "model": "notification"}


def remove_stray(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")

    # Only ever delete the duplicate, and only while the real row exists — so a
    # database where the move never happened, or was rolled back, is left alone.
    if not ContentType.objects.filter(**REAL).exists():
        return
    stray = ContentType.objects.filter(**STRAY)
    Permission.objects.filter(content_type__in=stray).delete()
    stray.delete()


def noop(apps, schema_editor):
    """Deliberately not reversed.

    Re-creating the duplicate would only restore the collision 0212 now guards
    against, and post_migrate mints one by itself if the state ever calls for it.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0214_move_backfill_to_maintenance"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0001_initial"),
    ]

    operations = [migrations.RunPython(remove_stray, noop)]
