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

Runs come in three shapes, and each states its own promise. A small
repair (``_run_recorded``) is one transaction, deliberately
all-or-nothing: interrupted, it rolls back whole and can simply be run
again. It is for library-only work and for the conversions, which hold
every gang they touch inside that one transaction; it must finish
inside one delivery, and a run that uses most of that time is flagged
on its record. Work too large for one transaction (``run_batched``)
commits row by row instead, writes how far it got onto the record, and
continues from there after any interruption — which trades the clean
rollback for a requirement that each row's work be idempotent. A repair
that walks players' gangs one at a time, proving each gang's books
before and after its own commit, is the third shape (``run_per_gang``):
the batched runner with the gangs of a plan as its work-list. Every
gang-by-gang repair goes through it, whatever its size looks like on
the day it is written — a gang's proof is many queries, and a plan of a
few hundred gangs is already longer than one delivery may take.
Delivery is at-least-once, so two guards stand between any of these
promises and a second copy running alongside the first: a lock only one
run can hold, and a cap on how many attempts may start without
recording any progress before the record gives up and says so. A
batched run resets that count with every batch it records, so a long
run's many deliveries are never mistaken for a stuck one.

A repair that has been run and cannot recur keeps its slug registered
with no view. It leaves the menu, and the record of the run still reads
as a name rather than a bare slug.
"""

import logging
import traceback
from contextlib import contextmanager
from datetime import date, timedelta

from django.contrib import messages
from django.core.exceptions import (
    MultipleObjectsReturned,
    ObjectDoesNotExist,
    ValidationError,
)
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
    "backfill_built_ins",
    "clear_item_restrictions",
    "delete_empty_affiliations",
    "delete_legacy_affiliation_assignments",
    "delete_nameless_gang_type",
    "open_founding_actions",
    "rehost_gang_picks",
    "repair_doubled_refunds",
    "repoint_champion_picks",
    "seed_journal_content",
    "PlanRefused",
    "run_batched",
    "run_per_gang",
    "task_routes",
]

#: How many times a run may start without recording any progress before
#: the record gives up. A one-transaction run that dies leaves nothing
#: behind and is redelivered; a batched run resets the count every time
#: it records a batch. Either way, without the cap a run that always
#: dies would repeat for ever, each attempt paying its cost again.
MAX_ATTEMPTS = 2

#: How long one delivery may run before the queue redelivers it and the
#: request serving it is cut off. Every one-transaction route below
#: declares this as its acknowledgement deadline, and the tests hold the
#: two together; a batched route may declare less, since it hands back
#: long before. A
#: one-transaction run that takes more than half of it is written up on
#: its record: the next run of the same size, on a slower day, is lost.
ONE_ATTEMPT_DEADLINE = timedelta(seconds=600)

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
    CONVERT_CHAOS_GOD = (
        "n26_convert_chaos_god",
        "n26: the Chaos Gods become picks",
    )
    CONVERT_VARIANT = (
        "n26_convert_variant",
        "n26: the Variants become picks",
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
    REPAIR_DOUBLED_REFUNDS = (
        "n26_repair_doubled_refunds",
        "n26: the second refund a doubled click wrote is dropped",
    )
    BACKFILL_BUILT_INS = (
        "n26_backfill_built_ins",
        "n26: fighters catch up with the built-ins they were hired without",
    )
    DROP_DUPLICATE_GRANTS = (
        "n26_drop_duplicate_grants",
        "n26: the second copy a catch-up granted is dropped",
    )
    REHOST_GANG_PICKS = (
        "n26_rehost_gang_picks",
        "n26: the picks a gang holds move off its models onto the gang",
    )
    REPOINT_CHAMPION_PICKS = (
        "n26_repoint_champion_picks",
        "n26: the Champion picks move onto the Champion archetypes",
    )
    DELETE_EMPTY_AFFILIATIONS = (
        "n26_delete_empty_affiliations",
        "n26: the emptied affiliation rows are deleted",
    )
    OPEN_FOUNDING_ACTIONS = (
        "n26_open_founding_actions",
        "n26: the Found and equip gang action is opened on gangs that never had one",
    )
    DELETE_LEGACY_AFFILIATION_ASSIGNMENTS = (
        "n26_delete_legacy_affiliation_assignments",
        "n26: legacy affiliation assignments are deleted",
    )
    SEED_JOURNAL_CONTENT = (
        "n26_seed_journal_content",
        "n26: the Gang supertype and the Underhive Journal territories are created",
    )
    DELETE_TEST_CONTENT = (
        "n26_delete_test_content",
        "n26: content is deleted along with the test gangs holding it",
    )
    DELETE_FIRING_LINE = (
        "n26_delete_firing_line",
        "n26: a firing line is removed from the fighters that have it and deleted",
    )
    MERGE_INTO = (
        "n26_merge_into",
        "n26: a duplicate row is merged into the row it duplicates",
    )
    CLEAR_ITEM_RESTRICTIONS = (
        "n26_clear_item_restrictions",
        "n26: the restrictions to fighter entries an upload wrote onto listed items are cleared",
    )


#: See the note on locks above: one per operation, never shared.
LOCK_KEYS = {
    Operation.DELETE_NAMELESS_GANG_TYPE: 826_020_606,
    Operation.AUDIT_RECONCILE: 826_020_607,
    Operation.CONVERT_OUTCAST_AFFILIATION: 826_020_608,
    Operation.REPAIR_DOUBLED_REFUNDS: 826_020_609,
    Operation.CONVERT_CHAOS_GOD: 826_020_610,
    Operation.CONVERT_VARIANT: 826_020_611,
    Operation.BACKFILL_BUILT_INS: 826_020_612,
    Operation.DROP_DUPLICATE_GRANTS: 826_020_613,
    Operation.REHOST_GANG_PICKS: 826_020_614,
    Operation.REPOINT_CHAMPION_PICKS: 826_020_615,
    Operation.DELETE_EMPTY_AFFILIATIONS: 826_020_616,
    Operation.OPEN_FOUNDING_ACTIONS: 826_020_617,
    Operation.DELETE_LEGACY_AFFILIATION_ASSIGNMENTS: 826_020_618,
    Operation.SEED_JOURNAL_CONTENT: 826_020_619,
    Operation.DELETE_TEST_CONTENT: 826_020_620,
    Operation.DELETE_FIRING_LINE: 826_020_621,
    Operation.MERGE_INTO: 826_020_622,
    Operation.CLEAR_ITEM_RESTRICTIONS: 826_020_623,
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

    The whole run must fit inside one delivery. How long it took is
    written on the record, and a run that used more than half of
    ``ONE_ATTEMPT_DEADLINE`` gets a warning there too: the work belongs
    on ``run_per_gang`` or ``run_batched`` before it is run again.
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

        started = timezone.now()
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

        took = timezone.now() - started
        summary_patch = {"report": list(report), "seconds": int(took.total_seconds())}
        if took > ONE_ATTEMPT_DEADLINE / 2:
            limit = int(ONE_ATTEMPT_DEADLINE.total_seconds())
            summary_patch["warning"] = (
                f"This run took {int(took.total_seconds())} of the {limit} "
                "seconds one delivery may take before the queue redelivers "
                "it and the request serving it is cut off. Move the work "
                "onto run_per_gang or run_batched before running it again."
            )
            logger.warning("%s: %s", what, summary_patch["warning"])
        _write(backfill_id, status=Backfill.Status.DONE, summary_patch=summary_patch)


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
    refusals=(),
):
    """Work through ``items`` one at a time, each on its own commit,
    remembering how far it got.

    ``_run_recorded`` is for work that fits inside one delivery and one
    transaction; this is the shape for everything else. ``items`` is a
    queryset with a unique primary key — ordered here, because the
    cursor is only sound over a total order — and it must be stable: a
    queryset that stops matching rows as they are settled moves the
    finish line while the cursor chases it. It may instead be a callable
    that reads the work-list under the run's lock, once per delivery;
    one that raises a ``refusals`` exception ends the record FAILED in
    the refusal's own words, and one that returns ``None`` has written
    the ending itself and there is nothing to walk — a record it left
    RUNNING is ended FAILED rather than left waiting. ``do_one(pk)``
    settles one row completely, committing its own writes and leaving
    nothing behind when it fails. It must be idempotent: a crashed
    attempt replays at most one batch, and a rerun is a fresh record
    that walks every row again, settling only what the earlier run
    missed. A string it returns is a line of the record's report.

    Progress lands on the record after every batch — how many rows are
    settled, of how many, the failures so far, the report so far, and
    the cursor the next attempt continues from. That write doubles as
    the cancel check: an
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
            work_list = items() if callable(items) else items
            if work_list is not None:
                continued = _work_through(
                    backfill_id, what, work_list, do_one, batch_size, budget
                )
            elif Backfill.objects.filter(
                pk=backfill_id, status=Backfill.Status.RUNNING
            ).exists():
                # Nothing to walk and no ending written: left alone, the
                # record would say RUNNING for ever with no delivery
                # coming to finish it.
                _write(
                    backfill_id,
                    status=Backfill.Status.FAILED,
                    error=(
                        "The work-list reported nothing to walk but wrote no "
                        "ending onto the record."
                    ),
                )
        except refusals as refused:
            # Refused before any row was walked, so the record ends in
            # the refusal's own words with nothing to unwind.
            _write(backfill_id, status=Backfill.Status.FAILED, error=str(refused))
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
    report = list(backfill.summary.get("report", []))
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
                "report": report,
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
                line = do_one(pk)
            except Exception as broke:  # noqa: BLE001 — one row never starves the rest
                logger.exception("%s could not settle %s", what, pk)
                failures[str(pk)] = str(broke)
            else:
                settled += 1
                failures.pop(str(pk), None)
                if isinstance(line, str):
                    report.append(line)
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


