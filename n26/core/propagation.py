"""Reconcile existing carriers after built-in set edits through background tasks.

Authoring creates a fresh BuiltInPropagationTask in the edit transaction
and publishes after commit. A worker claims PENDING to RUNNING under a
row lock, so duplicate deliveries cannot run the same task concurrently.
Reconcile each gang in its own operation through ``reconcile_defaults``;
provenance prevents repeat grants.

Every edit needs a fresh task: reusing a pending task could let a worker
read content before the edit commits and omit the change. Redundant later
tasks safely reconcile to no changes.

The sweep republishes pending tasks, fails abandoned runs and files fresh
tasks for retryable failures. Completed task records remain unchanged.

The execution flag gates workers and sweeps, while edits always file
tasks. Disabled execution preserves a pending backlog. Preview helpers use
the same carrier resolution, but workers recompute against current content.
"""

import logging
import traceback
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.tasks import task
from django.utils import timezone

from gyrinx.state_machine import InvalidStateTransition
from n26.core.models import Assignment, BuiltInPropagationTask, Gang, LedgerEvent
from n26.core.operations import operation
from n26.flags import BUILT_IN_PROPAGATION, switched_on

logger = logging.getLogger(__name__)

#: Minimum age of a PENDING task before the sweep republishes it.
REPUBLISH_AFTER = timedelta(minutes=2)

#: Minimum time since a RUNNING task's last update before declaring it lost.
GIVE_UP_RUNNING_AFTER = timedelta(minutes=15)

#: Consecutive failure limit for automatic retries. A later authoring edit
#: still creates a fresh task.
MAX_FAILURES_IN_A_ROW = 3


def file_propagation_task(default_set):
    """Create a fresh propagation task within the caller's edit transaction.

    Publish after commit so the worker sees the edited content. Rollbacks
    discard both the edit and its task.
    """
    filed = BuiltInPropagationTask.objects.create(default_set=default_set)
    _publish(filed.pk)
    return filed


def _publish(propagation_id):
    # After commit, so a rolled-back edit sends nothing and a delivered
    # message always finds its row.
    transaction.on_commit(
        lambda: propagate_built_ins.enqueue(propagation_id=str(propagation_id))
    )


@task
def propagate_built_ins(propagation_id):
    """Run one filed pass: reconcile every gang holding its set.

    Never raises. A raised error would only be redelivered, and the
    redelivery would stand down at the claim — so every ending is
    written onto the row instead, and the sweep is what retries.
    """
    # Before the claim, so shut loses no work: the row stays PENDING
    # and the sweep drains the backlog when the flag opens.
    if not switched_on(BUILT_IN_PROPAGATION):
        return
    propagation = (
        BuiltInPropagationTask.objects.select_related("default_set")
        .filter(pk=propagation_id)
        .first()
    )
    if propagation is None:
        return
    try:
        propagation.states.transition_to("RUNNING")
    except InvalidStateTransition:
        # Another delivery won, or the pass already ended. Routine.
        return
    try:
        summary = _reconcile_holders(propagation.default_set)
    except Exception as broke:  # noqa: BLE001 — the ending must be recorded
        logger.exception("Propagation pass %s broke", propagation_id)
        _finish(
            propagation,
            "FAILED",
            {"error": f"{broke}\n\n{traceback.format_exc()}"},
        )
        return
    _finish(propagation, "FAILED" if summary["failures"] else "DONE", summary)


def _finish(propagation, status, metadata):
    """End the pass — unless the sweep already declared it lost, in
    which case the fresh row it filed re-proves the work, so there is
    nothing left to say."""
    try:
        propagation.states.transition_to(status, metadata=metadata)
    except InvalidStateTransition:
        logger.info(
            "Propagation pass %s finished after being declared lost", propagation.pk
        )


def _holders(default_sets):
    """The library things whose built-ins are one of these sets."""
    from django.apps import apps

    from n26.library.models.assignable import Assignable

    found = []
    for model in apps.get_app_config("library").get_models():
        if issubclass(model, Assignable):
            found.extend(model.objects.filter(built_ins__in=default_sets))
    return found


def _carriers_of(default_sets):
    """Find live non-removal assignments using these built-ins or selected sets.

    Execution and preview reach counts share this queryset.
    """
    holds = Q(chosen_options__default_set__in=default_sets)
    by_field = {}
    for holder in _holders(default_sets):
        by_field.setdefault(Assignment.field_for(holder), []).append(holder)
    for field, holders in by_field.items():
        holds |= Q(**{f"{field}__in": holders})
    return Assignment.objects.filter(holds, archived=False, removes=False).distinct()


def _carrier_ids(default_set):
    return set(_carriers_of([default_set]).values_list("pk", flat=True))


@dataclass(frozen=True)
class Reach:
    """How far a change to a set's members travels: the live uses that
    a pass would visit, and the gangs they sit in."""

    uses: int
    gangs: int


def reach_of(default_set):
    """The reach of a member added to this set, counted without writing
    anything. A member being added does not exist yet, so the reach is
    simply every current use of the set — holders' uses and option
    selectors alike, outside archived gangs, exactly the carriers a
    pass then visits."""
    return _reach(_carriers_of([default_set]))


def reach_of_all(default_sets):
    """The combined reach of several sets, each use counted once even
    where one carrier holds more than one of them."""
    sets = list(default_sets)
    if not sets:
        return Reach(uses=0, gangs=0)
    return _reach(_carriers_of(sets))


