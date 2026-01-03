# Generated manually to remove orphaned M2M tables from ContentPack

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0151_remove_contentpack"),
    ]

    operations = [
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS content_contentpack_equipment;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS content_contentpack_fighters;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS content_contentpack_houses;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS content_contentpack_rules;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS content_contentpack_skill_categories;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS content_contentpack_weapon_accessories;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS content_contentpack_weapon_profiles;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS content_contentpack_weapon_traits;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