class PlanRefused(Exception):
    """A gang-by-gang plan read under the lock names problems."""


#: How many gangs a per-gang run settles between progress writes. A
#: gang's proof is many queries and the budget is only consulted after
#: a whole batch, so the batch is kept small: progress lands often, a
#: crash replays little, and a batch cannot on its own outlast the
#: delivery.
PER_GANG_BATCH_SIZE = 10


def run_per_gang(
    backfill_id,
    *,
    operation,
    what,
    find,
    apply_one,
    again,
    batch_size=PER_GANG_BATCH_SIZE,
    budget=BATCH_BUDGET,
    refusals=(),
):
    """Run a repair that works through players' gangs one at a time.

    The shape every such repair shares: ``find()`` reads a plan whose
    ``gangs`` name each gang to visit, whose ``problems`` refuse the
    whole run, and whose ``nothing_here`` says there is no work;
    ``apply_one(gang_id)`` reads that one gang's part of the plan again,
    settles the gang inside its own transaction, and returns the line
    the report carries for it. Proving one gang's books is many
    queries, so a plan of a few hundred gangs already outlasts one
    delivery: the gangs go through ``run_batched``, which commits gang
    by gang, records how far it got, and hands the rest to a fresh
    delivery when its budget is spent.

    The plan is read once, under the lock, on the first delivery. Its
    gang ids land on the record, and every later delivery walks the
    same list — a plan re-read mid-run could add gangs behind the cursor
    and never visit them. What each gang holds is read again when it is
    visited, because deliveries may be minutes apart: ``apply_one``
    settles what the gang holds now, and a gang that no longer passes
    the plan's checks is left alone and named in the report. The
    preview stays in ``summary["preview"]``, where the view put it, so
    the record's report holds only what was done.

    ``refusals`` are the exceptions a caller's ``find`` may raise to
    refuse the run in its own words; a plan naming ``problems`` refuses
    without raising.
    """
    from n26.core.models import Gang

    def gangs():
        backfill = Backfill.objects.get(pk=backfill_id)
        ids = backfill.summary.get("gang_ids")
        if ids is None:
            plan = find()
            if plan.problems:
                raise PlanRefused(
                    f"{what} cannot run: " + "; ".join(plan.problems) + "."
                )
            if plan.nothing_here:
                _write(
                    backfill_id,
                    status=Backfill.Status.DONE,
                    summary_patch={"report": list(plan.preview())},
                )
                return None
            ids = [str(gang_id) for gang_id, *_ in plan.gangs]
            _write(backfill_id, summary_patch={"gang_ids": ids})
        return Gang.objects.filter(pk__in=ids)

    run_batched(
        backfill_id,
        operation=operation,
        what=what,
        items=gangs,
        do_one=apply_one,
        again=again,
        batch_size=batch_size,
        budget=budget,
        refusals=(PlanRefused, *refusals),
    )


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


@task
def convert_chaos_god(backfill_id, **said_by_whoever_enqueued_it):
    """The Chaos God conversion, as a task."""
    _run_conversion(
        backfill_id,
        Operation.CONVERT_CHAOS_GOD,
        "chaos_god",
        **said_by_whoever_enqueued_it,
    )


