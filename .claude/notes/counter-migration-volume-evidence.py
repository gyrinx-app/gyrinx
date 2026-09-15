"""Rehearse final n26 records migrations against production-sized synthetic data."""

import hashlib
import json
import os
import time
from uuid import NAMESPACE_URL, uuid4, uuid5

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gyrinx.settings_dev")
django.setup()

from django.db import connection  # noqa: E402, I001
from django.db.migrations.executor import MigrationExecutor  # noqa: E402

PREFIX = "wren_counter_migration_evidence_"
OLD = [("n26", "0068_remove_assignment_assignment_exactly_one_assignable_and_more")]
FINAL = [("n26", "0071_alter_ledgerevent_options_and_more")]
COUNTERS, ZERO, ARCHIVED = 19_940, 863, 2_672
EVENTS, REMOVED, GANGS = 228_571, 2_643, 20
MIGRATION_BATCH = uuid5(NAMESPACE_URL, "https://gyrinx.app/migrations/n26/0069")


def state(targets):
    executor = MigrationExecutor(connection)
    return executor, executor.loader.project_state(targets).apps


def rows(model, ids, *fields):
    return {
        str(row[0]): tuple(row[1:])
        for row in model.objects.filter(pk__in=ids).values_list("pk", *fields)
    }


def digest(queryset, fields=None):
    fields = fields or [field.attname for field in queryset.model._meta.concrete_fields]
    value = hashlib.sha256()
    count = 0
    for row in queryset.order_by("pk").values_list(*fields).iterator(chunk_size=2000):
        value.update(json.dumps(row, default=str, separators=(",", ":")).encode())
        value.update(b"\n")
        count += 1
    return count, value.hexdigest()


def applied(name):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS(SELECT 1 FROM django_migrations "
            "WHERE app='n26' AND name=%s)",
            [name],
        )
        return cursor.fetchone()[0]


database = connection.settings_dict["NAME"]
if not database.startswith(PREFIX):
    raise RuntimeError(f"Refusing non-scratch database {database!r}")
if connection.introspection.table_names():
    raise RuntimeError(f"Refusing non-empty scratch database {database!r}")

whole_started = time.perf_counter()
MigrationExecutor(connection).migrate(OLD)
_, apps = state(OLD)
Gang = apps.get_model("n26", "Gang")
Assignment = apps.get_model("n26", "Assignment")
CounterValue = apps.get_model("n26", "CounterValue")
LedgerEvent = apps.get_model("n26", "LedgerEvent")
GangType = apps.get_model("library", "GangType")
Counter = apps.get_model("library", "Counter")

gang_type = GangType.objects.create(name="Synthetic evidence type")
counter = Counter.objects.create(name="Synthetic evidence counter")
gangs = [
    Gang.objects.create(name=f"Synthetic evidence gang {number}", gang_type=gang_type)
    for number in range(GANGS)
]
assignments = Assignment.objects.bulk_create(
    [
        Assignment(
            gang=gangs[n % GANGS],
            gang_root=gangs[n % GANGS],
            counter=counter,
            archived=n < ARCHIVED,
        )
        for n in range(COUNTERS)
    ],
    batch_size=500,
)
values = CounterValue.objects.bulk_create(
    [
        CounterValue(
            assignment=assignment,
            value=0 if n < ZERO else (n % 37) + 1,
        )
        for n, assignment in enumerate(assignments)
    ],
    batch_size=500,
)
pending = []
for n in range(EVENTS):
    if n < REMOVED:
        pending.append(
            LedgerEvent(
                gang=gangs[n % GANGS],
                assignment=assignments[n],
                kind="removed",
                note=f"Synthetic removal {n}",
            )
        )
    else:
        pending.append(
            LedgerEvent(
                gang=gangs[n % GANGS],
                kind="noted",
                note=f"Synthetic journal {n}",
            )
        )
    if len(pending) == 2000:
        LedgerEvent.objects.bulk_create(pending, batch_size=500)
        pending.clear()
if pending:
    LedgerEvent.objects.bulk_create(pending, batch_size=500)

assignment_ids = [row.pk for row in assignments]
value_ids = [row.pk for row in values]
event_ids = list(LedgerEvent.objects.values_list("pk", flat=True))
before_values = rows(CounterValue, value_ids, "assignment_id", "value")
before_assignments = rows(Assignment, assignment_ids, "gang_root_id", "archived")
event_fields = [field.attname for field in LedgerEvent._meta.concrete_fields]
before_events = digest(LedgerEvent.objects.all(), event_fields)
before_removed = rows(
    LedgerEvent,
    LedgerEvent.objects.filter(kind="removed").values_list("pk", flat=True),
    "gang_id",
    "assignment_id",
    "kind",
    "note",
)
assert before_events[0] == EVENTS and len(before_removed) == REMOVED

