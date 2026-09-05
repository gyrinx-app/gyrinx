"""The words on a campaign's gang budget.

Help text only; the column does not change shape and no row is touched.
The text now says what the number does — a gang worth more still joins and
is marked as over budget — rather than restating the field's name.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("n26", "0046_a_ledger_event_may_open_a_clone"),
    ]

    operations = [
        migrations.AlterField(
            model_name="campaign",
            name="budget",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="What a gang should be worth to join, counting its rating, stash and unspent credits. A gang worth more than this can still join, and is marked as over budget on the campaign page. Blank means the campaign has no budget.",
                null=True,
            ),
        ),
    ]
