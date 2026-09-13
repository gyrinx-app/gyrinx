"""Exercise n26 migration 0069's counter checkpoint at production volume.

Run only against a disposable database selected through ``DB_NAME``. The script
migrates that database back to both 0068 leaves, creates synthetic historical
rows through the migration state ORM, applies 0069, and independently compares
every counter value and checkpoint.
"""

import json
import os
import time

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gyrinx.settings_dev")
django.setup()

from django.db import connection  # noqa: E402, I001
from django.db.migrations.executor import MigrationExecutor  # noqa: E402


OLD_TARGETS = [
    ("n26", "0068_action_becomes_activity"),
    ("n26", "0068_remove_assignment_assignment_exactly_one_assignable_and_more"),
]
NEW_TARGET = [("n26", "0069_fighter_action_records_and_counter_events")]
VOLUME = 19_940
ZERO = 863
ARCHIVED = 2_672
REMOVED = 2_643


def rows_by_id(model, ids, fields):
    return {
        str(row[0]): tuple(row[1:])
        for row in model.objects.filter(pk__in=ids).values_list("pk", *fields)
    }


database = connection.settings_dict["NAME"]
if "counter_migration_evidence" not in database:
    raise RuntimeError(f"Refusing non-scratch database {database!r}")

executor = MigrationExecutor(connection)
executor.migrate(OLD_TARGETS)
old_apps = executor.loader.project_state(OLD_TARGETS).apps

Gang = old_apps.get_model("n26", "Gang")
Assignment = old_apps.get_model("n26", "Assignment")
CounterValue = old_apps.get_model("n26", "CounterValue")
LedgerEvent = old_apps.get_model("n26", "LedgerEvent")
GangType = old_apps.get_model("library", "GangType")
Counter = old_apps.get_model("library", "Counter")

gang_type = GangType.objects.first()
counter = Counter.objects.first()
if gang_type is None or counter is None:
    raise RuntimeError("Scratch clone must contain the standard content mirror")
gang = Gang.objects.create(name="Counter migration evidence", gang_type=gang_type)

assignments = Assignment.objects.bulk_create(
    [
        Assignment(
            gang=gang,
            gang_root=gang,
            counter=counter,
            archived=position < ARCHIVED,
        )
        for position in range(VOLUME)
    ],
    batch_size=500,
)
counter_values = CounterValue.objects.bulk_create(
    [
        CounterValue(
            assignment=assignment,
            value=0 if position < ZERO else (position % 37) + 1,
        )
        for position, assignment in enumerate(assignments)
    ],
    batch_size=500,
)
LedgerEvent.objects.bulk_create(
    [
        LedgerEvent(
            gang=gang,
            assignment=assignment,
            kind="removed",
            note="Synthetic pre-migration removal",
        )
        for assignment in assignments[:REMOVED]
    ],
    batch_size=500,
)

assignment_ids = [row.pk for row in assignments]
value_ids = [row.pk for row in counter_values]
before_values = rows_by_id(CounterValue, value_ids, ("assignment_id", "value"))
before_assignments = rows_by_id(
    Assignment, assignment_ids, ("gang_root_id", "archived")
)
before_removed = set(
    str(value)
    for value in LedgerEvent.objects.filter(
        assignment_id__in=assignment_ids, kind="removed"
    ).values_list("assignment_id", flat=True)
)

started = time.perf_counter()
executor = MigrationExecutor(connection)
executor.migrate(NEW_TARGET)
elapsed = time.perf_counter() - started
new_apps = executor.loader.project_state(NEW_TARGET).apps
NewCounterValue = new_apps.get_model("n26", "CounterValue")
NewAssignment = new_apps.get_model("n26", "Assignment")
NewLedgerEvent = new_apps.get_model("n26", "LedgerEvent")

after_values = rows_by_id(NewCounterValue, value_ids, ("assignment_id", "value"))
after_assignments = rows_by_id(
    NewAssignment, assignment_ids, ("gang_root_id", "archived")
)
checkpoints = {
    str(row[0]): tuple(row[1:])
    for row in NewLedgerEvent.objects.filter(
        assignment_id__in=assignment_ids, kind="counter_checkpointed"
    ).values_list(
        "assignment_id",
        "gang_id",
        "counter_before",
        "counter_delta",
        "counter_after",
    )
}
after_removed = set(
    str(value)
    for value in NewLedgerEvent.objects.filter(
        assignment_id__in=assignment_ids, kind="removed"
    ).values_list("assignment_id", flat=True)
)

assert before_values == after_values
assert before_assignments == after_assignments
assert before_removed == after_removed
assert len(checkpoints) == VOLUME
for _value_id, (assignment_id, value) in before_values.items():
    gang_id, _archived = before_assignments[str(assignment_id)]
    assert checkpoints[str(assignment_id)] == (gang_id, value, 0, value)

reverse_started = time.perf_counter()
executor = MigrationExecutor(connection)
executor.migrate(OLD_TARGETS)
reverse_elapsed = time.perf_counter() - reverse_started
reversed_apps = executor.loader.project_state(OLD_TARGETS).apps
ReversedCounterValue = reversed_apps.get_model("n26", "CounterValue")
ReversedAssignment = reversed_apps.get_model("n26", "Assignment")
ReversedLedgerEvent = reversed_apps.get_model("n26", "LedgerEvent")
assert (
    rows_by_id(ReversedCounterValue, value_ids, ("assignment_id", "value"))
    == before_values
)
assert (
    rows_by_id(ReversedAssignment, assignment_ids, ("gang_root_id", "archived"))
    == before_assignments
)
assert (
    set(
        str(value)
        for value in ReversedLedgerEvent.objects.filter(
            assignment_id__in=assignment_ids, kind="removed"
        ).values_list("assignment_id", flat=True)
    )
    == before_removed
)
assert not ReversedLedgerEvent.objects.filter(
    assignment_id__in=assignment_ids, kind="counter_checkpointed"
).exists()

print(
    json.dumps(
        {
            "database": database,
            "elapsed_seconds": round(elapsed, 3),
            "reverse_elapsed_seconds": round(reverse_elapsed, 3),
            "counter_values": len(after_values),
            "zero_values": sum(
                value == 0 for _assignment, value in after_values.values()
            ),
            "nonzero_values": sum(
                value > 0 for _assignment, value in after_values.values()
            ),
            "archived_assignments": sum(
                archived for _gang, archived in after_assignments.values()
            ),
            "active_assignments": sum(
                not archived for _gang, archived in after_assignments.values()
            ),
            "removed_assignments": len(after_removed),
            "checkpoint_events": len(checkpoints),
            "preserved_counter_value_rows": before_values == after_values,
            "preserved_assignment_rows": before_assignments == after_assignments,
            "preserved_removed_events": before_removed == after_removed,
            "checkpoint_before_after_delta_and_gang_exact": True,
            "reverse_removed_only_checkpoints": True,
        },
        indent=2,
        sort_keys=True,
    )
)
