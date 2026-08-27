"""The repairs this edition offers the maintenance console, and the one
door it offers them through.

The console is the site's: a superuser-gated index, one audit record per
run, a detail page, a cancel button. What there is to repair is edition
knowledge, so an edition registers its own operations rather than the
console knowing about either of them. This module is the whole of n26's
dependency on it — the registry, the audit record, the page furniture and
the background-task route are imported here and nowhere else in ``n26/``,
so the seam can be read and moved in one place.

A repair here does not travel as a migration. A migration that runs
live code inherits a dependency on every column that code will ever
read, and the pin needed to express that contradicts the recorded
history of any database that already ran it — so a repair runs after a
deploy instead, on a schema that is fully migrated by construction.

Runs come in two shapes, and each states its own promise. A small
repair (``_run_recorded``) is one transaction, deliberately
all-or-nothing: interrupted, it rolls back whole and can simply be run
again. Work too large for one transaction (``run_batched``) commits row
by row instead, writes how far it got onto the record, and continues
from there after any interruption — which trades the clean rollback for
a requirement that each row's work be idempotent. Delivery is
at-least-once, so two guards stand between either promise and a second
copy running alongside the first: a lock only one run can hold, and a
cap on how many attempts may start without recording any progress
before the record gives up and says so. A batched run resets that count
with every batch it records, so a long run's many deliveries are never
mistaken for a stuck one.

A repair that has been run and cannot recur keeps its slug registered
with no view. It leaves the menu, and the record of the run still reads
as a name rather than a bare slug.
"""

import logging
import traceback
from contextlib import contextmanager
from datetime import date, timedelta

from django.contrib import messages
from django.db import connection, models, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.tasks import task
from django.urls import reverse
from django.utils import timezone

from gyrinx.maintenance.models import Backfill
from gyrinx.maintenance.registry import MaintenanceOperation, register_operation
from gyrinx.maintenance.views import page_context, running_guard
from gyrinx.tasks import TaskRoute
from n26.core.propagation import propagate_built_ins, sweep_built_in_propagations

logger = logging.getLogger(__name__)

__all__ = [
    "Operation",
    "delete_nameless_gang_type",
    "run_batched",
    "task_routes",
]

#: How many times a run may start without recording any progress before
#: the record gives up. A one-transaction run that dies leaves nothing
#: behind and is redelivered; a batched run resets the count every time
#: it records a batch. Either way, without the cap a run that always
#: dies would repeat for ever, each attempt paying its cost again.
MAX_ATTEMPTS = 2

#: The locks a run holds for as long as it is working — one per
#: operation, declared beside their operations below. A lock fences the
#: redeliveries of one operation's own run; shared between operations it
#: would do worse than fence: the view's running-guard only sees its own
#: operation's records, so one repair could enqueue while another held
#: the lock, stand down there without writing, acknowledge its
#: message, and leave a record saying RUNNING for ever. Postgres
#: releases an advisory lock when the connection goes, so a killed run
#: frees it without anyone intervening.


class Operation(models.TextChoices):
    """The repairs this edition offers, by the slug written into each
    audit record. A slug is permanent: changing one orphans every
    historical record that carries it."""

    CONVERT_SPECIALISATION = (
        "n26_convert_specialisation",
        "n26: the specialisations become picks",
    )
    CONVERT_SKILL_TREE = (
        "n26_convert_skill_tree",
        "n26: the Venator skill trees become picks",
    )
    CONVERT_GANG_LEGACY = (
        "n26_convert_gang_legacy",
        "n26: the Venator gang legacies become picks",
    )
    RETIRE_GANG_LEGACY_PILOT = (
        "n26_retire_gang_legacy_pilot",
        "n26: the gang legacy slot pilot retires",
    )
    CONVERT_ARCHETYPE = (
        "n26_convert_archetype",
        "n26: the Outcast archetypes become picks",
    )
    CONVERT_OUTCAST_AFFILIATION = (
        "n26_convert_outcast_affiliation",
        "n26: the Outcast affiliations become picks",
    )
    SWEEP_ARCHIVED = (
        "n26_sweep_archived",
        "n26: the answers already taken back become picks",
    )
    DELETE_NAMELESS_GANG_TYPE = (
        "n26_delete_nameless_gang_type",
        "n26: the gang type with no name is retired",
    )
    CLEAR_SPARE_ANSWERS = (
        "n26_clear_spare_answers",
        "n26: the answers a doubled click left behind are cleared",
    )
    DELETE_RETIRED_KINDS = (
        "n26_delete_retired_kinds",
        "n26: what the conversions left standing is deleted",
    )
    MERGE_WARGEAR_INTO_WEAPON = (
        "n26_merge_wargear_into_weapon",
        "n26: duplicated wargear becomes its weapon",
    )
    AUDIT_RECONCILE = (
        "n26_audit_reconcile",
        "n26: every gang's books are checked against its ledger",
    )


