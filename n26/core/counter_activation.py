"""Establish counter history while the recorded activation owns the write pause.

Each gang commits separately. Replaying a gang accepts only the checkpoints
already written by this run at the same balances. The last completed gang
audits every counter before enabling structured writers. Zero-counter
installations pass the same audit without a gang to visit.
"""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Exists, OuterRef, Prefetch
from django.utils import timezone

from n26.core.counter_tracking import is_active
from n26.core.models import CounterTracking, CounterValue, Gang, LedgerEvent
from n26.core.reconcile import check_counter_value
from n26.write_pause import require_paused_consumer

BATCH_SIZE = 500


class ActivationRefused(Exception):
    """Counter history cannot be activated from the current data."""


@dataclass(frozen=True)
class ActivationPlan:
    gangs: tuple
    problems: tuple[str, ...] = ()

    @property
    def nothing_here(self):
        return not self.gangs

    def preview(self):
        return (f"Check counter history for {len(self.gangs)} gangs.",)


def preview():
    return {
        "counters": CounterValue.objects.count(),
        "archived": CounterValue.objects.filter(assignment__archived=True).count(),
        "structured_events": LedgerEvent.objects.filter(
            counter_before__isnull=False
        ).count(),
        "without_gang": CounterValue.objects.filter(
            assignment__gang_root__isnull=True
        ).count(),
    }


def plan(run_id, generation, *, cleanup=False):
    with transaction.atomic():
        require_paused_consumer(run_id=run_id, generation=generation)
        gang_ids = set(
            CounterValue.objects.order_by()
            .values_list("assignment__gang_root_id", flat=True)
            .distinct()
        )
        if cleanup:
            gang_ids.update(
                LedgerEvent.objects.filter(
                    batch=run_id, kind=LedgerEvent.Kind.COUNTER_CHECKPOINTED
                )
                .order_by()
                .values_list("gang_id", flat=True)
                .distinct()
            )
        if None in gang_ids:
            return ActivationPlan((), ("A counter or checkpoint has no gang.",))
        if not cleanup and not gang_ids:
            _activate_when_complete(run_id)
        return ActivationPlan(tuple((pk,) for pk in sorted(gang_ids)))


def _counter_values(**filters):
    return (
        CounterValue.objects.filter(**filters)
        .select_related("assignment", "assignment__counter")
        .prefetch_related(
            Prefetch(
                "assignment__ledger_events",
                queryset=LedgerEvent.objects.filter(
                    counter_before__isnull=False
                ).order_by("created", "pk"),
                to_attr="counter_events",
            )
        )
        .order_by("pk")
    )


def checkpoint_gang(gang_id, run_id, generation):
    with transaction.atomic():
        require_paused_consumer(run_id=run_id, generation=generation)
        Gang.objects.select_for_update().get(pk=gang_id)
        active = CounterTracking.objects.filter(activated_at__isnull=False).first()
        if active:
            if str(active.activation_run) == str(run_id):
                return
            raise ActivationRefused("Counter history was activated by another run.")
        pending = []
        for value in _counter_values(assignment__gang_root_id=gang_id).iterator(
            chunk_size=BATCH_SIZE
        ):
            events = value.assignment.counter_events
            if events:
                if (
                    len(events) != 1
                    or str(events[0].batch) != str(run_id)
                    or events[0].kind != LedgerEvent.Kind.COUNTER_CHECKPOINTED
                    or check_counter_value(value, events=events)
                ):
                    raise ActivationRefused(
                        f"Counter {value.pk} has history that this run cannot replace."
                    )
                continue
            pending.append(
                LedgerEvent(
                    assignment_id=value.assignment_id,
                    gang_id=gang_id,
                    kind=LedgerEvent.Kind.COUNTER_CHECKPOINTED,
                    batch=run_id,
                    counter_before=value.value,
                    counter_delta=0,
                    counter_after=value.value,
                )
            )
            if len(pending) == BATCH_SIZE:
                LedgerEvent.objects.bulk_create(pending, batch_size=BATCH_SIZE)
                pending.clear()
        if pending:
            LedgerEvent.objects.bulk_create(pending, batch_size=BATCH_SIZE)
        _activate_when_complete(run_id)


def _activate_when_complete(run_id):
    active = CounterTracking.objects.filter(activated_at__isnull=False).first()
    if active:
        if str(active.activation_run) == str(run_id):
            return
        raise ActivationRefused("Counter history was activated by another run.")
    checkpoint = LedgerEvent.objects.filter(
        assignment_id=OuterRef("assignment_id"),
        batch=run_id,
        kind=LedgerEvent.Kind.COUNTER_CHECKPOINTED,
    )
    if CounterValue.objects.filter(~Exists(checkpoint)).exists():
        return
    for value in _counter_values().iterator(chunk_size=BATCH_SIZE):
        problems = check_counter_value(value, events=value.assignment.counter_events)
        if problems:
            raise ActivationRefused("; ".join(problems))
    CounterTracking.objects.update_or_create(
        pk=1,
        defaults={"activated_at": timezone.now(), "activation_run": run_id},
    )


def cleanup_gang(gang_id, run_id, generation):
    with transaction.atomic():
        require_paused_consumer(run_id=run_id, generation=generation)
        if is_active():
            raise ActivationRefused("Counter history is active and cannot be cleared.")
        Gang.objects.select_for_update().get(pk=gang_id)
        LedgerEvent.objects.filter(
            gang_id=gang_id,
            batch=run_id,
            kind=LedgerEvent.Kind.COUNTER_CHECKPOINTED,
        ).delete()
