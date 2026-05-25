"""Merge duplicate ContentRule records by name (issue #1530).

Picks the canonical record per name as: highest total reference count first,
oldest `created` as the tiebreaker. Repoints every reference (ContentFighter
default rules, ListFighter custom/disabled rules, ContentModFighterRule, and
CustomContentPackItem GenericForeignKey rows) at the canonical record, then
deletes the duplicates. A follow-up migration adds a unique constraint on
ContentRule.name.

Irreversible (rule rows that are deleted cannot be reconstructed). The
reverse_code is a no-op so `migrate content zero` doesn't fail, but it does
not restore the merged records.
"""

from django.db import migrations
from django.db.models import Count


def dedupe_content_rules(apps, schema_editor):
    ContentRule = apps.get_model("content", "ContentRule")
    ContentFighter = apps.get_model("content", "ContentFighter")
    ContentModFighterRule = apps.get_model("content", "ContentModFighterRule")
    ListFighter = apps.get_model("core", "ListFighter")
    CustomContentPackItem = apps.get_model("core", "CustomContentPackItem")
    ContentType = apps.get_model("contenttypes", "ContentType")

    rule_ct = ContentType.objects.get(app_label="content", model="contentrule")

    dupe_groups = list(
        ContentRule.objects.values("name")
        .annotate(c=Count("id"))
        .filter(c__gt=1)
        .order_by("name")
    )

    if not dupe_groups:
        print("No duplicate ContentRule names found.")
        return

    def ref_count(rule):
        return (
            ContentFighter.objects.filter(rules=rule).count()
            + ListFighter.objects.filter(custom_rules=rule).count()
            + ListFighter.objects.filter(disabled_rules=rule).count()
            + ContentModFighterRule.objects.filter(rule=rule).count()
            + CustomContentPackItem.objects.filter(
                content_type=rule_ct, object_id=rule.id
            ).count()
        )

    groups_merged = 0
    records_deleted = 0

    for group in dupe_groups:
        name = group["name"]
        rules = list(ContentRule.objects.filter(name=name))

        scored = sorted(rules, key=lambda r: (-ref_count(r), r.created))
        canonical = scored[0]
        duplicates = scored[1:]

        print(
            f"Rule {name!r}: keeping {canonical.id} "
            f"(refs={ref_count(canonical)}), merging {len(duplicates)} duplicate(s)"
        )

        for dup in duplicates:
            for cf in ContentFighter.objects.filter(rules=dup):
                cf.rules.add(canonical)
                cf.rules.remove(dup)

            for lf in ListFighter.objects.filter(custom_rules=dup):
                lf.custom_rules.add(canonical)
                lf.custom_rules.remove(dup)

            for lf in ListFighter.objects.filter(disabled_rules=dup):
                lf.disabled_rules.add(canonical)
                lf.disabled_rules.remove(dup)

            ContentModFighterRule.objects.filter(rule=dup).update(rule=canonical)

            # CustomContentPackItem uses a GenericForeignKey and has a
            # conditional unique constraint on (pack, content_type, object_id)
            # where archived=False. If the canonical is already in the same
            # pack, we'd collide on update — delete the duplicate's pack item
            # in that case.
            dup_pack_items = CustomContentPackItem.objects.filter(
                content_type=rule_ct, object_id=dup.id
            )
            for item in dup_pack_items:
                conflict = CustomContentPackItem.objects.filter(
                    pack=item.pack,
                    content_type=rule_ct,
                    object_id=canonical.id,
                    archived=False,
                ).exists()
                if conflict and not item.archived:
                    item.delete()
                else:
                    item.object_id = canonical.id
                    item.save()

            # If canonical has no description but a duplicate did, preserve
            # the text. (Audit showed every duplicate has empty description
            # in production, but this is cheap insurance.)
            if not canonical.description and dup.description:
                canonical.description = dup.description
                canonical.save()

            dup.delete()
            records_deleted += 1

        groups_merged += 1

    print(
        f"Merged {groups_merged} duplicate group(s); deleted {records_deleted} record(s)."
    )


def reverse_noop(apps, schema_editor):  # noqa: ARG001
    """No-op reverse — deleted rule rows cannot be reconstructed."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0167_add_icon_to_house"),
        ("core", "0144_list_campaign_pin_star"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(dedupe_content_rules, reverse_noop),
    ]