#: See the note on locks above: one per operation, never shared.
LOCK_KEYS = {
    Operation.DELETE_NAMELESS_GANG_TYPE: 826_020_606,
    Operation.AUDIT_RECONCILE: 826_020_607,
    Operation.CONVERT_OUTCAST_AFFILIATION: 826_020_608,
}


def _write(backfill_id, *, status=None, summary_patch=None, error=""):
    """Record what happened, under the row's own lock.

    A record that has reached an ending keeps it. Only one copy of a run
    ever works — the lock sees to that — so whatever wrote the ending was
    the run itself, and anything arriving afterwards is a redelivery with
    nothing new to say. A long run finishes close to the moment its
    delivery is retried, so the copy that finds the work already done is
    the likely case, not the exotic one: were it allowed to write, it
    would file a successful run as a failure.

    An operator's stop counts as an ending too, and outranks the rest.
    """
    ENDINGS = (Backfill.Status.DONE, Backfill.Status.FAILED, Backfill.Status.CANCELLED)
    with transaction.atomic():
        try:
            backfill = Backfill.objects.select_for_update().get(pk=backfill_id)
        except Backfill.DoesNotExist:
            logger.warning("Backfill record %s missing; progress dropped", backfill_id)
            return False
        if backfill.status in ENDINGS:
            logger.info(
                "Backfill %s is already %s; dropping write (attempted %s)",
                backfill_id,
                backfill.status,
                status or "progress",
            )
            return False
        if summary_patch:
            backfill.summary = {**backfill.summary, **summary_patch}
        if status:
            backfill.status = status
        if error:
            backfill.error = error
        backfill.save()
        return True


