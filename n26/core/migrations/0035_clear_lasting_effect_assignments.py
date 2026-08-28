from django.db import migrations


class Migration(migrations.Migration):
    """Clear assignments naming a lasting effect, before the schema goes.

    The check constraint that follows names every assignable kind except
    this one, and Postgres validates a new check against the rows already
    in the table — so such a row would abort the migration. Dropping the
    column instead would not save it either: it would then name no
    assignable at all, which the same check forbids. There is nothing to
    keep, so clear them.

    This stands alone because the delete leaves trigger events pending
    until its transaction commits, and Postgres refuses to alter a table
    that has them.
    """

    dependencies = [
        ("n26", "0034_a_gang_plays_one_campaign_at_a_time"),
    ]

    operations = [
        migrations.RunSQL(
            sql="DELETE FROM n26_assignment WHERE lasting_effect_id IS NOT NULL;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