@task
def convert_variant(backfill_id, **said_by_whoever_enqueued_it):
    """The Variant conversion, as a task."""
    _run_conversion(
        backfill_id,
        Operation.CONVERT_VARIANT,
        "variant",
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
                request, "The conversion cannot run: " + "; ".join(plan.problems)
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


def convert_chaos_god_view(request):
    return _conversion_view(
        request,
        Operation.CONVERT_CHAOS_GOD,
        "chaos_god",
        convert_chaos_god,
    )


def convert_variant_view(request):
    return _conversion_view(
        request,
        Operation.CONVERT_VARIANT,
        "variant",
        convert_variant,
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
                f"The {words['noun']} cannot run: " + "; ".join(plan.problems) + ".",
            )
            return HttpResponseRedirect(address)
        # A plan that keeps more than its lines — the rows it named, so
        # the run can hold its own reading against what was approved —
        # writes that onto the record beside the preview.
        recorded = getattr(plan, "recorded", dict)()
        backfill = Backfill.objects.create(
            operation=operation,
            triggered_by=request.user,
            status=Backfill.Status.RUNNING,
            summary={"preview": list(plan.preview()), "attempts": 0, **recorded},
        )
        task_fn.enqueue(backfill_id=str(backfill.id))
        messages.success(
            request, f"The {words['noun']} is running. The result will appear below."
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
def repair_doubled_refunds(backfill_id, **said_by_whoever_enqueued_it):
    """Drop the surplus refund, sale and removal legs a doubled click
    wrote, and prove every affected gang's books whole, once.

    One gang's worth of events in one transaction: a gang that still
    fails to reconcile unwinds its own repair and the rest go on.
    """
    from n26.core.doubled_refunds import apply_one, find

    run_per_gang(
        backfill_id,
        operation=Operation.REPAIR_DOUBLED_REFUNDS,
        what="Doubled refund repair",
        find=find,
        apply_one=apply_one,
        again=lambda: repair_doubled_refunds.enqueue(backfill_id=backfill_id),
    )


DOUBLED_WORDS = {
    "noun": "repair",
    "intro": (
        "This deletes ledger events from players' gangs. A refund, sale or "
        "removal whose click reached the server twice used to be written "
        "twice: the line was archived once, but a second refunded or sold "
        "leg — and, for a fighter, a second removed leg for each thing "
        "they brought — went into the books, so the entry's events fold "
        "to minus what it was worth while its pins say zero, and the gang "
        "holds credits it was never owed. Every leg after the first of its "
        "kind on a line is dropped, along with the removal legs written in "
        "the same act, and each gang's pinned numbers are written again "
        "from what remains. A line still on the roster with a doubled leg "
        "is refused rather than touched."
    ),
    "nothing_heading": "Nothing to drop",
    "nothing_flash": "There was nothing to drop — no line carries a second refund or sale.",
    "nothing_words": "No line in any gang carries a second refund or sale.",
    "refuses_heading": "The repair refuses",
    "button": "Drop the surplus legs",
    "confirm": "Drop every surplus refund, sale and removal leg and rewrite the affected gangs' pinned numbers? This cannot be undone.",
}


def repair_doubled_refunds_view(request):
    """Preview the repair (GET), or record a run and enqueue it."""
    from n26.core.doubled_refunds import find

    return _deletion_view(
        request,
        Operation.REPAIR_DOUBLED_REFUNDS,
        find,
        repair_doubled_refunds,
        DOUBLED_WORDS,
    )


@task
def rehost_gang_picks(backfill_id, **said_by_whoever_enqueued_it):
    """Move every live pick a gang holds off the model it was written
    on and onto the gang, and prove every affected gang's books whole,
    once.

    A gang's worth of picks in one transaction: a gang that fails to
    reconcile unwinds its own move and the rest go on.
    """
    from n26.core.rehost_picks import apply_one, find

    run_per_gang(
        backfill_id,
        operation=Operation.REHOST_GANG_PICKS,
        what="Gang pick rehosting",
        find=find,
        apply_one=apply_one,
        again=lambda: rehost_gang_picks.enqueue(backfill_id=backfill_id),
    )


@task
def delete_empty_affiliations(backfill_id, **said_by_whoever_enqueued_it):
    """Delete emptied Affiliation library rows, and record it.

    The runner discipline of a conversion around work that deletes
    library rows only. Nothing a player holds is touched, which is why
    what it proves is that no page moves at all.
    """
    from n26.library.empty_affiliations import Refused, apply, find

    _run_recorded(
        backfill_id,
        Operation.DELETE_EMPTY_AFFILIATIONS,
        "Empty Affiliation deletion",
        lambda: apply(find()),
        Refused,
    )


@task
def delete_legacy_affiliation_assignments(backfill_id, **said_by_whoever_enqueued_it):
    """Delete the two measured player-data leftovers of the conversions."""
    from n26.core.legacy_affiliation_assignments import apply_one, find

    run_per_gang(
        backfill_id,
        operation=Operation.DELETE_LEGACY_AFFILIATION_ASSIGNMENTS,
        what="Legacy affiliation assignment deletion",
        find=find,
        apply_one=apply_one,
        again=lambda: delete_legacy_affiliation_assignments.enqueue(
            backfill_id=backfill_id
        ),
    )


LEGACY_AFFILIATION_ASSIGNMENT_WORDS = {
    "noun": "deletion",
    "intro": (
        "This deletes the player assignments left by the affiliation conversions. "
        "Only archived None assignments replaced by an optional Variant slot and "
        "live spare assignments whose converted affiliation pick has since changed "
        "can be deleted. Every assignment must have a zero-value ledger entry, only "
        "the expected zero-value history events, and no dependent data. Its ledger "
        "entry and history events are deleted with it. Each affected gang must "
        "reconcile. An archived assignment cannot change a page; a live spare may "
        "remove only its own obsolete line. Otherwise the gang is left alone."
    ),
    "nothing_heading": "Nothing to delete",
    "nothing_flash": "No legacy affiliation assignments remain.",
    "nothing_words": "No legacy affiliation assignments remain.",
    "refuses_heading": "The deletion cannot run",
    "button": "Delete the legacy assignments",
    "confirm": (
        "Delete these assignments, their ledger entries and their history events? "
        "This cannot be undone."
    ),
}


def delete_legacy_affiliation_assignments_view(request):
    """Preview the player-data deletion (GET), or record and enqueue it."""
    from n26.core.legacy_affiliation_assignments import find

    return _deletion_view(
        request,
        Operation.DELETE_LEGACY_AFFILIATION_ASSIGNMENTS,
        find,
        delete_legacy_affiliation_assignments,
        LEGACY_AFFILIATION_ASSIGNMENT_WORDS,
    )


REHOST_WORDS = {
    "noun": "move",
    "intro": (
        "This moves picks between hosts in players' gangs. A slot sets "
        "where its pick lands: on the model that carries it, or on the "
        "gang, where the model is asked and the gang holds the pick. A "
        "pick is hosted where the slot pointed when it was made, so a "
        "Leader's Archetype pick made while the slot pointed at the model "
        "sits on the Leader, and changing the slot moves nothing already "
        "written. Every live pick whose slot points at the gang and which "
        "sits on a model is moved onto that model's gang. It still names the assignment "
        "that asked and the slot it settles, so the card that asked still "
        "reads it as chosen, and it still goes when that model does. "
        "Anything it caused stays where it is. An archived pick is "
        "counted and left alone. No money moves; every gang is proved to "
        "reconcile."
    ),
    "nothing_heading": "Nothing to move",
    "nothing_flash": (
        "There was nothing to move — every live pick of a slot that points "
        "at the gang sits on the gang."
    ),
    "nothing_words": "Every live pick of a slot that points at the gang sits on the gang.",
    "refuses_heading": "The move cannot run",
    "button": "Move the picks onto their gangs",
    "confirm": (
        "Move every live pick of a slot that points at the gang off its "
        "model and onto the gang? This cannot be undone."
    ),
}


def rehost_gang_picks_view(request):
    """Preview the move (GET), or record a run and enqueue it."""
    from n26.core.rehost_picks import find

    return _deletion_view(
        request,
        Operation.REHOST_GANG_PICKS,
        find,
        rehost_gang_picks,
        REHOST_WORDS,
    )


EMPTY_AFFILIATION_WORDS = {
    "noun": "deletion",
    "intro": (
        "This deletes old library rows without changing player data: "
        "emptied affiliation rows, their menus, unused affiliation "
        "offers, and unused hidden rows that grant slots. The rows "
        "selected for deletion are listed below, together with the rows "
        "that will remain and the reason for keeping them. The slot types "
        "named Affiliation, Clan House, Chaos God and Variant remain, "
        "along with their pickables, picklists and slots. Those rows are "
        "the new system. The deletion is rolled back if it would change "
        "any checked gang page. The deletion cannot run while any "
        "assignment still names an affiliation or anyone still holds an "
        "affiliation offer. Run the legacy affiliation assignment deletion first."
    ),
    "nothing_heading": "Nothing to delete",
    "nothing_flash": "There was nothing selected for deletion.",
    "nothing_words": "No Affiliation leftovers are selected for deletion.",
    "refuses_heading": "The deletion cannot run",
    "button": "Delete the emptied affiliation rows",
    "confirm": "Delete these library rows? This cannot be undone.",
}


def delete_empty_affiliations_view(request):
    """Preview the deletion (GET), or record a run and enqueue it."""
    from n26.library.empty_affiliations import find

    return _deletion_view(
        request,
        Operation.DELETE_EMPTY_AFFILIATIONS,
        find,
        delete_empty_affiliations,
        EMPTY_AFFILIATION_WORDS,
    )


@task
def repoint_champion_picks(backfill_id, **said_by_whoever_enqueued_it):
    """Point every live pick at the pickable of its own name on its
    slot's picklist, and prove every affected gang's books whole, once.

    A gang's worth of picks in one transaction: a gang that fails to
    reconcile unwinds its own move and the rest go on.
    """
    from n26.core.repoint_champion_picks import apply_one, find

    run_per_gang(
        backfill_id,
        operation=Operation.REPOINT_CHAMPION_PICKS,
        what="Champion pick repointing",
        find=find,
        apply_one=apply_one,
        again=lambda: repoint_champion_picks.enqueue(backfill_id=backfill_id),
    )


REPOINT_WORDS = {
    "noun": "move",
    "intro": (
        "This moves picks between pickables in players' gangs. A slot "
        "draws from a picklist, and pointing the slot at a different list "
        "moves nothing already picked: the pick goes on naming what was "
        "picked, which the list the slot now reads may not hold at all. "
        "A Champion's Archetype and the gang's were picked from one list, "
        "so every Champion's pick names the gang's archetype and reads "
        "the gang's skill sets rather than the Champion's. Every live "
        "pick of a slot that puts the pick on the model that made it, "
        "where the slot's picklist does not hold what was picked, is "
        "moved onto the pickable of the same name on that list. Nothing "
        "else changes: the pick still names the assignment that asked and "
        "the slot it settles, so the card still reads it as chosen, and "
        "it still goes when that model does. An archived pick is counted "
        "and left alone. No money moves; every gang is proved to "
        "reconcile."
    ),
    "nothing_heading": "Nothing to move",
    "nothing_flash": (
        "There was nothing to move — every live pick names something its "
        "slot's picklist offers."
    ),
    "nothing_words": "Every live pick names something its slot's picklist offers.",
    "refuses_heading": "The move cannot run",
    "button": "Move the picks onto their slot's own pickables",
    "confirm": (
        "Move every live pick onto the pickable of the same name on its "
        "slot's picklist? This cannot be undone."
    ),
}


def repoint_champion_picks_view(request):
    """Preview the move (GET), or record a run and enqueue it."""
    from n26.core.repoint_champion_picks import find

    return _deletion_view(
        request,
        Operation.REPOINT_CHAMPION_PICKS,
        find,
        repoint_champion_picks,
        REPOINT_WORDS,
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


@task
def backfill_built_ins(backfill_id, **said_by_whoever_enqueued_it):
    """Tag every legacy built-in grant with its provenance and catch
    every live carrier up with its sets, one gang at a time.

    Archived gangs are walked too. An archived gang is one its owner
    may bring back, and one left untagged comes back holding grants
    nothing can account for — while the live propagation pass, which
    only ever visits gangs in play, would never reach it.

    Batched, because the whole estate is walked and each gang is its
    own operation, committing on its own. What each gang came to is
    added to the record's totals as it lands, so a run read part-way
    still says what it has done so far.
    """
    from n26.core.backfill_built_ins import catch_up
    from n26.core.models import Gang

    record = Backfill.objects.get(pk=backfill_id)
    totals = dict(record.summary.get("totals", {}))
    held_another_way = list(record.summary.get("held_another_way", []))

    def do_one(pk):
        outcome = catch_up(pk)
        for key, count in outcome.counts().items():
            totals[key] = int(totals.get(key, 0)) + count
        held_another_way.extend(outcome.held_another_way)
        _write(
            backfill_id,
            summary_patch={"totals": totals, "held_another_way": held_another_way},
        )

    run_batched(
        backfill_id,
        operation=Operation.BACKFILL_BUILT_INS,
        what="Built-ins backfill",
        items=Gang.objects.all(),
        do_one=do_one,
        again=lambda: backfill_built_ins.enqueue(backfill_id=backfill_id),
    )


def backfill_built_ins_view(request):
    """Say what would be walked (GET), or record a run and enqueue it.

    The preview is deliberately cheap — one count of the grants still
    without provenance, by kind, and the number of gangs — because the
    exact grant count is only known by walking every carrier, which is
    the run's job, not the page's.
    """
    from n26.core.backfill_built_ins import TAGGABLE_KINDS, legacy_grants_by_kind
    from n26.core.models import Gang

    operation = Operation.BACKFILL_BUILT_INS
    address = reverse(f"admin:maintenance_{operation.value}")
    if request.method == "POST":
        running = running_guard(operation)
        if running is not None:
            messages.warning(request, "That backfill is already running.")
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[running.id])
            )
        backfill = Backfill.objects.create(
            operation=operation,
            triggered_by=request.user,
            status=Backfill.Status.RUNNING,
            summary={"attempts": 0},
        )
        backfill_built_ins.enqueue(backfill_id=str(backfill.id))
        messages.success(
            request, "The backfill is running. This page shows what it does."
        )
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )
    by_kind = legacy_grants_by_kind()
    context = page_context(
        request,
        operation.label,
        gangs=Gang.objects.count(),
        legacy=[
            {
                "kind": kind.replace("_", " "),
                "count": count,
                "taggable": kind in TAGGABLE_KINDS,
            }
            for kind, count in by_kind.items()
        ],
        legacy_total=sum(
            count for kind, count in by_kind.items() if kind in TAGGABLE_KINDS
        ),
        apply_url=address,
        recent=Backfill.objects.filter(operation=operation)[:10],
    )
    return render(request, "admin/maintenance/n26/backfill_built_ins.html", context)