@contextmanager
def _single_flight(lock_key):
    """Hold one operation's lock for the length of a run, or yield False.

    Postgres frees an advisory lock when the connection goes, so a run
    killed mid-flight leaves nothing to clean up by hand.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [lock_key])
        held = cursor.fetchone()[0]
    try:
        yield held
    finally:
        if held:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [lock_key])


def _claim(backfill_id):
    """Count this attempt and say whether it may start.

    Written outside the run's own transaction, so the count
    survives a run that rolls back — which is how a run too large to
    finish is noticed rather than repeated for ever.
    """
    with transaction.atomic():
        try:
            backfill = Backfill.objects.select_for_update().get(pk=backfill_id)
        except Backfill.DoesNotExist:
            return False, "the record this run would write to is gone"
        if backfill.status != Backfill.Status.RUNNING:
            return False, f"the record is already {backfill.get_status_display()}"
        attempts = int(backfill.summary.get("attempts", 0)) + 1
        backfill.summary = {**backfill.summary, "attempts": attempts}
        backfill.save()
        if attempts > MAX_ATTEMPTS:
            return False, (
                f"started {attempts} times without getting anywhere — each "
                "attempt died before recording an ending or any progress. "
                "Look at what kills the attempt (its deadline, its size) "
                "before running again."
            )
        return True, ""


def _run_recorded(backfill_id, operation, what, work, refusals):
    """Run one operation's work, once, under the full runner discipline.

    The discipline is the part that must never regress, so it is held
    here once for everything the console runs: take the operation's own
    lock and stand down silently if another copy holds it; count the
    attempt on the record and give up past the cap; record a refusal in
    its own words, an unexpected failure with its traceback, and a
    finished report — and never raise, because a task that fails is
    redelivered and there is nowhere for a raised error to go but round
    again.
    """
    with _single_flight(LOCK_KEYS[operation]) as mine:
        if not mine:
            logger.info("%s already running; this copy stands down", what)
            return

        may_start, why_not = _claim(backfill_id)
        if not may_start:
            logger.info("%s not started: %s", what, why_not)
            _write(
                backfill_id,
                status=Backfill.Status.FAILED,
                error=f"Not started: {why_not}",
            )
            return

        try:
            report = work()
        except refusals as refused:
            # A refusal is the discipline working: nothing was written,
            # and the reason is already in words.
            _write(backfill_id, status=Backfill.Status.FAILED, error=str(refused))
            return
        except Exception as broke:  # noqa: BLE001 — the ending must be recorded
            logger.exception("%s broke", what)
            _write(
                backfill_id,
                status=Backfill.Status.FAILED,
                error=f"{broke}\n\n{traceback.format_exc()}",
            )
            return

        _write(
            backfill_id,
            status=Backfill.Status.DONE,
            summary_patch={"report": list(report)},
        )


#: How long one batched attempt may work before handing the rest back
#: to the queue. The invariant a consumer's route must satisfy: this
#: budget plus the time one batch takes must fit inside the route's
#: acknowledgement deadline, or the queue redelivers an attempt that is
#: still working. The default fits the framework's default deadline
#: with a minute to spare for the batch in flight.
BATCH_BUDGET = timedelta(minutes=4)

#: How many rows a batched run settles between progress writes. Small
#: enough that a crash replays little; large enough that the record is
#: not written per row.
BATCH_SIZE = 50


def run_batched(
    backfill_id,
    *,
    operation,
    what,
    items,
    do_one,
    again,
    batch_size=BATCH_SIZE,
    budget=BATCH_BUDGET,
):
    """Work through ``items`` one at a time, each on its own commit,
    remembering how far it got.

    ``_run_recorded`` holds a whole run inside one transaction; this is
    the shape for work too large for that. ``items`` is a queryset with
    a unique primary key — ordered here, because the cursor is only
    sound over a total order — and it must be stable: a queryset that
    stops matching rows as they are settled moves the finish line while
    the cursor chases it. ``do_one(pk)`` settles one row completely,
    committing its own writes and leaving nothing behind when it fails.
    It must be idempotent: a crashed attempt replays at most one batch,
    and a rerun is a fresh record that walks every row again, settling
    only what the earlier run missed.

    Progress lands on the record after every batch — how many rows are
    settled, of how many, the failures so far, and the cursor the next
    attempt continues from. That write doubles as the cancel check: an
    operator's CANCELLED is an ending, endings are final, so the
    refused write is the signal to stop, and the rows already settled
    stay settled. It also starts the attempt count over, which is what
    lets ``_claim`` serve both run shapes: only an attempt that dies
    before recording any progress counts towards giving up.

    A failing row is written down and stepped past; one that settles on
    a later walk is struck off. The ending is DONE only when nothing
    failed. Past ``budget`` the attempt records the cursor and hands
    the rest to a fresh delivery — enqueued only after the lock is
    released, so the delivery it summons can never find the lock still
    held, stand down, and leave the record RUNNING with no delivery
    left to finish it.

    The work never raises, for ``_run_recorded``'s reason: a raised
    error is only redelivered, and there is nowhere for it to go but
    round again. The hand-back is the one deliberate exception: an
    enqueue that fails is allowed to raise, because the failed delivery
    is then redelivered and the retry re-summons the continuation —
    swallowing it would leave no delivery to finish the run.
    """
    continued = False
    with _single_flight(LOCK_KEYS[operation]) as mine:
        if not mine:
            logger.info("%s already running; this copy stands down", what)
            return
        may_start, why_not = _claim(backfill_id)
        if not may_start:
            logger.info("%s not started: %s", what, why_not)
            _write(
                backfill_id,
                status=Backfill.Status.FAILED,
                error=f"Not started: {why_not}",
            )
            return
        try:
            continued = _work_through(
                backfill_id, what, items, do_one, batch_size, budget
            )
        except Exception as broke:  # noqa: BLE001 — the ending must be recorded
            logger.exception("%s broke", what)
            _write(
                backfill_id,
                status=Backfill.Status.FAILED,
                error=f"{broke}\n\n{traceback.format_exc()}",
            )
    if continued:
        again()


def _work_through(backfill_id, what, items, do_one, batch_size, budget):
    """One attempt's walk. True means a fresh delivery must continue."""
    started = timezone.now()
    backfill = Backfill.objects.get(pk=backfill_id)
    cursor = backfill.summary.get("cursor", "")
    settled = int(backfill.summary.get("done", 0))
    failures = dict(backfill.summary.get("failures", {}))
    # Counted once, on the first attempt: the finish line must not move
    # while the cursor chases it.
    total = backfill.summary.get("total")
    if total is None:
        total = items.count()

    items = items.order_by("pk")

    def record(position):
        # Resetting the attempt count is what marks this attempt as
        # having got somewhere — see the docstring above.
        return _write(
            backfill_id,
            summary_patch={
                "done": settled,
                "total": total,
                "cursor": str(position),
                "failures": failures,
                "attempts": 0,
            },
        )

    def stopped():
        still = (
            Backfill.objects.filter(pk=backfill_id)
            .values_list("status", flat=True)
            .first()
        )
        if still is None:
            logger.warning(
                "%s: the record is gone mid-run; stopping with the work half-applied",
                what,
            )
        else:
            logger.info(
                "%s ended by the operator (%s); stopping where it stands", what, still
            )

    while True:
        # Checked before the batch as well as written after it, so a
        # cancel landing between batches stops the very next one rather
        # than one batch later. One cheap read per batch.
        still_running = Backfill.objects.filter(
            pk=backfill_id, status=Backfill.Status.RUNNING
        ).exists()
        if not still_running:
            stopped()
            return False
        narrowed = items.filter(pk__gt=cursor) if cursor else items
        batch = list(narrowed.values_list("pk", flat=True)[:batch_size])
        if not batch:
            break
        for pk in batch:
            try:
                do_one(pk)
            except Exception as broke:  # noqa: BLE001 — one row never starves the rest
                logger.exception("%s could not settle %s", what, pk)
                failures[str(pk)] = str(broke)
            else:
                settled += 1
                failures.pop(str(pk), None)
        cursor = str(batch[-1])
        if not record(cursor):
            stopped()
            return False
        # Hand back only while something remains — a spent budget on
        # the final batch ends the run rather than summoning a
        # delivery with nothing to do.
        if timezone.now() - started > budget and items.filter(pk__gt=cursor).exists():
            return True

    if failures:
        _write(
            backfill_id,
            status=Backfill.Status.FAILED,
            error=(
                f"{len(failures)} of {total} could not be settled; the "
                "rest are done. A rerun walks everything again and "
                "settles only what failed."
            ),
        )
    else:
        _write(backfill_id, status=Backfill.Status.DONE)
    return False


