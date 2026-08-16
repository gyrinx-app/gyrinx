# Deliberately inert. The Paths conversion ran here once, but a
# conversion runs live code, and live code keeps moving: every new
# column the conversion's queries touch would need adding to this
# migration's dependencies, while any database that already applied the
# two in the other order — as production did — would refuse the same
# dependency as inconsistent history. No dependency list can be true on
# every database at once, so conversions do not ship as migrations.
#
# The conversion itself lives on:
#
#     manage n26_convert paths --apply
#
# A database still holding the old system converts then, with the plan
# previewed first and every affected gang's pages proven unchanged; one
# already converted answers that there is nothing here.

from django.db import migrations


class Migration(migrations.Migration):
    # The loosest dependencies this migration ever declared, so that no
    # database's recorded history — whichever order it applied things in
    # — reads as inconsistent.
    dependencies = [
        ("library", "0061_reach_is_said_not_implied"),
        ("n26", "0012_a_pick_names_the_slot_it_settles"),
    ]

    operations = []