register_operation(
    MaintenanceOperation(
        operation=Operation.BACKFILL_BUILT_INS.value,
        name=Operation.BACKFILL_BUILT_INS.label,
        added=date(2026, 8, 29),
        description=(
            "Walk every gang, archived ones included. Each built-in grant "
            "written before "
            "provenance was recorded is tagged with the set member it came "
            "from and the carrier it came for; then every live carrier — "
            "each model's membership, the gang's founding, a bought mount — "
            "catches up with what its sets say it comes with, so a member "
            "added after the hire arrives now, told in the history as "
            "caught up. A model that already holds a member's thing some "
            "other way is skipped and named on the record. Tagging moves no "
            "money; every gang is proved to reconcile."
        ),
        view=backfill_built_ins_view,
        detail_template="admin/maintenance/n26/_backfill_built_ins_detail.html",
    )
)


@task
def drop_duplicate_grants(backfill_id, **said_by_whoever_enqueued_it):
    """Drop every duplicate a catch-up pass granted, one gang at a time.

    Batched, because the whole estate is walked and each gang is its own
    transaction, proved to reconcile before it commits.
    """
    from n26.core.duplicate_grants import de_duplicate
    from n26.core.models import Gang

    record = Backfill.objects.get(pk=backfill_id)
    totals = dict(record.summary.get("totals", {}))
    kept_a_tally = list(record.summary.get("kept_a_tally", []))
    # A run may be confined to one model, which is how the repair is
    # tried and read back before the whole estate is walked. Its gang is
    # recorded beside it so the walk is one row long.
    only_model = record.summary.get("only_model")
    only_gang = record.summary.get("only_gang")

    def do_one(pk):
        outcome = de_duplicate(pk, only_miniature_id=only_model)
        for key, count in outcome.counts().items():
            totals[key] = int(totals.get(key, 0)) + count
        kept_a_tally.extend(outcome.kept_a_tally)
        _write(
            backfill_id,
            summary_patch={"totals": totals, "kept_a_tally": kept_a_tally},
        )

    run_batched(
        backfill_id,
        operation=Operation.DROP_DUPLICATE_GRANTS,
        what="Duplicate grants",
        items=Gang.objects.filter(pk=only_gang) if only_gang else Gang.objects.all(),
        do_one=do_one,
        again=lambda: drop_duplicate_grants.enqueue(backfill_id=backfill_id),
    )