def _plan(system):
    from n26.library.conversion import SYSTEMS

    return SYSTEMS[system]()


def _run_conversion(backfill_id, operation, system, **said_by_whoever_enqueued_it):
    """Run one conversion, once, and write down the outcome.

    Takes whatever else it is handed and ignores it. Delivery outlives a
    deploy, so a message can arrive naming arguments the version that
    enqueued it had and this one does not — and a task that refuses its
    own message is retried for ever, there being nowhere for it to go.
    """
    from n26.library.conversion import ConversionRefused, apply

    _run_recorded(
        backfill_id,
        operation,
        f"{system.replace('_', ' ').capitalize()} conversion",
        lambda: apply(_plan(system)),
        ConversionRefused,
    )


@task
def convert_outcast_affiliation(backfill_id, **said_by_whoever_enqueued_it):
    """The Outcast Affiliation conversion, as a task."""
    _run_conversion(
        backfill_id,
        Operation.CONVERT_OUTCAST_AFFILIATION,
        "outcast_affiliation",
        **said_by_whoever_enqueued_it,
    )


def _proof_words(plan):
    """What a conversion's page says about its own proof."""
    # Same fallback as Plan.preview — a plan may omit `reaches`.
    reaches = plan.reaches or len(plan.holder_ids) or len(plan.gang_ids)
    holders = len(plan.holder_ids) or reaches
    return {
        "reach_words": (
            f"It reaches {reaches} gang"
            f"{'' if reaches == 1 else 's'}, locks them, and proves "
            f"{len(plan.gang_ids)} of them read the same before committing — "
            "a spread wide enough to hold every shape the system comes in. "
            f"Every reached gang is then reconciled ({holders} of them); "
            "a mismatch unwinds the whole write."
        ),
        "confirm_words": (
            f"Convert {reaches} gang(s)? It writes nothing unless every "
            "page it proves reads the same, and every reached gang still "
            "reconciles."
        ),
        "button_words": "Apply conversion",
        "leaves_behind": "",
    }


