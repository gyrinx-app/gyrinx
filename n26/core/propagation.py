"""Propagation — a set change reaches everything already holding it.

An author adds a member to a set of defaults. New acquisitions come
with it from that moment; this module is how everything acquired
*before* the change catches up, within seconds of the commit, without
the author doing anything.

The shape is debt-then-pass. The authoring verb files a durable
:class:`~n26.core.models.ReconcileObligation` in its own transaction —
a rolled-back edit files nothing — and publishes a task message after
commit. The task claims the debt and reconciles every gang holding the
set, one :func:`~n26.core.operations.operation` per gang, through the
same :meth:`~n26.core.operations.Operation.reconcile_defaults` every
acquisition uses. Because reconcile creates only what provenance says
is missing, a pass is idempotent: run twice it grants nothing twice,
which is what makes at-least-once delivery safe underneath.

The claim itself is the obligation's PENDING → RUNNING transition,
validated under the row's own lock — of two concurrent deliveries one
wins and the other stands down silently, a routine outcome. Publishing
is fire-and-forget and can lose a message, so a scheduled sweep
re-publishes debts left PENDING, declares a pass whose worker died
lost, and files a fresh debt after a failure. Retry is always a fresh
row: the graph is strictly forward, and an ended row is a record.
"""

import logging
import traceback
from datetime import timedelta

from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.tasks import task
from django.utils import timezone

from gyrinx.state_machine import InvalidStateTransition
from n26.core.models import Assignment, Gang, LedgerEvent, ReconcileObligation
from n26.core.operations import operation

logger = logging.getLogger(__name__)

#: How long a PENDING debt may stand before the sweep assumes its
#: message was lost and publishes another. Well past a healthy
#: delivery, well inside an author's patience.
REPUBLISH_AFTER = timedelta(minutes=2)

#: How long a RUNNING pass may stand before the sweep declares its
#: worker dead. Longer than any delivery deadline, so a slow pass
#: finishes rather than being declared lost while still working.
GIVE_UP_RUNNING_AFTER = timedelta(minutes=15)

#: How many passes over one set may fail in a row before the sweep
#: stops filing retries. A failure that survives this many attempts
#: needs a fix, not a schedule — and the next authoring edit files a
#: fresh debt anyway, so nothing is stranded for good.
MAX_FAILURES_IN_A_ROW = 3


def file_obligation(default_set):
    """File the debt a set change creates, in the caller's transaction.

    Called by the authoring verb that adds a member, so the debt rides
    the edit: rolled back together, committed together. One PENDING row
    per set — edits arriving before the pass starts share it — and every
    call publishes after commit, because a message is cheap to send and
    to stand down, while the one that was lost is expensive to wait for.
    """
    obligation, _ = ReconcileObligation.objects.get_or_create(
        default_set=default_set, status="PENDING"
    )
    _publish(obligation.pk)
    return obligation


def _publish(obligation_id):
    # After commit, so a rolled-back edit sends nothing and a delivered
    # message always finds its row.
    transaction.on_commit(
        lambda: propagate_built_ins.enqueue(obligation_id=str(obligation_id))
    )


@task
def propagate_built_ins(obligation_id):
    """Pay one filed debt: reconcile every gang holding its set.

    Never raises. A raised error would only be redelivered, and the
    redelivery would stand down at the claim — so every ending is
    written onto the obligation instead, and the sweep is what retries.
    """
    obligation = (
        ReconcileObligation.objects.select_related("default_set")
        .filter(pk=obligation_id)
        .first()
    )
    if obligation is None:
        return
    try:
        obligation.states.transition_to("RUNNING")
    except InvalidStateTransition:
        # Another delivery won, or the pass already ended. Routine.
        return
    try:
        summary = _reconcile_holders(obligation.default_set)
    except Exception as broke:  # noqa: BLE001 — the ending must be recorded
        logger.exception("Propagation pass %s broke", obligation_id)
        _finish(
            obligation,
            "FAILED",
            {"error": f"{broke}\n\n{traceback.format_exc()}"},
        )
        return
    _finish(obligation, "FAILED" if summary["failures"] else "DONE", summary)