def drop_duplicate_grants_view(request):
    """Say what would be dropped (GET), or record a run and enqueue it."""
    from n26.core.duplicate_grants import (
        duplicate_grants_by_kind,
        what_one_model_carries,
    )
    from n26.core.models import Gang, Miniature

    operation = Operation.DROP_DUPLICATE_GRANTS
    address = reverse(f"admin:maintenance_{operation.value}")
    # One model may be named, by id, to try the repair on before the
    # estate is walked. A GET reads what would happen to it; the POST
    # from the same page runs that model alone.
    asked = (request.POST.get("model") or request.GET.get("model") or "").strip()
    one = None
    if asked:
        try:
            one = Miniature.objects.filter(pk=asked).first()
        except ValidationError, ValueError, TypeError:
            # Anything that is not an id at all: the field refuses it
            # while the query is being built, before any row is read.
            one = None
        if one is not None and one.membership_id is None:
            # Nothing to walk: a model with no membership sits in no gang.
            one = None
        if one is None:
            messages.warning(request, "No model in a gang has that id.")
    if request.method == "POST":
        running = running_guard(operation)
        if running is not None:
            messages.warning(request, "That repair is already running.")
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[running.id])
            )
        if asked and one is None:
            return HttpResponseRedirect(address)
        summary = {"attempts": 0}
        if one is not None:
            summary["only_model"] = str(one.pk)
            summary["only_gang"] = str(one.membership.gang_root_id)
            summary["only_model_name"] = one.name
        backfill = Backfill.objects.create(
            operation=operation,
            triggered_by=request.user,
            status=Backfill.Status.RUNNING,
            summary=summary,
        )
        drop_duplicate_grants.enqueue(backfill_id=str(backfill.id))
        messages.success(
            request, "The repair is running. This page shows what it does."
        )
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )
    by_kind = duplicate_grants_by_kind()
    context = page_context(
        request,
        operation.label,
        asked=asked,
        one=one,
        one_carries=what_one_model_carries(one) if one is not None else [],
        gangs=Gang.objects.count(),
        duplicates=[
            {"kind": kind.replace("_", " "), "count": count}
            for kind, count in sorted(by_kind.items())
        ],
        duplicate_total=sum(by_kind.values()),
        apply_url=address,
        recent=Backfill.objects.filter(operation=operation)[:10],
    )
    return render(request, "admin/maintenance/n26/drop_duplicate_grants.html", context)


def gangs_without_a_founding_action():
    """The unarchived gangs that have never had a founding action.

    Never, rather than not at this moment: an owner who has completed
    the act is done with it, and opening a second would put them back
    where they started. So a completed one counts as much as an open
    one.
    """
    from n26.core.models import Action, Gang

    return Gang.objects.filter(archived=False).exclude(
        actions__kind=Action.Kind.FOUNDING
    )


@task
def open_founding_actions(backfill_id, **said_by_whoever_enqueued_it):
    """Open a Found and equip gang action on every unarchived gang that
    has never had one, a gang at a time.

    A gang founded before the action existed has none, so nothing on
    its page says the act is still to be completed and its owner would
    have to start one by hand. Each is opened through the operation a
    founding uses, so the same event is written and the gang's history
    reads as it would have.

    Nobody is named as having done it, as the built-ins backfill does
    the same way: the act is the estate catching up, not a person, and
    filing it against whoever clicked in the admin would put a staff
    username in a stranger's gang history.

    The walk is every unarchived gang rather than only the ones that
    qualify: ``run_batched`` needs a set that does not shrink as it is
    worked through, and a gang that already has one is stepped past
    where it stands. It is also why a rerun does nothing but walk.

    Batched, because the whole estate is walked and each gang commits on
    its own. What the run has come to is added to the record as each
    gang lands, so a record read part-way says how far it has got.
    """
    from n26.core.models import Action, Gang
    from n26.core.operations import Refusal, operation

    record = Backfill.objects.get(pk=backfill_id)
    totals = dict(record.summary.get("totals", {}))

    def add_to_totals(key):
        totals[key] = int(totals.get(key, 0)) + 1
        _write(backfill_id, summary_patch={"totals": totals})

    def do_one(pk):
        gang = Gang.objects.filter(pk=pk, archived=False).first()
        if gang is None:
            # Archived, or gone, since the walk was counted. Either way
            # it is not one of the gangs this run is for.
            return
        if Action.objects.filter(gang=gang, kind=Action.Kind.FOUNDING).exists():
            add_to_totals("already_had_one")
            return
        try:
            with operation(gang, actor=None) as op:
                op.open_action(Action.Kind.FOUNDING)
        except Refusal:
            # The check above runs before the gang's line is held, so an
            # owner can start the act in between and hold it by the time
            # this gets the line. Refusing is that guard working: the
            # gang has what this run came to give it.
            add_to_totals("already_had_one")
            return
        add_to_totals("opened")

    run_batched(
        backfill_id,
        operation=Operation.OPEN_FOUNDING_ACTIONS,
        what="Founding actions",
        items=Gang.objects.filter(archived=False),
        do_one=do_one,
        again=lambda: open_founding_actions.enqueue(backfill_id=backfill_id),
    )


def _preview_words(eligible, walked):
    """What the run set out to do, in sentences the record keeps.

    The second says what the run's own total counts, because the two
    figures differ: every unarchived gang is walked and only some of
    them get anything, so a run reporting more done than there were
    gangs to change would otherwise read as a mistake.
    """
    return [
        f"{eligible} of {walked} unarchived gang"
        f"{'' if walked == 1 else 's'} "
        f"{'has' if eligible == 1 else 'have'} never had a Found and "
        "equip gang action.",
        "Every unarchived gang is walked, so this run's total counts "
        "gangs walked, not gangs changed.",
    ]


def open_founding_actions_view(request):
    """Say how many gangs would get one (GET), or record a run and
    enqueue it."""
    from n26.core.models import Gang

    operation = Operation.OPEN_FOUNDING_ACTIONS
    address = reverse(f"admin:maintenance_{operation.value}")
    if request.method == "POST":
        running = running_guard(operation)
        if running is not None:
            messages.warning(request, "That backfill is already running.")
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[running.id])
            )
        eligible = gangs_without_a_founding_action().count()
        if not eligible:
            messages.info(
                request,
                "There is nothing to open — every unarchived gang already "
                "has the Found and equip gang action.",
            )
            return HttpResponseRedirect(address)
        walked = Gang.objects.filter(archived=False).count()
        backfill = Backfill.objects.create(
            operation=operation,
            triggered_by=request.user,
            status=Backfill.Status.RUNNING,
            summary={"preview": _preview_words(eligible, walked), "attempts": 0},
        )
        open_founding_actions.enqueue(backfill_id=str(backfill.id))
        messages.success(
            request, "The backfill is running. This page shows what it does."
        )
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )
    context = page_context(
        request,
        operation.label,
        gangs=Gang.objects.filter(archived=False).count(),
        eligible=gangs_without_a_founding_action().count(),
        apply_url=address,
        recent=Backfill.objects.filter(operation=operation)[:10],
    )
    return render(request, "admin/maintenance/n26/open_founding_actions.html", context)


