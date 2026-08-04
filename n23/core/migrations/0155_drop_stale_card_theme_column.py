from django.db import migrations


class Migration(migrations.Migration):
    """Drop the stray ``card_theme`` column left behind on databases that
    applied an earlier iteration of 0154.

    0154 originally added a ``card_theme`` field alongside ``card_style``. That
    field was dropped from the model (classic cards always use the blank plate)
    and the AddField ops were removed from 0154 before merge. Databases that had
    already applied the earlier 0154 keep a ``NOT NULL`` ``card_theme`` column
    with no default, which breaks every PrintConfig insert. Drop it where it
    exists; this is a no-op on fresh databases that never had the column.

    The migration state is deliberately untouched — the model already has no
    ``card_theme`` — so this only reconciles the physical schema.
    """

    dependencies = [
        ("core", "0154_print_config_card_style_theme"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                'ALTER TABLE "core_printconfig" DROP COLUMN IF EXISTS "card_theme";',
                'ALTER TABLE "core_historicalprintconfig" DROP COLUMN IF EXISTS "card_theme";',
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