def _conversion_view(request, operation, system, task_fn):
    """Preview a conversion (GET), or record a run and enqueue it (POST)."""
    address = reverse(f"admin:maintenance_{operation.value}")
    if request.method == "POST":
        running = running_guard(operation)
        if running is not None:
            messages.warning(request, "That conversion is already running.")
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[running.id])
            )
        plan = _plan(system)
        if plan.nothing_here:
            messages.info(request, "There is nothing to convert.")
            return HttpResponseRedirect(address)
        if not plan.ok:
            messages.error(
                request, "The conversion refuses: " + "; ".join(plan.problems)
            )
            return HttpResponseRedirect(address)
        backfill = Backfill.objects.create(
            operation=operation,
            triggered_by=request.user,
            status=Backfill.Status.RUNNING,
            summary={"preview": list(plan.preview()), "attempts": 0},
        )
        task_fn.enqueue(backfill_id=str(backfill.id))
        messages.success(
            request, "The conversion is running. This page shows what it did."
        )
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )

    plan = _plan(system)
    context = page_context(
        request,
        operation.label,
        plan=plan,
        preview=list(plan.preview()),
        reaches=plan.reaches,
        proven=len(plan.gang_ids),
        apply_url=address,
        recent=Backfill.objects.filter(operation=operation)[:10],
        **_proof_words(plan),
    )
    return render(request, "admin/maintenance/n26/convert.html", context)


def convert_outcast_affiliation_view(request):
    return _conversion_view(
        request,
        Operation.CONVERT_OUTCAST_AFFILIATION,
        "outcast_affiliation",
        convert_outcast_affiliation,
    )


def _who_asked(backfill_id):
    """The operator a run acts as, for the history it writes.

    A repair that hands a gang something writes that down, and an act
    filed against nobody reads as the gang having done it to itself.
    The gang's own acts keep their own actor: what a repair may not do
    is put its name on those.
    """
    backfill = Backfill.objects.filter(pk=backfill_id).first()
    return backfill.triggered_by if backfill else None


@task
def delete_nameless_gang_type(backfill_id, **said_by_whoever_enqueued_it):
    """Retire the nameless gang type and settle what stood on it, once.

    The runner discipline is the lock, the claim, and every ending
    recorded, around work that deletes and rewrites a player's gang —
    which is why the module it calls reads every gang before it touches
    one.
    """
    from n26.library.nameless_gang_type import Refused, apply, find

    _run_recorded(
        backfill_id,
        Operation.DELETE_NAMELESS_GANG_TYPE,
        "Nameless gang type retirement",
        lambda: apply(find(), actor=_who_asked(backfill_id)),
        Refused,
    )


#: The words one deletion page says for itself. Everything else about
#: the page — the plan, the refusals, the apply button, the recent runs —
#: is the same for every deletion, so only these differ.
NAMELESS_WORDS = {
    "noun": "retirement",
    "intro": (
        "This deletes a library row, and rewrites what a player's gang is. "
        "An ingest planned a gang type from a blank Gang cell, so a type "
        "with no name was founded and drew as an empty card on the "
        "create-gang page. A gang founded on it and never played is "
        "deleted with it. A gang somebody has played is not: it is "
        "repointed to the list its models were actually hired from. The "
        "act that founded it is kept and made to name that type, so its "
        "history still opens with its owner creating it, and that type's "
        "built-ins and gang-wide rules arrive — its models, its gear and "
        "its budget are untouched. A gang whose models come from no one "
        "list is left exactly as it stands, and so is the type it names."
    ),
    "nothing_heading": "Nothing to retire",
    "nothing_flash": "There was nothing to retire — every gang type has a name.",
    "nothing_words": "Every gang type in the pack has a name.",
    "refuses_heading": "The retirement refuses",
    "button": "Retire the nameless gang type",
    "confirm": "Retire the nameless gang type? Untouched gangs on it are deleted and played ones are repointed. This cannot be undone.",
}