register_operation(
    MaintenanceOperation(
        operation=Operation.OPEN_FOUNDING_ACTIONS.value,
        name=Operation.OPEN_FOUNDING_ACTIONS.label,
        added=date(2026, 9, 4),
        description=(
            "Open the Found and equip gang action on every unarchived "
            "gang that has never had one. A gang founded before the "
            "action existed has none, so its page has nothing for the "
            "owner to complete. Each of those gangs gets the action a "
            "gang founded today has, and the same entry in its history. "
            "A gang that already has one, open or completed, is skipped, "
            "so running this again changes nothing. Archived gangs are "
            "left alone. No money moves."
        ),
        view=open_founding_actions_view,
        detail_template="admin/maintenance/n26/_open_founding_actions_detail.html",
    )
)


register_operation(
    MaintenanceOperation(
        operation=Operation.REHOST_GANG_PICKS.value,
        name=Operation.REHOST_GANG_PICKS.label,
        added=date(2026, 9, 3),
        description=(
            "A slot sets where its pick lands: on the model that carries "
            "it, or on the gang. A Leader's Archetype pick made while the "
            "slot pointed at the model sits on the Leader, and changing "
            "the slot moves nothing already written; this moves those "
            "picks onto their gangs. Each still names what asked it and the slot it "
            "settles, so the Leader's card still reads it as chosen, and "
            "it still goes when the Leader does. No money moves; every "
            "gang is proved to reconcile."
        ),
        view=rehost_gang_picks_view,
        detail_template="admin/maintenance/n26/_per_gang_detail.html",
    )
)


register_operation(
    MaintenanceOperation(
        operation=Operation.REPOINT_CHAMPION_PICKS.value,
        name=Operation.REPOINT_CHAMPION_PICKS.label,
        added=date(2026, 9, 4),
        description=(
            "A slot draws from a picklist, and pointing the slot at a "
            "different list moves nothing already picked. A Champion's "
            "Archetype and the gang's were picked from one list, so a "
            "Champion's pick names the gang's archetype and reads the "
            "gang's skill sets rather than the Champion's. This points "
            "each such pick at the pickable of the same name on its "
            "slot's own picklist. Each still names what asked it and the "
            "slot it settles, so the card still reads it as chosen. No "
            "money moves; every gang is proved to reconcile."
        ),
        view=repoint_champion_picks_view,
        detail_template="admin/maintenance/n26/_per_gang_detail.html",
    )
)


register_operation(
    MaintenanceOperation(
        operation=Operation.DROP_DUPLICATE_GRANTS.value,
        name=Operation.DROP_DUPLICATE_GRANTS.label,
        added=date(2026, 8, 31),
        description=(
            "A catch-up pass tells whether a model already holds a built-in "
            "by the provenance on its copies. Grants written before "
            "provenance existed carry none, so a pass granted a second copy "
            "of what the model plainly already had. This drops the pass's "
            "copy and gives the owner's copy the provenance it should have "
            "had, so the member stays accounted for and no pass grants it "
            "again. What the dropped copy caused goes with it. A copy "
            "somebody has been counting on is left alone and named on the "
            "record. No money moves; every gang is proved to reconcile."
        ),
        view=drop_duplicate_grants_view,
        detail_template="admin/maintenance/n26/_drop_duplicate_grants_detail.html",
    )
)


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
        operation=Operation.CONVERT_CHAOS_GOD.value,
        name=Operation.CONVERT_CHAOS_GOD.label,
        added=date(2026, 8, 28),
        description=(
            "Move the Chaos God choice onto slots and picks, both doors: "
            "the Hidden built into Chaos Helot Cult and the Chaos Corrupted "
            "affiliation each grant a Chaos God slot instead of offering a "
            "choice, and every stored god pick — live and archived — is "
            "re-said as a pick. Chaos Corrupted stays an Affiliation. "
            "Proves a spread of gangs' pages read the same and every reached "
            "gang still reconciles, or writes nothing."
        ),
        view=convert_chaos_god_view,
        detail_template="admin/maintenance/n26/_convert_detail.html",
    )
)


