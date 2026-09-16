"""Rehearse dormant deployment, failed activation, cleanup and activation."""

import hashlib
import json
import os
import time
from datetime import timedelta
from unittest.mock import patch

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gyrinx.settings_dev")
django.setup()

from django.db import connection  # noqa: E402, I001
from django.db.migrations.executor import MigrationExecutor  # noqa: E402

PREFIX = "wren_counter_activation_evidence_"
OLD = [("n26", "0068_remove_assignment_assignment_exactly_one_assignable_and_more")]
COUNTERS, ZERO, ARCHIVED = 19_940, 863, 2_672
EVENTS, REMOVED, GANGS = 228_571, 2_643, 20


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

from django.core.management import call_command  # noqa: E402

schema_started = time.perf_counter()
call_command("migrate", interactive=False, verbosity=0)
schema_seconds = time.perf_counter() - schema_started

from gyrinx.maintenance.models import Backfill  # noqa: E402
from gyrinx.site.models import WritePause  # noqa: E402
from gyrinx.tasks import local_backend  # noqa: E402
from gyrinx.tasks.models import QueuedTask  # noqa: E402
from gyrinx.tasks.worker import Outcome, deliver  # noqa: E402
from n26 import maintenance  # noqa: E402
from n26.core import counter_activation  # noqa: E402
from n26.core.counter_tracking import is_active  # noqa: E402
from n26.core.models import Assignment as NewAssignment  # noqa: E402
from n26.core.models import CounterValue as NewValue  # noqa: E402
from n26.core.models import Gang as NewGang  # noqa: E402
from n26.core.models import LedgerEvent as NewEvent  # noqa: E402
from n26.core.operations import operation  # noqa: E402

assert not is_active()
assert not NewEvent.objects.filter(counter_before__isnull=False).exists()
assert rows(NewValue, value_ids, "assignment_id", "value") == before_values
assert (
    rows(NewAssignment, assignment_ids, "gang_root_id", "archived")
    == before_assignments
)
assert digest(NewEvent.objects.filter(pk__in=event_ids), event_fields) == before_events

# Both serving revisions can write before activation. Persist the old worker's
# shape, then exercise the deployed inactive writer against the same counter.
sample = assignments[ZERO + 17]
CounterValue.objects.filter(assignment_id=sample.pk).update(value=42)
LedgerEvent.objects.create(
    gang_id=sample.gang_root_id,
    assignment_id=sample.pk,
    kind="tallied",
    note="Synthetic legacy worker: counter set to 42",
)
with operation(NewGang.objects.get(pk=sample.gang_root_id)) as op:
    op.tally(NewAssignment.objects.get(pk=sample.pk), 2)
assert NewValue.objects.get(assignment_id=sample.pk).value == 44
assert not NewEvent.objects.filter(counter_before__isnull=False).exists()

expected_values = rows(NewValue, value_ids, "assignment_id", "value")
expected_assignments = rows(NewAssignment, assignment_ids, "gang_root_id", "archived")
expected_event_ids = list(NewEvent.objects.values_list("pk", flat=True))
expected_digest = digest(NewEvent.objects.filter(pk__in=expected_event_ids))


def assert_preserved():
    assert rows(NewValue, value_ids, "assignment_id", "value") == expected_values
    assert (
        rows(NewAssignment, assignment_ids, "gang_root_id", "archived")
        == expected_assignments
    )
    assert digest(NewEvent.objects.filter(pk__in=expected_event_ids)) == expected_digest
    assert (
        rows(NewEvent, before_removed, "gang_id", "assignment_id", "kind", "note")
        == before_removed
    )


def drain_queue():
    for _ in range(100):
        queued = QueuedTask.objects.claim_one(
            worker_id="counter-rehearsal",
            lease=timedelta(minutes=10),
            ignore_schedule=True,
        )
        if queued is None:
            return
        outcome = deliver(queued, sender=local_backend.DatabaseBackend)
        assert outcome == Outcome.SUCCESS, outcome
    raise AssertionError("Activation queue did not drain")


local_backend.set_mode_override("manual")
failed_run = maintenance.start_counter_history(None)
generation = failed_run.summary["pause_generation"]
original_checkpoint = counter_activation.checkpoint_gang
failure_gang = gangs[1].pk


def fail_one(gang_id, run_id, pause_generation):
    if gang_id == failure_gang:
        raise RuntimeError("Intentional checkpoint failure")
    return original_checkpoint(gang_id, run_id, pause_generation)