def _deletion_view(request, operation, find_fn, task_fn, words):
    """Preview a deletion (GET), or record a run and enqueue it.

    Shared by every operation that deletes. The discipline is the
    a running guard, nothing recorded for a run with nothing to do, and
    a refusal shown to whoever asked for it rather than filed as a
    failure. Only ``words`` differs between pages.
    """
    address = reverse(f"admin:maintenance_{operation.value}")
    if request.method == "POST":
        running = running_guard(operation)
        if running is not None:
            messages.warning(request, f"That {words['noun']} is already running.")
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[running.id])
            )
        plan = find_fn()
        if plan.nothing_here:
            messages.info(request, words["nothing_flash"])
            return HttpResponseRedirect(address)
        if not plan.ok:
            messages.error(
                request,
                f"The {words['noun']} refuses: " + "; ".join(plan.problems),
            )
            return HttpResponseRedirect(address)
        backfill = Backfill.objects.create(
            operation=operation,
            triggered_by=request.user,
            status=Backfill.Status.RUNNING,
            summary={"preview": list(plan.preview()), "attempts": 0},
        )
        task_fn.enqueue(backfill_id=str(backfill.id))
        messages.success(
            request, f"The {words['noun']} is running. This page shows what it did."
        )
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )

    plan = find_fn()
    context = page_context(
        request,
        operation.label,
        plan=plan,
        preview=list(plan.preview()),
        words=words,
        apply_url=address,
        recent=Backfill.objects.filter(operation=operation)[:10],
    )
    return render(request, "admin/maintenance/n26/delete.html", context)


def delete_nameless_gang_type_view(request):
    """Preview the deletion (GET), or record a run and enqueue it."""
    from n26.library.nameless_gang_type import find

    return _deletion_view(
        request,
        Operation.DELETE_NAMELESS_GANG_TYPE,
        find,
        delete_nameless_gang_type,
        NAMELESS_WORDS,
    )


@task
def audit_reconcile(backfill_id, **said_by_whoever_enqueued_it):
    """Check every unarchived gang's books against its ledger.

    Reads everything, writes nothing to any gang: a gang whose pinned
    totals or entries disagree with its ledger lands in the record's
    failures with the discrepancy in words. Batched, because the whole
    estate is walked and each gang stands alone.
    """
    from n26.core.models import Gang
    from n26.core.reconcile import assert_reconciled

    run_batched(
        backfill_id,
        operation=Operation.AUDIT_RECONCILE,
        what="Gang books audit",
        items=Gang.objects.filter(archived=False),
        do_one=lambda pk: assert_reconciled(Gang.objects.get(pk=pk)),
        again=lambda: audit_reconcile.enqueue(backfill_id=backfill_id),
    )


def audit_reconcile_view(request):
    """Say what would be checked (GET), or record a run and enqueue it."""
    from n26.core.models import Gang

    operation = Operation.AUDIT_RECONCILE
    address = reverse(f"admin:maintenance_{operation.value}")
    if request.method == "POST":
        running = running_guard(operation)
        if running is not None:
            messages.warning(request, "That audit is already running.")
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[running.id])
            )
        backfill = Backfill.objects.create(
            operation=operation,
            triggered_by=request.user,
            status=Backfill.Status.RUNNING,
            summary={"attempts": 0},
        )
        audit_reconcile.enqueue(backfill_id=str(backfill.id))
        messages.success(
            request, "The audit is running. This page shows what it finds."
        )
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )
    context = page_context(
        request,
        operation.label,
        gangs=Gang.objects.filter(archived=False).count(),
        apply_url=address,
        recent=Backfill.objects.filter(operation=operation)[:10],
    )
    return render(request, "admin/maintenance/n26/audit.html", context)


register_operation(
    MaintenanceOperation(
        operation=Operation.AUDIT_RECONCILE.value,
        name=Operation.AUDIT_RECONCILE.label,
        added=date(2026, 8, 26),
        description=(
            "Walk every unarchived gang and check its pinned totals — "
            "rating, credits, each model's worth — against what its "
            "ledger sums to. Reads everything and changes nothing; a "
            "gang whose books disagree is listed on the run's record "
            "with the discrepancy in words."
        ),
        view=audit_reconcile_view,
    )
)


register_operation(
    MaintenanceOperation(
        operation=Operation.CONVERT_OUTCAST_AFFILIATION.value,
        name=Operation.CONVERT_OUTCAST_AFFILIATION.label,
        added=date(2026, 8, 27),
        description=(
            "Move the Outcast affiliations onto slots and picks: the Hidden "
            "built into the gang type grants an Affiliation slot instead of "
            "offering a choice, Clan House grants a chained Clan House slot, "
            "and every stored choice — live and archived — is re-said as a "
            "pick. What an affiliation does travels with it untouched. "
            "Proves a spread of gangs' pages read the same and every reached "
            "gang still reconciles, or writes nothing."
        ),
        view=convert_outcast_affiliation_view,
        detail_template="admin/maintenance/n26/_convert_detail.html",
    )
)