register_operation(
    MaintenanceOperation(
        operation=Operation.CONVERT_VARIANT.value,
        name=Operation.CONVERT_VARIANT.label,
        added=date(2026, 8, 28),
        description=(
            "Move the Variants onto slots and picks: the shared offer on the "
            "house gang types becomes a grant of an optional Variant slot, "
            "the three corruptions become pickables (Chaos Corrupted keeps "
            "its Chaos God grant), every stored corruption pick is re-said "
            "as a pick, and every stored None is archived so the question "
            "reads unanswered. Cards that print the word None today will "
            "print nothing after — an optional slot with nothing chosen "
            "already says that. Proves a spread of gangs' pages read the "
            "same and every reached gang still reconciles, or writes nothing."
        ),
        view=convert_variant_view,
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

register_operation(
    MaintenanceOperation(
        operation=Operation.REPAIR_DOUBLED_REFUNDS.value,
        name=Operation.REPAIR_DOUBLED_REFUNDS.label,
        added=date(2026, 8, 28),
        description=(
            "Drop the second refunded or sold leg a doubled click wrote onto "
            "a line, and the removal legs written in the same act, then "
            "write each affected gang's pinned numbers again. The books "
            "audit reports these gangs as entries pinned 0 whose events "
            "fold to minus what the thing was worth."
        ),
        view=repair_doubled_refunds_view,
        detail_template="admin/maintenance/n26/_per_gang_detail.html",
    )
)

register_operation(
    MaintenanceOperation(
        operation=Operation.DELETE_LEGACY_AFFILIATION_ASSIGNMENTS.value,
        name=Operation.DELETE_LEGACY_AFFILIATION_ASSIGNMENTS.label,
        added=date(2026, 9, 4),
        description=(
            "Delete archived None assignments and live spare affiliation assignments "
            "left by the conversions. Each assignment must have the expected "
            "zero-value ledger entry and history events. Those records are deleted too, "
            "and every affected gang must reconcile. Only a live spare's own "
            "obsolete line may disappear from its gang sheet."
        ),
        view=delete_legacy_affiliation_assignments_view,
        detail_template="admin/maintenance/n26/_per_gang_detail.html",
    )
)

register_operation(
    MaintenanceOperation(
        operation=Operation.DELETE_EMPTY_AFFILIATIONS.value,
        name=Operation.DELETE_EMPTY_AFFILIATIONS.label,
        added=date(2026, 8, 29),
        description=(
            "Delete the affiliation library rows left after the "
            "conversions: the emptied kind rows, their menus, unused "
            "affiliation offers, and unused hidden rows that grant slots. "
            "The deletion is rolled back if it would change any checked "
            "gang page. The slot types named Affiliation, Clan House, "
            "Chaos God and Variant remain. The deletion cannot run while "
            "any assignment still names an affiliation or any affiliation "
            "offer remains attached to a carrier; run the legacy affiliation "
            "assignment deletion first."
        ),
        view=delete_empty_affiliations_view,
        detail_template="admin/maintenance/n26/_delete_detail.html",
    )
)


@task
def clear_item_restrictions(backfill_id, **said_by_whoever_enqueued_it):
    """Strip the item-level restriction to fighter entries from every
    item the record's plan names, and record it.

    Library-only work in one transaction under the runner discipline:
    the equipment-lists upload wrote each list's "<Fighter> only" onto
    the item every list shares. The plan is the one the page previewed
    and wrote onto the record, so nothing that appeared after the
    preview is swept up. Nothing a player holds is touched.
    """
    from n26.library.item_restrictions import Refused, apply

    _run_recorded(
        backfill_id,
        Operation.CLEAR_ITEM_RESTRICTIONS,
        "Item restriction clearing",
        lambda: apply(_approved_plan(backfill_id)),
        Refused,
    )


def _approved_plan(backfill_id):
    """The plan written onto a record when its run was asked for, or
    ``None`` for a record that holds none."""
    record = Backfill.objects.filter(pk=backfill_id).first()
    return None if record is None else record.summary.get("plan")


CLEAR_ITEM_RESTRICTIONS_WORDS = {
    "noun": "removal",
    "intro": (
        "This clears the restriction to fighter entries (“usable by … only”) "
        "from every item that appears in at least one collection entry. The "
        "equipment-lists upload used to write the sheet's Restrictions column "
        "onto the item, and an item's restriction holds wherever the item is "
        "listed — so a bracket printed on one gang's list marked the item for "
        "every gang, and every upload wrote it again. The upload now writes "
        "the column onto the collection entry. Only the item's own restriction "
        "to fighter entries is cleared: restrictions to types and subtypes, "
        "items no collection lists, and every entry's own restrictions stay as "
        "they are. Upload the equipment lists again afterwards to write each "
        "list's own restrictions onto its entries. The items are listed below "
        "with the fighter entries they name and the collections that list them."
    ),
    "nothing_heading": "Nothing to clear",
    "nothing_flash": "No listed item carries a restriction to fighter entries.",
    "nothing_words": "No listed item carries a restriction to fighter entries.",
    "refuses_heading": "The removal cannot run",
    "button": "Clear the restrictions from these items",
    "confirm": (
        "Clear the restriction to fighter entries from these items? Upload the "
        "equipment lists again afterwards to restore each list's own "
        "restrictions. This cannot be undone."
    ),
}


def clear_item_restrictions_view(request):
    """Preview the removal (GET), or record a run and enqueue it."""
    from n26.library.item_restrictions import find

    return _deletion_view(
        request,
        Operation.CLEAR_ITEM_RESTRICTIONS,
        find,
        clear_item_restrictions,
        CLEAR_ITEM_RESTRICTIONS_WORDS,
    )


register_operation(
    MaintenanceOperation(
        operation=Operation.CLEAR_ITEM_RESTRICTIONS.value,
        name=Operation.CLEAR_ITEM_RESTRICTIONS.label,
        added=date(2026, 9, 12),
        description=(
            "Clear the restriction to fighter entries from every item that "
            "appears in a collection entry. The equipment-lists upload wrote "
            "each list's “<Fighter> only” onto the item every list shares, "
            "so one gang's bracket marked the item for every gang. Restrictions "
            "to types and subtypes, unlisted items and every entry's own "
            "restrictions stay. Upload the equipment lists again afterwards to "
            "write each list's restrictions onto its entries."
        ),
        view=clear_item_restrictions_view,
        detail_template="admin/maintenance/n26/_clear_item_restrictions_detail.html",
    )
)


@task
def seed_journal_content(backfill_id, **said_by_whoever_enqueued_it):
    """Create the Gang supertype and the two Underhive Journals' territories
    and tables, once, and record what was created.

    Library-only work in one transaction under the runner discipline:
    every row is matched on its name and pack and left alone where it
    stands, so a rerun creates nothing and says so. The built-in members
    it adds file the propagation pass that gives gangs already founded
    their supertype pick.
    """
    from n26.library.journal_content import seed_all

    _run_recorded(
        backfill_id,
        Operation.SEED_JOURNAL_CONTENT,
        "Journal content seed",
        seed_all,
        (),
    )


def seed_journal_content_view(request):
    """Say what the seed would create (GET), or record a run and enqueue it.

    The preview is the seed itself, run and rolled back, so it lists
    exactly the rows a run would create or skip. A seed with nothing to
    do records no run.
    """
    from n26.library.journal_content import NOTHING_TO_DO, preview

    operation = Operation.SEED_JOURNAL_CONTENT
    address = reverse(f"admin:maintenance_{operation.value}")
    if request.method == "POST":
        running = running_guard(operation)
        if running is not None:
            messages.warning(request, "That seed is already running.")
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[running.id])
            )
        try:
            lines = preview()
        except (ObjectDoesNotExist, MultipleObjectsReturned, ValidationError) as broke:
            # The same library shape the GET shows in words: a POST made by
            # hand against it gets the message, not an error page.
            messages.error(request, f"The seed cannot run: {broke}")
            return HttpResponseRedirect(address)
        if lines[0] == NOTHING_TO_DO:
            messages.info(request, NOTHING_TO_DO)
            return HttpResponseRedirect(address)
        backfill = Backfill.objects.create(
            operation=operation,
            triggered_by=request.user,
            status=Backfill.Status.RUNNING,
            summary={"preview": lines, "attempts": 0},
        )
        seed_journal_content.enqueue(backfill_id=str(backfill.id))
        messages.success(
            request, "The seed is running. This page shows what it creates."
        )
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )
    problem = ""
    try:
        lines = preview()
    except (ObjectDoesNotExist, MultipleObjectsReturned, ValidationError) as broke:
        # A library shape the seed does not expect — two Territory asset
        # types, say — is shown on the page in words rather than as an
        # error page, so the operation stays reachable.
        lines, problem = [], str(broke)
    context = page_context(
        request,
        operation.label,
        preview=lines,
        nothing_to_do=bool(lines) and lines[0] == NOTHING_TO_DO,
        problem=problem,
        apply_url=address,
        recent=Backfill.objects.filter(operation=operation)[:10],
    )
    return render(request, "admin/maintenance/n26/seed_journal_content.html", context)


register_operation(
    MaintenanceOperation(
        operation=Operation.SEED_JOURNAL_CONTENT.value,
        name=Operation.SEED_JOURNAL_CONTENT.label,
        added=date(2026, 9, 7),
        description=(
            "Create the Gang supertype: a hidden gang-level slot with six "
            "marker pickables, Goliath to Cawdor. It is built into each Clan "
            "House gang type with that House picked, and Clan House Outcast "
            "gangs are given it by their Clan House pickable. Create the two "
            "Underhive Journals' territories as well: twelve Territories "
            "under the Territory campaign type, each with its income and its "
            "House Controlled boon, and the Goliath Territories and Escher "
            "Territories tables, each given to the gangs of its House. The "
            "journal rows are staged until an author puts them live. Every "
            "row is matched by name, so running this again creates nothing. "
            "No money moves; the propagation pass gives gangs already "
            "founded their supertype pick."
        ),
        view=seed_journal_content_view,
        detail_template="admin/maintenance/n26/_seed_journal_content_detail.html",
    )
)