# Let the real 0069 data function finish, then fail inside the same atomic
# migration. The old state, including all 228,571 events, must be exact.
failed_executor = MigrationExecutor(connection)
migration = failed_executor.loader.get_migration(
    "n26", "0069_fighter_action_records_and_counter_events"
)
run_python = next(
    operation
    for operation in migration.operations
    if getattr(operation, "code", None)
    and operation.code.__name__ == "checkpoint_counter_values"
)
real_code = run_python.code


def fail_after_checkpoints(historical_apps, schema_editor):
    real_code(historical_apps, schema_editor)
    raise RuntimeError("intentional failure after checkpoints")


run_python.code = fail_after_checkpoints
failure_started = time.perf_counter()
try:
    failed_executor.migrate(FINAL)
except RuntimeError as error:
    assert str(error) == "intentional failure after checkpoints"
else:
    raise AssertionError("forced forward failure unexpectedly succeeded")
finally:
    run_python.code = real_code
failure_seconds = time.perf_counter() - failure_started

assert not applied("0069_fighter_action_records_and_counter_events")
_, failed_apps = state(OLD)
FailedValue = failed_apps.get_model("n26", "CounterValue")
FailedAssignment = failed_apps.get_model("n26", "Assignment")
FailedEvent = failed_apps.get_model("n26", "LedgerEvent")
assert rows(FailedValue, value_ids, "assignment_id", "value") == before_values
assert (
    rows(FailedAssignment, assignment_ids, "gang_root_id", "archived")
    == before_assignments
)
assert digest(FailedEvent.objects.all(), event_fields) == before_events

forward_started = time.perf_counter()
MigrationExecutor(connection).migrate(FINAL)
forward_seconds = time.perf_counter() - forward_started
_, final_apps = state(FINAL)
NewValue = final_apps.get_model("n26", "CounterValue")
NewAssignment = final_apps.get_model("n26", "Assignment")
NewEvent = final_apps.get_model("n26", "LedgerEvent")
assert rows(NewValue, value_ids, "assignment_id", "value") == before_values
assert (
    rows(NewAssignment, assignment_ids, "gang_root_id", "archived")
    == before_assignments
)
assert digest(NewEvent.objects.filter(pk__in=event_ids), event_fields) == before_events
assert (
    rows(NewEvent, before_removed, "gang_id", "assignment_id", "kind", "note")
    == before_removed
)

checkpoints = {
    str(row[0]): tuple(row[1:])
    for row in NewEvent.objects.filter(
        kind="counter_checkpointed", batch=MIGRATION_BATCH
    ).values_list(
        "assignment_id",
        "gang_id",
        "counter_before",
        "counter_delta",
        "counter_after",
    )
}
assert (
    NewEvent.objects.filter(kind="counter_checkpointed", batch=MIGRATION_BATCH).count()
    == COUNTERS
)
assert len(checkpoints) == COUNTERS
for _pk, (assignment_id, value) in before_values.items():
    gang_id, _archived = before_assignments[str(assignment_id)]
    assert checkpoints[str(assignment_id)] == (gang_id, value, 0, value)

# A later checkpoint owned by another batch must survive 0069's reverse.
unrelated = NewEvent.objects.create(
    gang_id=assignments[0].gang_root_id,
    assignment_id=assignments[0].pk,
    kind="counter_checkpointed",
    batch=uuid4(),
    counter_before=values[0].value,
    counter_delta=0,
    counter_after=values[0].value,
    note="Unrelated later checkpoint",
)

# Reproduce both old-worker gaps after the checkpoint. These are expected
# findings: old code changed the pin and wrote the fixed note, but left the
# new structured columns NULL.
legacy_existing = NewValue.objects.get(pk=values[ZERO].pk)
legacy_existing.value += 4
legacy_existing.save(update_fields=["value", "modified"])
NewEvent.objects.create(
    gang_id=assignments[ZERO].gang_root_id,
    assignment_id=assignments[ZERO].pk,
    kind="tallied",
    note=f"+4 → {legacy_existing.value}: old worker",
)
legacy_assignment = NewAssignment.objects.create(
    gang_id=gangs[0].pk, gang_root_id=gangs[0].pk, counter_id=counter.pk
)
legacy_value = NewValue.objects.create(assignment=legacy_assignment, value=6)
NewEvent.objects.create(
    gang_id=gangs[0].pk,
    assignment=legacy_assignment,
    kind="tallied",
    note="+6 → 6: old worker created counter",
)
from n26.core.models import CounterValue as LiveCounterValue  # noqa: E402
from n26.core.reconcile import check_counter_value  # noqa: E402

existing_gap = check_counter_value(LiveCounterValue.objects.get(pk=legacy_existing.pk))
new_gap = check_counter_value(LiveCounterValue.objects.get(pk=legacy_value.pk))
assert any("events end" in problem for problem in existing_gap)
assert any("no counter opening" in problem for problem in new_gap)