register_operation(
    MaintenanceOperation(
        operation=Operation.DELETE_NAMELESS_GANG_TYPE.value,
        name=Operation.DELETE_NAMELESS_GANG_TYPE.label,
        added=date(2026, 8, 21),
        description=(
            "Retire the gang type an ingest founded from a blank Gang cell — "
            "the nameless one that drew as an empty card on the create-gang "
            "page. An untouched gang founded on it goes with it; a played "
            "one is repointed to the list its models were hired from, "
            "keeping the act that founded it so its history is not "
            "rewritten. A gang that cannot be read, and the type it "
            "names, are left standing."
        ),
        view=delete_nameless_gang_type_view,
        detail_template="admin/maintenance/n26/_delete_detail.html",
    )
)

#: Declared for the task registry, which reads this from ``n26/core/tasks.py``.
#: The deadline is the longest Pub/Sub allows, because a repair holds one
#: transaction for as long as proving what it touched takes. It is also
#: the request timeout the service is deployed with, and the two belong
#: together: a run outliving its deadline is delivered again while the first
#: copy is still working, and the second — standing down at the lock — answers
#: successfully and acknowledges the message out from under it. Change one and
#: change the other (``--timeout`` in ``cloudbuild.yaml``).
#:
#: The propagation tasks live with the rest of that machinery in
#: ``n26.core.propagation``; their routes are declared here because this
#: module is the edition's one door onto the task framework. The sweep
#: is scheduled work: the framework provisions a Cloud Scheduler job
#: from the declaration, and only there — the local backend fires no
#: schedules, so dev and tests invoke the sweep function directly.
task_routes = [
    TaskRoute(delete_nameless_gang_type, ack_deadline=600, min_retry_delay=60),
    TaskRoute(convert_outcast_affiliation, ack_deadline=600, min_retry_delay=60),
    TaskRoute(propagate_built_ins, ack_deadline=600),
    TaskRoute(sweep_built_in_propagations, schedule="*/5 * * * *"),
    TaskRoute(audit_reconcile),
]


# Run, and what each repaired cannot recur. Registered with no view: they
# leave the menu, and the record of a run still reads as a name rather
# than a bare slug.
register_operation(
    MaintenanceOperation(
        operation=Operation.CONVERT_SPECIALISATION.value,
        name=Operation.CONVERT_SPECIALISATION.label,
    )
)
register_operation(
    MaintenanceOperation(
        operation=Operation.CONVERT_SKILL_TREE.value,
        name=Operation.CONVERT_SKILL_TREE.label,
    )
)
register_operation(
    MaintenanceOperation(
        operation=Operation.RETIRE_GANG_LEGACY_PILOT.value,
        name=Operation.RETIRE_GANG_LEGACY_PILOT.label,
    )
)
register_operation(
    MaintenanceOperation(
        operation=Operation.CONVERT_GANG_LEGACY.value,
        name=Operation.CONVERT_GANG_LEGACY.label,
    )
)
register_operation(
    MaintenanceOperation(
        operation=Operation.CONVERT_ARCHETYPE.value,
        name=Operation.CONVERT_ARCHETYPE.label,
    )
)
register_operation(
    MaintenanceOperation(
        operation=Operation.SWEEP_ARCHIVED.value,
        name=Operation.SWEEP_ARCHIVED.label,
    )
)
register_operation(
    MaintenanceOperation(
        operation=Operation.CLEAR_SPARE_ANSWERS.value,
        name=Operation.CLEAR_SPARE_ANSWERS.label,
    )
)
register_operation(
    MaintenanceOperation(
        operation=Operation.DELETE_RETIRED_KINDS.value,
        name=Operation.DELETE_RETIRED_KINDS.label,
    )
)
register_operation(
    MaintenanceOperation(
        operation=Operation.MERGE_WARGEAR_INTO_WEAPON.value,
        name=Operation.MERGE_WARGEAR_INTO_WEAPON.label,
    )
)