@task
def delete_test_content(backfill_id, **said_by_whoever_enqueued_it):
    """Delete content and the test gangs holding it, exactly as the
    authoring page showed it.

    Asked for from the authoring pages rather than the console: an
    author deleting a staged gang type is deleting their own test gang
    with it, and that is player data, so it runs here — recorded, locked,
    and read again under the lock before anything goes.
    """
    from n26.library.deletion import DeletionPlan, Refused, apply

    record = Backfill.objects.get(pk=backfill_id)
    plan = DeletionPlan.from_record(record.summary)
    _run_recorded(
        backfill_id,
        Operation.DELETE_TEST_CONTENT,
        "Test content deletion",
        lambda: apply(plan, actor=_who_asked(backfill_id)),
        Refused,
    )


@task
def delete_firing_line(backfill_id, **said_by_whoever_enqueued_it):
    """Remove a free firing line from every fighter that has it, gang by
    gang, and delete the row with the last of them.

    Gang by gang because each gang is proved to reconcile around its
    own commit, and a line a whole book of fighters carries is many
    gangs; the walk records how far it got and hands the rest to a
    fresh delivery.
    """
    from n26.library.deletion import (
        DeletionPlan,
        Refused,
        free_line_removal,
        remove_free_lines_from,
    )

    record = Backfill.objects.get(pk=backfill_id)
    plan = DeletionPlan.from_record(record.summary)
    run_per_gang(
        backfill_id,
        operation=Operation.DELETE_FIRING_LINE,
        what="Firing line deletion",
        find=lambda: free_line_removal(plan),
        apply_one=lambda gang_id: remove_free_lines_from(gang_id, plan),
        again=lambda: delete_firing_line.enqueue(backfill_id=backfill_id),
        refusals=(Refused,),
    )


@task
def merge_into(backfill_id, **said_by_whoever_enqueued_it):
    """Point everything naming a duplicate at the row it duplicates,
    gang by gang, and delete the duplicate with the last gang."""
    from n26.library.merging import MergePlan, Refused, merge_gang, merge_run

    record = Backfill.objects.get(pk=backfill_id)
    plan = MergePlan.from_record(record.summary)
    run_per_gang(
        backfill_id,
        operation=Operation.MERGE_INTO,
        what="Merge",
        find=lambda: merge_run(plan),
        apply_one=lambda gang_id: merge_gang(gang_id, plan),
        again=lambda: merge_into.enqueue(backfill_id=backfill_id),
        refusals=(Refused,),
    )


#: The operations the authoring pages ask for, and the task each runs
#: on. A plan that removes a line from fighters or merges a row walks
#: gangs; one that deletes gangs holds everything in one transaction.
AUTHORING_DELETIONS = {
    Operation.DELETE_TEST_CONTENT: delete_test_content,
    Operation.DELETE_FIRING_LINE: delete_firing_line,
    Operation.MERGE_INTO: merge_into,
}


class AnotherRunning(Exception):
    """A run of this operation is still going, so a second cannot start:
    the runner's lock would make it stand down without writing an
    ending, and its record would say running for ever."""


def start_authoring_deletion(plan, user):
    """Record a deletion the authoring page asked for, and enqueue it.

    The record holds the plan as the page showed it, so the run can
    refuse if what stands has changed, and so the page that shows the
    outcome can say what was asked. Returns the record. Raises
    :class:`AnotherRunning` while an earlier run of the same kind is
    still going.
    """
    if getattr(plan, "survivor", None):
        operation = Operation.MERGE_INTO
    elif plan.lines:
        operation = Operation.DELETE_FIRING_LINE
    else:
        operation = Operation.DELETE_TEST_CONTENT
    if running_guard(operation) is not None:
        raise AnotherRunning
    record = Backfill.objects.create(
        operation=operation,
        triggered_by=user,
        status=Backfill.Status.RUNNING,
        summary={**plan.as_record(), "attempts": 0},
    )
    AUTHORING_DELETIONS[operation].enqueue(backfill_id=str(record.id))
    return record


def authoring_deletion(pk):
    """One deletion's record, for the page that shows its outcome — or
    None where no such record exists."""
    return Backfill.objects.filter(
        pk=pk, operation__in=[op.value for op in AUTHORING_DELETIONS]
    ).first()


register_operation(
    MaintenanceOperation(
        operation=Operation.DELETE_TEST_CONTENT.value,
        name=Operation.DELETE_TEST_CONTENT.label,
        added=date(2026, 9, 9),
        description=(
            "Asked for from the content library's delete pages, not from "
            "here. Deletes library rows together with the test gangs "
            "holding them — gangs owned by staff that share no campaign "
            "or battle with a player's gang. Refuses in words if a "
            "player's gang holds any of it."
        ),
    )
)
register_operation(
    MaintenanceOperation(
        operation=Operation.MERGE_INTO.value,
        name=Operation.MERGE_INTO.label,
        added=date(2026, 9, 9),
        description=(
            "Asked for from a row's Merge into page, not from here. Points "
            "every assignment, list line, built-in membership and modifier "
            "part naming a duplicate at the row it duplicates, gang by gang, "
            "each gang proved to reconcile, and deletes the duplicate with "
            "the last of them. Moves no money."
        ),
    )
)
register_operation(
    MaintenanceOperation(
        operation=Operation.DELETE_FIRING_LINE.value,
        name=Operation.DELETE_FIRING_LINE.label,
        added=date(2026, 9, 9),
        description=(
            "Asked for from a firing line's delete page, not from here. "
            "Removes a free firing line — one the weapon brought, that "
            "nobody paid for — from every fighter that has it, gang by "
            "gang, each gang proved to reconcile, and deletes the row "
            "with the last of them."
        ),
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
    TaskRoute(delete_test_content, ack_deadline=600, min_retry_delay=60),
    TaskRoute(delete_firing_line, ack_deadline=600, min_retry_delay=60),
    TaskRoute(merge_into, ack_deadline=600, min_retry_delay=60),
    TaskRoute(delete_nameless_gang_type, ack_deadline=600, min_retry_delay=60),
    TaskRoute(convert_outcast_affiliation, ack_deadline=600, min_retry_delay=60),
    TaskRoute(convert_chaos_god, ack_deadline=600, min_retry_delay=60),
    TaskRoute(convert_variant, ack_deadline=600, min_retry_delay=60),
    TaskRoute(propagate_built_ins, ack_deadline=600),
    TaskRoute(sweep_built_in_propagations, schedule="*/5 * * * *"),
    TaskRoute(audit_reconcile),
    TaskRoute(repair_doubled_refunds, ack_deadline=600, min_retry_delay=60),
    TaskRoute(backfill_built_ins, ack_deadline=600),
    TaskRoute(drop_duplicate_grants, ack_deadline=600),
    TaskRoute(rehost_gang_picks, ack_deadline=600, min_retry_delay=60),
    TaskRoute(repoint_champion_picks, ack_deadline=600, min_retry_delay=60),
    TaskRoute(
        delete_legacy_affiliation_assignments,
        ack_deadline=600,
        min_retry_delay=60,
    ),
    TaskRoute(delete_empty_affiliations, ack_deadline=600, min_retry_delay=60),
    TaskRoute(open_founding_actions, ack_deadline=600),
    TaskRoute(seed_journal_content, ack_deadline=600, min_retry_delay=60),
    TaskRoute(clear_item_restrictions, ack_deadline=600, min_retry_delay=60),
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