def reach_of_new_built_ins(holder):
    """The reach of the built-ins set a first built-in would found on
    this thing. No set exists yet, so its only uses are the thing's
    own."""
    return _reach(
        Assignment.objects.filter(
            archived=False,
            removes=False,
            **{Assignment.field_for(holder): holder},
        )
    )


def assignments_naming(member):
    """The live assignments materialised from one set member, and the
    gangs holding them.

    What taking the member off the set leaves behind: nothing retracts
    an assignment, so every one of these stays exactly where it is.
    Counted by provenance, so an owner's own copy of the same thing is
    not counted among them.
    """
    return _reach(
        Assignment.objects.filter(
            materialised_from=member, archived=False, removes=False
        )
    )


def _reach(carriers):
    # An archived gang is skipped by the pass, so its uses are outside
    # the reach; a carrier belonging to no gang likewise.
    counted = carriers.filter(gang_root__archived=False).aggregate(
        uses=Count("pk", distinct=True),
        gangs=Count("gang_root", distinct=True),
    )
    return Reach(**counted)


def _reconcile_holders(default_set):
    """Reconcile each affected gang in a separate operation and transaction.

    Record failures and continue so one invalid gang cannot block the rest.
    """
    by_gang = {}
    for carrier_id, gang_id in Assignment.objects.filter(
        pk__in=_carrier_ids(default_set)
    ).values_list("pk", "gang_root_id"):
        if gang_id is not None:
            by_gang.setdefault(gang_id, []).append(carrier_id)

    summary = {"gangs": 0, "granted": 0, "skipped": 0, "failures": {}}
    for gang_id in sorted(by_gang, key=str):
        # Skip archived gangs. Restored gangs catch up on another pass or backfill.
        gang = Gang.objects.filter(pk=gang_id, archived=False).first()
        if gang is None:
            continue
        try:
            granted, skipped = _reconcile_gang(gang, by_gang[gang_id])
        except Exception as broke:  # noqa: BLE001 — one gang never starves the rest
            logger.exception("Propagation could not settle gang %s", gang_id)
            summary["failures"][str(gang_id)] = str(broke)
            continue
        summary["gangs"] += 1
        summary["granted"] += granted
        summary["skipped"] += skipped
    return summary


def _reconcile_gang(gang, carrier_ids):
    """Reconcile one gang's carriers inside one operation.

    The carriers are re-read under the gang's own lock, so one archived
    since the pass was planned is left alone. Grants say they arrived
    by catch-up — the one place that kind is used — and the pass is
    nobody's act, so the operation carries no actor.
    """
    granted = 0
    skipped = 0
    with operation(gang, actor=None) as op:
        carriers = Assignment.objects.filter(
            pk__in=carrier_ids, archived=False, removes=False
        )
        for carrier in carriers:
            # The founding is gang-hosted and about no model, so its
            # grants land on the gang — the same split hire makes.
            hosted_on_gang = (
                carrier.miniature_root_id is None and carrier.gang_id is not None
            )
            outcome = op.reconcile_defaults(
                carrier,
                gang=carrier.gang if hosted_on_gang else None,
                strict=False,
                event_kind=LedgerEvent.Kind.CAUGHT_UP,
            )
            granted += len(outcome.created)
            skipped += len(outcome.skipped)
    return granted, skipped


@task
def sweep_built_in_propagations():
    """Republish pending work, fail abandoned runs and retry eligible failures.

    Duplicate messages cannot claim an already claimed task. Redundant tasks
    reconcile idempotently, making overlapping sweeps safe.
    """
    # While disabled, retain pending work without republishing or refiling it.
    if not switched_on(BUILT_IN_PROPAGATION):
        return
    now = timezone.now()

    # A row still PENDING this long after filing lost its message.
    for propagation_id in BuiltInPropagationTask.objects.filter(
        status="PENDING", created__lt=now - REPUBLISH_AFTER
    ).values_list("pk", flat=True):
        propagate_built_ins.enqueue(propagation_id=str(propagation_id))

    # Fail timed-out tasks before filing fresh retries. A slow worker that
    # later finishes finds the task already ended and stops.
    for propagation in BuiltInPropagationTask.objects.filter(
        status="RUNNING", modified__lt=now - GIVE_UP_RUNNING_AFTER
    ):
        try:
            propagation.states.transition_to(
                "FAILED",
                metadata={"error": "declared lost by the sweep: no ending recorded"},
            )
        except InvalidStateTransition:
            continue

    _refile_failures()


def _refile_failures():
    """Retry sets whose latest propagation failed, up to the attempt cap."""
    latest = (
        BuiltInPropagationTask.objects.filter(default_set=OuterRef("default_set"))
        .order_by("-created")
        .values("pk")[:1]
    )
    stalled = BuiltInPropagationTask.objects.filter(
        status="FAILED", pk=Subquery(latest)
    ).select_related("default_set")
    for propagation in stalled:
        if _failures_in_a_row(propagation.default_set_id) >= MAX_FAILURES_IN_A_ROW:
            continue
        file_propagation_task(propagation.default_set)


def _failures_in_a_row(default_set_id):
    count = 0
    statuses = (
        BuiltInPropagationTask.objects.filter(default_set_id=default_set_id)
        .order_by("-created")
        .values_list("status", flat=True)
    )
    for status in statuses:
        if status != "FAILED":
            break
        count += 1
    return count