def _finish(obligation, status, metadata):
    """End the pass — unless the sweep already declared it lost, in
    which case the fresh debt it filed re-proves the work, so there is
    nothing left to say."""
    try:
        obligation.states.transition_to(status, metadata=metadata)
    except InvalidStateTransition:
        logger.info(
            "Propagation pass %s finished after being declared lost", obligation.pk
        )


def _holders(default_set):
    """The library things whose built-ins are this set."""
    from django.apps import apps

    from n26.library.models.assignable import Assignable

    found = []
    for model in apps.get_app_config("library").get_models():
        if issubclass(model, Assignable):
            found.extend(model.objects.filter(built_ins=default_set))
    return found


def _carrier_ids(default_set):
    """The assignments owed a pass: every use of a holder, and every
    carrier that chose the set as an option. A removal is machinery,
    not a use; an archived carrier is settled history."""
    ids = set()
    for holder in _holders(default_set):
        ids.update(
            Assignment.objects.filter(
                archived=False,
                removes=False,
                **{Assignment.field_for(holder): holder},
            ).values_list("pk", flat=True)
        )
    ids.update(
        Assignment.objects.filter(
            chosen_options__default_set=default_set,
            archived=False,
            removes=False,
        ).values_list("pk", flat=True)
    )
    return ids


def _reconcile_holders(default_set):
    """One pass over every gang holding the set, each gang its own
    operation committing on its own — a gang the pass cannot settle is
    recorded and stepped past, never allowed to starve the rest."""
    by_gang = {}
    for carrier_id, gang_id in Assignment.objects.filter(
        pk__in=_carrier_ids(default_set)
    ).values_list("pk", "gang_root_id"):
        if gang_id is not None:
            by_gang.setdefault(gang_id, []).append(carrier_id)

    summary = {"gangs": 0, "granted": 0, "skipped": 0, "failures": {}}
    for gang_id in sorted(by_gang, key=str):
        # An archived gang is one its owner parted with; nothing is
        # granted behind their back. Unarchived later, it catches up
        # with the next pass over this set, or with the backfill.
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
def sweep_built_in_obligations():
    """Drain what the happy path dropped.

    Three legs, each idempotent, so overlapping sweeps do no harm: a
    duplicate publish stands down at the claim, and a duplicate filing
    meets the one-PENDING-per-set constraint.
    """
    now = timezone.now()

    # A debt still PENDING this long after filing lost its message.
    for obligation_id in ReconcileObligation.objects.filter(
        status="PENDING", created__lt=now - REPUBLISH_AFTER
    ).values_list("pk", flat=True):
        propagate_built_ins.enqueue(obligation_id=str(obligation_id))

    # A pass RUNNING this long lost its worker. Declaring it FAILED
    # keeps every row's ending written; the retry leg below files the
    # fresh debt. A worker that was merely slow finds its own ending
    # already written and stands down.
    for obligation in ReconcileObligation.objects.filter(
        status="RUNNING", modified__lt=now - GIVE_UP_RUNNING_AFTER
    ):
        try:
            obligation.states.transition_to(
                "FAILED",
                metadata={"error": "declared lost by the sweep: no ending recorded"},
            )
        except InvalidStateTransition:
            continue

    _refile_failures()


def _refile_failures():
    """A set whose latest pass failed is owed another, up to the cap."""
    latest = (
        ReconcileObligation.objects.filter(default_set=OuterRef("default_set"))
        .order_by("-created")
        .values("pk")[:1]
    )
    stalled = ReconcileObligation.objects.filter(
        status="FAILED", pk=Subquery(latest)
    ).select_related("default_set")
    for obligation in stalled:
        if _failures_in_a_row(obligation.default_set_id) >= MAX_FAILURES_IN_A_ROW:
            continue
        file_obligation(obligation.default_set)


def _failures_in_a_row(default_set_id):
    count = 0
    statuses = (
        ReconcileObligation.objects.filter(default_set_id=default_set_id)
        .order_by("-created")
        .values_list("status", flat=True)
    )
    for status in statuses:
        if status != "FAILED":
            break
        count += 1
    return count