failed_started = time.perf_counter()
with patch.object(counter_activation, "checkpoint_gang", fail_one):
    drain_queue()
failure_seconds = time.perf_counter() - failed_started
failed_run.refresh_from_db()
assert failed_run.status == Backfill.Status.FAILED
assert not is_active()
assert WritePause.objects.get(scope="n26").state == WritePause.State.PAUSED
partial_count = NewEvent.objects.filter(
    batch=failed_run.pk, kind=NewEvent.Kind.COUNTER_CHECKPOINTED
).count()
assert 0 < partial_count < COUNTERS
assert_preserved()

cleanup_started = time.perf_counter()
maintenance.restart_counter_history(failed_run.pk, generation, cleanup=True)
drain_queue()
cleanup_seconds = time.perf_counter() - cleanup_started
assert not is_active()
assert not NewEvent.objects.filter(batch=failed_run.pk).exists()
assert_preserved()
maintenance.resume_after_counter_history(failed_run.pk, generation, None)

# A later activation must use the balance after legacy writes resumed.
with operation(NewGang.objects.get(pk=sample.gang_root_id)) as op:
    op.tally(NewAssignment.objects.get(pk=sample.pk), 3)
expected_values = rows(NewValue, value_ids, "assignment_id", "value")
expected_event_ids = list(NewEvent.objects.values_list("pk", flat=True))
expected_digest = digest(NewEvent.objects.filter(pk__in=expected_event_ids))

activation_started = time.perf_counter()
completed_run = maintenance.start_counter_history(None)
generation = completed_run.summary["pause_generation"]
drain_queue()
activation_seconds = time.perf_counter() - activation_started
completed_run.refresh_from_db()
assert completed_run.status == Backfill.Status.DONE
assert is_active()
assert WritePause.objects.get(scope="n26").state == WritePause.State.PAUSED
assert_preserved()

checkpoints = {
    str(row[0]): tuple(row[1:])
    for row in NewEvent.objects.filter(
        batch=completed_run.pk, kind=NewEvent.Kind.COUNTER_CHECKPOINTED
    ).values_list(
        "assignment_id", "gang_id", "counter_before", "counter_delta", "counter_after"
    )
}
assert len(checkpoints) == COUNTERS
assert NewEvent.objects.filter(batch=completed_run.pk).count() == COUNTERS
for _pk, (assignment_id, value) in expected_values.items():
    gang_id, _archived = expected_assignments[str(assignment_id)]
    assert checkpoints[str(assignment_id)] == (gang_id, value, 0, value)

checkpoint_ids = set(
    NewEvent.objects.filter(batch=completed_run.pk).values_list("pk", flat=True)
)
maintenance.activate_counter_history.enqueue(
    backfill_id=str(completed_run.pk), pause_generation=generation
)
drain_queue()
assert (
    set(NewEvent.objects.filter(batch=completed_run.pk).values_list("pk", flat=True))
    == checkpoint_ids
)
maintenance.resume_after_counter_history(completed_run.pk, generation, None)
with operation(NewGang.objects.get(pk=sample.gang_root_id)) as op:
    op.tally(NewAssignment.objects.get(pk=sample.pk), -4)
payment = NewEvent.objects.filter(
    assignment_id=sample.pk, kind=NewEvent.Kind.TALLIED, counter_before__isnull=False
).get()
assert (payment.counter_before, payment.counter_delta, payment.counter_after) == (
    47,
    -4,
    43,
)
assert NewValue.objects.get(assignment_id=sample.pk).value == 43

print(
    json.dumps(
        {
            "database": database,
            "counters": COUNTERS,
            "archived_counters": ARCHIVED,
            "zero_counters": ZERO,
            "old_events": EVENTS,
            "removed_references": REMOVED,
            "partial_checkpoints": partial_count,
            "schema_seconds": schema_seconds,
            "failed_activation_seconds": failure_seconds,
            "cleanup_seconds": cleanup_seconds,
            "activation_seconds": activation_seconds,
            "total_seconds": time.perf_counter() - whole_started,
            "journal_digest_before_activation": expected_digest,
            "all_balances_and_references_preserved": True,
            "old_and_new_writers_before_activation": True,
            "failed_activation_kept_writes_paused": True,
            "cleanup_removed_only_failed_run": True,
            "fresh_activation_used_new_balances": True,
            "redelivery_preserved_checkpoint_ids": True,
            "manual_resume_required": True,
            "structured_payment_after_resume": [47, -4, 43],
        },
        indent=2,
    )
)
