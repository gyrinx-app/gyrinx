"""Every open Visit Trading Post action becomes a row of its own.

A gang at the post was a figure on the gang plus the event its spending
was measured from. It is an action row now, so the purchases that
counted against it can point at it by name rather than be found by the
time they happened.

One row per gang still at a post, pointing at the boundary event that
visit already wrote — so the receipt still names who performed it, from
the batch that event carries — and then the purchases the figure was
being read from are stamped with it.
"""

from django.db import migrations

#: The kind of action a trip to the trading post opens, and the event
#: kind that opened one before there were actions. Written out because a
#: migration reads the columns as they were, not the choices as they are.
VISIT = "trading_post_visit"
TRADE_POINTS_SET = "trade_points_set"


def open_the_visits(apps, schema_editor):
    Gang = apps.get_model("n26", "Gang")
    Action = apps.get_model("n26", "Action")
    LedgerEntry = apps.get_model("n26", "LedgerEntry")
    LedgerEvent = apps.get_model("n26", "LedgerEvent")

    for gang in Gang.objects.filter(starting_trade_points__isnull=False).iterator():
        if Action.objects.filter(gang=gang, kind=VISIT, closed__isnull=True).exists():
            continue
        opened = (
            LedgerEvent.objects.filter(gang=gang, kind=TRADE_POINTS_SET)
            .order_by("-created")
            .first()
        )
        if opened is None:
            # A figure with no act behind it. There is no event for the
            # row to point at and nothing to measure the purchases from,
            # so the gang is left as it is rather than given a visit
            # nobody performed.
            continue
        action = Action.objects.create(
            gang=gang,
            kind=VISIT,
            opened=opened,
            trade_points=gang.starting_trade_points,
        )
        # What the figure was being read from: purchases made since the
        # boundary that moved Trade Points. Windowed on the assignment,
        # as the reading itself is, so a purchase and everything that
        # later happened to it stay on the same side of the line.
        counted = list(
            LedgerEntry.objects.filter(
                assignment__gang_root=gang,
                assignment__created__gte=opened.created,
                assignment__ledger_events__trade_points_delta__gt=0,
            )
            .values_list("pk", flat=True)
            .distinct()
        )
        if counted:
            LedgerEntry.objects.filter(pk__in=counted).update(action=action)


class Migration(migrations.Migration):
    dependencies = [
        ("n26", "0043_a_purchase_records_the_action_it_counted_against"),
    ]

    operations = [
        # Nothing to undo: going back drops the column these rows were
        # written into, and the figure on the gang is still there.
        migrations.RunPython(open_the_visits, migrations.RunPython.noop),
    ]