# Exact persisted shape of a post-migration open followed by a tally.
modern_assignment = NewAssignment.objects.create(
    gang_id=gangs[1].pk, gang_root_id=gangs[1].pk, counter_id=counter.pk
)
modern_value = NewValue.objects.create(assignment=modern_assignment, value=4)
NewEvent.objects.create(
    gang_id=gangs[1].pk,
    assignment=modern_assignment,
    kind="counter_opened",
    counter_before=0,
    counter_delta=4,
    counter_after=4,
)
modern_value.value = 7
modern_value.save(update_fields=["value", "modified"])
NewEvent.objects.create(
    gang_id=gangs[1].pk,
    assignment=modern_assignment,
    kind="tallied",
    counter_before=4,
    counter_delta=3,
    counter_after=7,
    note="+3 → 7",
)

pre_reverse_value_ids = list(NewValue.objects.values_list("pk", flat=True))
pre_reverse_assignment_ids = list(NewAssignment.objects.values_list("pk", flat=True))
pre_reverse_values = rows(NewValue, pre_reverse_value_ids, "assignment_id", "value")
pre_reverse_assignments = rows(
    NewAssignment,
    pre_reverse_assignment_ids,
    "gang_root_id",
    "archived",
)
assert len(pre_reverse_values) == COUNTERS + 2
assert len(pre_reverse_assignments) == COUNTERS + 2

reverse_started = time.perf_counter()
MigrationExecutor(connection).migrate(OLD)
reverse_seconds = time.perf_counter() - reverse_started
_, reversed_apps = state(OLD)
ReversedValue = reversed_apps.get_model("n26", "CounterValue")
ReversedEvent = reversed_apps.get_model("n26", "LedgerEvent")
assert not ReversedEvent.objects.filter(
    kind="counter_checkpointed", batch=MIGRATION_BATCH
).exists()
assert ReversedEvent.objects.filter(pk=unrelated.pk).exists()
assert (
    digest(ReversedEvent.objects.filter(pk__in=event_ids), event_fields)
    == before_events
)
assert (
    rows(ReversedValue, pre_reverse_value_ids, "assignment_id", "value")
    == pre_reverse_values
)
ReversedAssignment = reversed_apps.get_model("n26", "Assignment")
assert (
    rows(
        ReversedAssignment,
        pre_reverse_assignment_ids,
        "gang_root_id",
        "archived",
    )
    == pre_reverse_assignments
)
assert ReversedValue.objects.get(pk=modern_value.pk).value == 7
assert ReversedValue.objects.get(pk=legacy_value.pk).value == 6

reapply_started = time.perf_counter()
MigrationExecutor(connection).migrate(FINAL)
reapply_seconds = time.perf_counter() - reapply_started
_, reapplied_apps = state(FINAL)
ReappliedEvent = reapplied_apps.get_model("n26", "LedgerEvent")
ReappliedValue = reapplied_apps.get_model("n26", "CounterValue")
assert (
    ReappliedEvent.objects.filter(
        kind="counter_checkpointed", batch=MIGRATION_BATCH
    ).count()
    == COUNTERS + 2
)
assert ReappliedEvent.objects.filter(pk=unrelated.pk).exists()
assert (
    digest(ReappliedEvent.objects.filter(pk__in=event_ids), event_fields)
    == before_events
)
assert (
    rows(ReappliedValue, pre_reverse_value_ids, "assignment_id", "value")
    == pre_reverse_values
)
ReappliedAssignment = reapplied_apps.get_model("n26", "Assignment")
assert (
    rows(
        ReappliedAssignment,
        pre_reverse_assignment_ids,
        "gang_root_id",
        "archived",
    )
    == pre_reverse_assignments
)
assert ReappliedValue.objects.get(pk=modern_value.pk).value == 7
assert ReappliedValue.objects.get(pk=legacy_value.pk).value == 6

print(
    json.dumps(
        {
            "active_assignments": COUNTERS - ARCHIVED,
            "archived_assignments": ARCHIVED,
            "atomic_failure_seconds": round(failure_seconds, 3),
            "atomic_failure_left_old_state_exact": True,
            "checkpoint_events": COUNTERS,
            "counter_values": COUNTERS,
            "database": database,
            "forward_through_0071_seconds": round(forward_seconds, 3),
            "gangs": GANGS,
            "legacy_existing_counter_gap": existing_gap,
            "legacy_new_counter_gap": new_gap,
            "post_migration_counter_value_survived_reverse": True,
            "preserved_all_pre_reverse_assignments": True,
            "preserved_all_pre_reverse_counter_values": True,
            "preexisting_ledger_digest": before_events[1],
            "preexisting_ledger_events": before_events[0],
            "preserved_all_preexisting_ledger_rows": True,
            "reapply_through_0071_seconds": round(reapply_seconds, 3),
            "removed_event_references": REMOVED,
            "reverse_seconds": round(reverse_seconds, 3),
            "selective_reverse_preserved_unrelated_checkpoint": True,
            "total_seconds": round(time.perf_counter() - whole_started, 3),
            "zero_values": ZERO,
        },
        indent=2,
        sort_keys=True,
    )
)
