"""Register N26 repairs with the shared maintenance console and task framework. This module
owns the edition boundary for maintenance records, pages and delivery routes; repairs
run after deployment against the migrated schema.

Use _run_recorded for atomic work that fits one delivery. Use run_batched for idempotent
work with independent row transactions, or run_per_gang for repairs that reconcile each
gang before committing. Advisory locks prevent concurrent execution of one operation;
recorded progress resets the attempt limit.

Keep completed, non-recurring operations registered without a view so historical records
retain their labels.
"""

import json
import logging
import traceback
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.core import signing
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
from gyrinx.maintenance.registry import (
    MaintenanceOperation,
)
from gyrinx.maintenance.registry import (
    register_operation as register_platform_operation,
)
from gyrinx.maintenance.views import page_context, running_guard
from gyrinx.tasks import PausedTaskConsumer, TaskRoute
from n26.core.propagation import propagate_built_ins, sweep_built_in_propagations
from n26.write_pause import WritesPaused

logger = logging.getLogger(__name__)


def register_operation(operation):
    """Register every n26 maintenance page as an n26 writer."""
    register_platform_operation(replace(operation, write_scope="n26"))


def register_control_operation(operation):
    """Register a page whose service takes exclusive admission itself."""
    register_platform_operation(operation)


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
    "repair_campaign_reputation",
    "reset_prelaunch_campaign_cycles",
    "repoint_champion_picks",
    "seed_journal_content",
    "seed_territory_boons",
    "seed_territory_boon_choices",
    "remove_published_journal_boons",
    "PlanRefused",
    "run_batched",
    "run_per_gang",
    "task_routes",
]

#: Limit attempts without recorded progress; successful batched progress resets the
#: count.
MAX_ATTEMPTS = 2

#: Single-transaction routes use this delivery deadline. Warn when a run exceeds half the
#: limit so it can be moved to a batched runner before a slower run times out.
ONE_ATTEMPT_DEADLINE = timedelta(seconds=600)


class Operation(models.TextChoices):
    """Permanent operation slugs stored in maintenance audit records. Keep retired slugs
    registered so existing records still resolve.
    """

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
        "n26: the Spend founding TP action is opened on gangs that never had one",
    )
    DELETE_LEGACY_AFFILIATION_ASSIGNMENTS = (
        "n26_delete_legacy_affiliation_assignments",
        "n26: legacy affiliation assignments are deleted",
    )
    SEED_JOURNAL_CONTENT = (
        "n26_seed_journal_content",
        "n26: update journal territories and gang supertypes",
    )
    SEED_TERRITORY_BOONS = (
        "n26_seed_territory_boons",
        "n26: add territory income and standing boons",
    )
    SEED_TERRITORY_BOON_CHOICES = (
        "n26_seed_territory_boon_choices",
        "n26: add territory boon choices",
    )
    REMOVE_PUBLISHED_JOURNAL_BOONS = (
        "n26_remove_published_journal_boons",
        "n26: remove published journal boon placeholders",
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
    ORDER_COLLECTIONS = (
        "n26_order_collections",
        "n26: variant equipment lists are moved after the gang's own on Equip",
    )
    ACTIVATE_COUNTER_HISTORY = (
        "n26_activate_counter_history",
        "n26: activate counter history",
    )
    REPAIR_CAMPAIGN_REPUTATION = (
        "n26_repair_campaign_reputation",
        "n26: correct campaign reputation minimums",
    )
    INITIALISE_ACTION_ALLOWANCES = (
        "n26_initialise_action_allowances",
        "n26: existing fighters receive earned action allowances",
    )
    PREVIEW_ACTION_ALLOWANCES = (
        "n26_preview_action_allowances",
        "n26: preview existing model action allowances",
    )
    RESET_SPYRER_BUILT_INS = (
        "n26_reset_spyrer_built_ins",
        "n26: reset the mistaken Spyre Hunters built-ins",
    )
    FINISH_SPYRER_AUGMENTATIONS = (
        "n26_finish_spyrer_augmentations",
        "n26: finish the Spyrer augmentation launch",
    )
    RESET_PRELAUNCH_CAMPAIGN_CYCLES = (
        "n26_reset_prelaunch_campaign_cycles",
        "n26: reset prelaunch campaign cycles",
    )


#: Use a distinct advisory lock per operation. Running guards only inspect their own
#: operation, so a shared lock could acknowledge another repair's delivery while leaving
#: its record RUNNING.
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
    Operation.SEED_TERRITORY_BOONS: 826_020_631,
    Operation.SEED_TERRITORY_BOON_CHOICES: 826_020_632,
    Operation.REMOVE_PUBLISHED_JOURNAL_BOONS: 826_020_629,
    Operation.DELETE_TEST_CONTENT: 826_020_620,
    Operation.DELETE_FIRING_LINE: 826_020_621,
    Operation.MERGE_INTO: 826_020_622,
    Operation.CLEAR_ITEM_RESTRICTIONS: 826_020_623,
    Operation.ORDER_COLLECTIONS: 826_020_625,
    Operation.ACTIVATE_COUNTER_HISTORY: 826_020_627,
    Operation.INITIALISE_ACTION_ALLOWANCES: 826_020_626,
    Operation.PREVIEW_ACTION_ALLOWANCES: 826_020_630,
    Operation.REPAIR_CAMPAIGN_REPUTATION: 826_020_633,
    Operation.RESET_SPYRER_BUILT_INS: 826_020_628,
    Operation.RESET_PRELAUNCH_CAMPAIGN_CYCLES: 826_020_634,
}


def _write(backfill_id, *, status=None, summary_patch=None, error=""):
    """Update progress under a row lock, returning False if the record is missing or
    terminal. Preserve DONE, FAILED and CANCELLED statuses so late deliveries cannot
    overwrite a completed or cancelled run.
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
    """Try to hold the operation advisory lock until the caller exits, yielding whether it
    was acquired. PostgreSQL releases the lock if the connection closes.
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
    """Increment the attempt count independently of the repair transaction, refusing
    non-running records and attempts beyond MAX_ATTEMPTS. Batched progress resets the
    count so only attempts without progress exhaust the limit.
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
    """Run work under the operation lock and record its result. The work must provide its
    own atomic transaction and finish within one delivery.

    Record expected refusals as messages and unexpected exceptions with tracebacks.
    WritesPaused propagates for retry; other work failures end the record without
    triggering redelivery. Warn when execution exceeds half ONE_ATTEMPT_DEADLINE,
    because slower runs may exceed the delivery limit.
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
            # Record expected refusal messages without a traceback.
            _write(backfill_id, status=Backfill.Status.FAILED, error=str(refused))
            return
        except WritesPaused:
            raise
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


#: The budget plus one batch must fit within the route acknowledgement deadline, because
#: the budget is checked between batches. The default leaves one minute for the final
#: batch.
BATCH_BUDGET = timedelta(minutes=4)

#: Record progress every 50 rows to limit crash replay without writing progress after
#: each row.
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
    stand_down=None,
):
    """Process a stable queryset in primary-key order, saving progress after each batch.
    do_one(pk) must commit its own atomic writes and be idempotent: a crash can replay
    the last unrecorded batch, and a new run visits all rows again. Returned strings are
    appended to the report.

    items may be a callable evaluated under the operation lock on each delivery. A
    refusals exception fails the run; returning None must leave a terminal record or the
    runner marks it failed. Keep the queryset membership stable while processing so
    totals and the cursor remain meaningful.

    Record row failures and continue; any recorded failures make the final status
    FAILED. Progress writes reset the attempt count and stop processing if cancellation
    or another terminal status prevents the write. Check cancellation before each batch
    too.

    After budget expires, enqueue the continuation only after releasing the lock. Work
    exceptions are recorded except WritesPaused, which propagates for retry.
    Continuation and stand_down exceptions also propagate so failed delivery can be
    retried.
    """
    continued = False
    contended = False
    with _single_flight(LOCK_KEYS[operation]) as mine:
        if not mine:
            logger.info("%s already running; this copy stands down", what)
            contended = True
        if mine:
            may_start, why_not = _claim(backfill_id)
        if mine and not may_start:
            logger.info("%s not started: %s", what, why_not)
            _write(
                backfill_id,
                status=Backfill.Status.FAILED,
                error=f"Not started: {why_not}",
            )
            return
        if mine:
            try:
                work_list = items() if callable(items) else items
                if work_list is not None:
                    continued = _work_through(
                        backfill_id, what, work_list, do_one, batch_size, budget
                    )
                elif Backfill.objects.filter(
                    pk=backfill_id, status=Backfill.Status.RUNNING
                ).exists():
                    _write(
                        backfill_id,
                        status=Backfill.Status.FAILED,
                        error=(
                            "The work-list reported nothing to walk but wrote no "
                            "ending onto the record."
                        ),
                    )
            except refusals as refused:
                _write(backfill_id, status=Backfill.Status.FAILED, error=str(refused))
            except WritesPaused:
                raise
            except Exception as broke:  # noqa: BLE001 — the ending must be recorded
                logger.exception("%s broke", what)
                _write(
                    backfill_id,
                    status=Backfill.Status.FAILED,
                    error=f"{broke}\n\n{traceback.format_exc()}",
                )
    if contended and stand_down is not None:
        stand_down()
    elif continued:
        again()


def _work_through(backfill_id, what, items, do_one, batch_size, budget):
    """Process one delivery, returning True when another delivery must continue from the
    recorded cursor.
    """
    started = timezone.now()
    backfill = Backfill.objects.get(pk=backfill_id)
    cursor = backfill.summary.get("cursor", "")
    settled = int(backfill.summary.get("done", 0))
    failures = dict(backfill.summary.get("failures", {}))
    report = list(backfill.summary.get("report", []))
    # Keep the original total across deliveries so progress does not change as the
    # queryset is processed.
    total = backfill.summary.get("total")
    if total is None:
        total = items.count()

    items = items.order_by("pk")

    def record(position):
        # Recorded progress resets the consecutive-attempt limit.
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
        # Check cancellation before starting a batch, including cancellation received
        # after the previous progress write.
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
            except WritesPaused:
                raise
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
        # Enqueue another delivery only if rows remain after the budget expires.
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
    """The per-gang plan contains problems that prevent the repair from starting."""


#: Use smaller batches for per-gang reconciliation: the time budget is checked only
#: between batches, and each gang requires multiple queries.
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
    stand_down=None,
):
    """Run a repair through run_batched using a recorded list of gang IDs. On the first
    delivery, find() returns a plan with gangs, problems and nothing_here; problems
    refuse the run, while nothing_here completes it with the preview report.

    Record the initial IDs so later deliveries cannot miss newly discovered gangs behind
    the cursor. apply_one(gang_id) must recheck current state, repair and reconcile the
    gang in its own transaction, and return its report line. Leave the approved preview
    in summary["preview"].

    Pass find() exceptions that should fail the record in refusals; PlanRefused is
    always included.
    """
    from n26.core.models import Gang

    def gangs():
        backfill = Backfill.objects.get(pk=backfill_id)
        ids = backfill.summary.get("gang_ids")
        if ids is None:
            plan = find()
            if plan is None:
                return None
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
        stand_down=stand_down,
    )


def _plan(system):
    from n26.library.conversion import SYSTEMS

    return SYSTEMS[system]()


def _run_conversion(backfill_id, operation, system, **said_by_whoever_enqueued_it):
    """Run a conversion and record its outcome. Ignore extra message arguments because
    queued deliveries can outlive the code version that enqueued them.
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

    _run_conversion(
        backfill_id,
        Operation.CONVERT_OUTCAST_AFFILIATION,
        "outcast_affiliation",
        **said_by_whoever_enqueued_it,
    )


@task
def convert_chaos_god(backfill_id, **said_by_whoever_enqueued_it):

    _run_conversion(
        backfill_id,
        Operation.CONVERT_CHAOS_GOD,
        "chaos_god",
        **said_by_whoever_enqueued_it,
    )


@task
def convert_variant(backfill_id, **said_by_whoever_enqueued_it):

    _run_conversion(
        backfill_id,
        Operation.CONVERT_VARIANT,
        "variant",
        **said_by_whoever_enqueued_it,
    )


def _proof_words(plan):

    # Match Plan.preview when reaches is omitted.
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
    """Return the requesting operator for new repair history entries, or None if the record
    is missing. Preserve actors on existing player history.
    """
    backfill = Backfill.objects.filter(pk=backfill_id).first()
    return backfill.triggered_by if backfill else None


@task
def delete_nameless_gang_type(backfill_id, **said_by_whoever_enqueued_it):
    """Retire the nameless gang type through an atomic repair that checks every affected
    gang before writing.
    """
    from n26.library.nameless_gang_type import Refused, apply, find

    _run_recorded(
        backfill_id,
        Operation.DELETE_NAMELESS_GANG_TYPE,
        "Nameless gang type retirement",
        lambda: apply(find(), actor=_who_asked(backfill_id)),
        Refused,
    )


#: Operation-specific copy for the shared deletion page.
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
    """Preview a plan on GET; on POST, reject running, empty or invalid plans before
    recording and enqueuing work. words supplies the operation-specific page copy.
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
        # Retain plan-specific row IDs or other approved state alongside the preview for
        # execution-time checks.
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
    """Remove surplus refund, sale and removal events, reconciling each gang within its own
    transaction. A failed gang rolls back without blocking the others.
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
    """Move live gang-hosted picks from models onto their gangs. Reconcile and commit each
    gang separately.
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
    """Delete unused affiliation library rows without changing player data. The repair
    checks that the inspected gang pages remain unchanged.
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
    """Delete archived None assignments and obsolete live affiliation assignments, one gang
    at a time.
    """
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

    from n26.core.legacy_affiliation_assignments import find

    return _deletion_view(
        request,
        Operation.DELETE_LEGACY_AFFILIATION_ASSIGNMENTS,
        find,
        delete_legacy_affiliation_assignments,
        LEGACY_AFFILIATION_ASSIGNMENT_WORDS,
    )


@task
def reset_spyrer_built_ins(backfill_id, **unused):
    from n26.core.reset_spyrer_built_ins import Refused, apply_one, prepare

    run_per_gang(
        backfill_id,
        operation=Operation.RESET_SPYRER_BUILT_INS,
        what="Spyre Hunters built-in reset",
        find=prepare,
        apply_one=apply_one,
        refusals=(Refused,),
        again=lambda: reset_spyrer_built_ins.enqueue(backfill_id=backfill_id),
    )


def reset_spyrer_built_ins_view(request):
    from n26.core.reset_spyrer_built_ins import find

    return _deletion_view(
        request,
        Operation.RESET_SPYRER_BUILT_INS,
        find,
        reset_spyrer_built_ins,
        {
            "noun": "reset",
            "intro": (
                "Remove Fighter progression, Promotion, Suit Evolution and Suit "
                "Maintenance from the Spyre Hunters built-ins and existing gangs. "
                "Delete their three inspected action uses and restore the staff "
                "test's counter values. Gangs, equipment, XP and other completed "
                "advancements are kept. The shared rules and actions are kept."
            ),
            "nothing_heading": "Nothing to reset",
            "nothing_flash": "The mistaken Spyre Hunters setup has been removed.",
            "nothing_words": "The mistaken Spyre Hunters setup has been removed.",
            "refuses_heading": "The reset cannot run",
            "button": "Reset the mistaken setup",
            "confirm": "Delete these attachments, propagated assignments and action uses? This cannot be undone.",
        },
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
    """Repoint live picks to same-named pickables in their current slot picklists.
    Reconcile and commit each gang separately.
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
    """Check every unarchived gang against its ledger without changing player data. Record
    discrepancies per gang and continue the batched audit.
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
    """Tag legacy built-in grants with provenance and catch up live carriers, committing
    each gang separately. Include archived gangs because they may be restored and are
    excluded from normal propagation; record running totals after each gang.
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
    """Preview legacy grants by kind and count gangs without walking every carrier. Exact
    catch-up totals are calculated by the background run.
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
    """Remove duplicate catch-up grants, reconciling and committing each gang separately."""
    from n26.core.duplicate_grants import de_duplicate
    from n26.core.models import Gang

    record = Backfill.objects.get(pk=backfill_id)
    totals = dict(record.summary.get("totals", {}))
    kept_a_tally = list(record.summary.get("kept_a_tally", []))
    # A targeted repair records the model and its gang so only that gang is visited.
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

    from n26.core.duplicate_grants import (
        duplicate_grants_by_kind,
        what_one_model_carries,
    )
    from n26.core.models import Gang, Miniature

    operation = Operation.DROP_DUPLICATE_GRANTS
    address = reverse(f"admin:maintenance_{operation.value}")
    # Use the same optional model ID for both preview and execution.
    asked = (request.POST.get("model") or request.GET.get("model") or "").strip()
    one = None
    if asked:
        try:
            one = Miniature.objects.filter(pk=asked).first()
        except ValidationError, ValueError, TypeError:
            # Invalid IDs can raise while the queryset is built.
            one = None
        if one is not None and one.membership_id is None:
            # Exclude models without a gang membership.
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
    """Return unarchived gangs with no founding action, including completed actions in the
    exclusion. Completing an action must not make the gang eligible for another.
    """
    from n26.core.models import Activity, Gang

    return Gang.objects.filter(archived=False).exclude(
        activities__kind=Activity.Kind.FOUNDING
    )


@task
def open_founding_actions(backfill_id, **said_by_whoever_enqueued_it):
    """Open missing founding actions through the domain operation, with no actor so
    automated backfill does not attribute gang history to a staff account.

    Walk all unarchived gangs to keep the batched queryset stable as actions are opened.
    Skip gangs that already have an open or completed founding action, making reruns
    idempotent.
    """
    from n26.core.models import Activity, Gang
    from n26.core.operations import Refusal, operation

    record = Backfill.objects.get(pk=backfill_id)
    totals = dict(record.summary.get("totals", {}))

    def add_to_totals(key):
        totals[key] = int(totals.get(key, 0)) + 1
        _write(backfill_id, summary_patch={"totals": totals})

    def do_one(pk):
        gang = Gang.objects.filter(pk=pk, archived=False).first()
        if gang is None:
            # Skip gangs archived or deleted since the queryset was counted.
            return
        if Activity.objects.filter(gang=gang, kind=Activity.Kind.FOUNDING).exists():
            add_to_totals("already_had_one")
            return
        try:
            with operation(gang, actor=None) as op:
                op.open_activity(Activity.Kind.FOUNDING)
        except Refusal:
            # The owner may open the action between this check and the operation lock.
            # Treat that refusal as an existing action.
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
    """Report both eligible gangs and gangs visited, because batched progress counts the
    full queryset rather than only changed gangs.
    """
    return [
        f"{eligible} of {walked} unarchived gang"
        f"{'' if walked == 1 else 's'} "
        f"{'has' if eligible == 1 else 'have'} never had a Spend founding "
        "TP action.",
        "Every unarchived gang is walked, so this run's total counts "
        "gangs walked, not gangs changed.",
    ]


def open_founding_actions_view(request):

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
                "has the Spend founding TP action.",
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
            "Open the Spend founding TP action on every unarchived "
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


def _allowance_preview_plan(record):
    """Read only a fully successful scan, never a partial work-list."""
    from n26.core.action_initialisation import InitialisationPlan

    if record is None or record.status != Backfill.Status.DONE:
        raise PlanRefused("Prepare and review a completed allowance preview first.")
    gangs, missing, problems = [], [], []
    for line in (
        record.summary.get("report", []) if record.summary.get("gang_ids") else []
    ):
        result = json.loads(line)
        gangs.extend((pk,) for pk in result["gangs"])
        missing.extend(result["missing_baselines"])
        problems.extend(result["problems"])
    return InitialisationPlan(tuple(gangs), tuple(missing), tuple(problems))


@task
def preview_action_allowances(backfill_id, **said_by_whoever_enqueued_it):
    """Inspect effective fighter access off the HTTP request, gang by gang."""
    from n26.core.action_initialisation import candidates, find
    from n26.core.models import Gang

    def inspect_one(gang_id):
        gang = Gang.objects.filter(pk=gang_id, archived=False).first()
        plan = find(gang) if gang is not None else None
        return json.dumps(
            {
                "gangs": [str(pk) for pk, *_ in plan.gangs] if plan else [],
                "missing_baselines": plan.missing_baselines if plan else [],
                "problems": plan.problems if plan else [],
            }
        )

    def retry_after_lock_holder():
        raise RuntimeError("Action allowance preview is already running.")

    run_per_gang(
        backfill_id,
        operation=Operation.PREVIEW_ACTION_ALLOWANCES,
        what="Existing model allowance preview",
        find=candidates,
        apply_one=inspect_one,
        again=lambda: preview_action_allowances.enqueue(backfill_id=backfill_id),
        stand_down=retry_after_lock_holder,
    )


register_operation(
    MaintenanceOperation(
        operation=Operation.PREVIEW_ACTION_ALLOWANCES.value,
        name=Operation.PREVIEW_ACTION_ALLOWANCES.label,
        added=date(2026, 10, 11),
        description="Inspect existing model allowances without changing player data.",
        detail_template="admin/maintenance/n26/_action_allowance_preview_detail.html",
    )
)


@task
def repair_campaign_reputation(backfill_id, **said_by_whoever_enqueued_it):
    """Journal minimum corrections once per affected campaign counter."""
    from n26.core.reputation_repair import apply_one, find

    run_per_gang(
        backfill_id,
        operation=Operation.REPAIR_CAMPAIGN_REPUTATION,
        what="Campaign reputation correction",
        find=find,
        apply_one=apply_one,
        again=lambda: repair_campaign_reputation.enqueue(backfill_id=backfill_id),
    )


def repair_campaign_reputation_view(request):
    from n26.core.reputation_repair import find

    return _deletion_view(
        request,
        Operation.REPAIR_CAMPAIGN_REPUTATION,
        find,
        repair_campaign_reputation,
        {
            "noun": "correction",
            "intro": "Raise active campaign reputation balances below their minimum. Each correction is recorded in the gang’s history. Higher balances and credits remain unchanged.",
            "nothing_heading": "No corrections needed",
            "nothing_flash": "Campaign reputation balances meet their minimums.",
            "nothing_words": "Campaign reputation balances meet their minimums.",
            "refuses_heading": "The correction cannot run",
            "button": "Correct reputation",
            "confirm": "Raise the listed reputation balances to their minimums?",
        },
    )


register_operation(
    MaintenanceOperation(
        operation=Operation.REPAIR_CAMPAIGN_REPUTATION.value,
        name=Operation.REPAIR_CAMPAIGN_REPUTATION.label,
        added=date(2026, 10, 15),
        description="Raise active campaign reputation balances to their minimums and record each correction in gang history.",
        view=repair_campaign_reputation_view,
        detail_template="admin/maintenance/n26/_per_gang_detail.html",
    )
)


@task
def initialise_action_allowances(backfill_id, **said_by_whoever_enqueued_it):
    """Give existing fighters the rank allowances earned since recruitment."""
    from n26.core.action_initialisation import INACTIVE_REASON, apply_one
    from n26.core.counter_tracking import is_active

    operation = Operation.INITIALISE_ACTION_ALLOWANCES

    def retry_after_lock_holder():
        # Raise so Pub/Sub applies retry backoff. Enqueuing immediately would loop while
        # another worker holds the operation lock.
        raise RuntimeError("Action allowance initialisation is already running.")

    def find_once():
        # Check the one-off completion record under the operation lock so concurrent
        # queued runs cannot both pass.
        if (
            Backfill.objects.filter(operation=operation, status=Backfill.Status.DONE)
            .exclude(pk=backfill_id)
            .exists()
        ):
            _write(
                backfill_id,
                status=Backfill.Status.FAILED,
                error="Existing fighter allowances were already initialised.",
            )
            return None
        if not is_active():
            raise PlanRefused(INACTIVE_REASON)
        record = Backfill.objects.get(pk=backfill_id)
        preview_id = record.summary.get("preview_id")
        preview = (
            Backfill.objects.filter(
                pk=preview_id, operation=Operation.PREVIEW_ACTION_ALLOWANCES
            ).first()
            if preview_id
            else None
        )
        return _allowance_preview_plan(preview)

    run_per_gang(
        backfill_id,
        operation=operation,
        what="Existing fighter action allowances",
        find=find_once,
        apply_one=apply_one,
        again=lambda: initialise_action_allowances.enqueue(backfill_id=backfill_id),
        stand_down=retry_after_lock_holder,
    )


def initialise_action_allowances_view(request):
    """Preview the legacy fighter plan, or enqueue its recorded run."""
    from n26.core.action_initialisation import INACTIVE_REASON
    from n26.core.counter_tracking import is_active

    operation = Operation.INITIALISE_ACTION_ALLOWANCES
    address = reverse(f"admin:maintenance_{operation.value}")
    completed = Backfill.objects.filter(
        operation=operation, status=Backfill.Status.DONE
    ).first()
    if request.method == "POST" and completed is not None:
        messages.info(request, "Existing fighter allowances were already initialised.")
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[completed.id])
        )
    active = is_active()
    preview = (
        Backfill.objects.filter(operation=Operation.PREVIEW_ACTION_ALLOWANCES).first()
        if completed is None
        else None
    )
    plan = (
        _allowance_preview_plan(preview)
        if preview is not None and preview.status == Backfill.Status.DONE
        else None
    )
    if request.method == "POST":
        running = running_guard(operation)
        if running is not None:
            messages.warning(request, "That initialisation is already running.")
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[running.id])
            )
        if not active:
            messages.error(request, INACTIVE_REASON)
            return HttpResponseRedirect(address)
        if request.POST.get("action") == "preview":
            running = running_guard(Operation.PREVIEW_ACTION_ALLOWANCES)
            if running is None:
                running = Backfill.objects.create(
                    operation=Operation.PREVIEW_ACTION_ALLOWANCES,
                    triggered_by=request.user,
                    status=Backfill.Status.RUNNING,
                    summary={"attempts": 0},
                )
                preview_action_allowances.enqueue(backfill_id=str(running.id))
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[running.id])
            )
        if plan is None or request.POST.get("preview_id") != str(preview.pk):
            messages.error(
                request, "Prepare and review a completed allowance preview first."
            )
            return HttpResponseRedirect(address)
        if plan.problems:
            if len(plan.problems) == 1:
                messages.error(request, plan.problems[0])
            else:
                messages.error(
                    request,
                    "Resolve the reported problems before initialising allowances.",
                )
            return HttpResponseRedirect(address)
        if plan.nothing_here:
            messages.info(
                request, "There are no existing fighter allowances to initialise."
            )
            return HttpResponseRedirect(address)
        backfill = Backfill.objects.create(
            operation=operation,
            triggered_by=request.user,
            status=Backfill.Status.RUNNING,
            summary={
                "preview": plan.preview(),
                "preview_id": str(preview.pk),
                "attempts": 0,
            },
        )
        initialise_action_allowances.enqueue(backfill_id=str(backfill.id))
        messages.success(request, "The initialisation is running.")
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )
    context = page_context(
        request,
        operation.label,
        plan=plan,
        preview=preview,
        inactive_reason=INACTIVE_REASON if not active else "",
        completed=completed,
        apply_url=address,
        recent=Backfill.objects.filter(operation=operation)[:10],
    )
    return render(
        request,
        "admin/maintenance/n26/initialise_action_allowances.html",
        context,
    )


register_operation(
    MaintenanceOperation(
        operation=Operation.INITIALISE_ACTION_ALLOWANCES.value,
        name=Operation.INITIALISE_ACTION_ALLOWANCES.label,
        added=date(2026, 9, 14),
        description=(
            "Give existing fighters the action uses earned by XP thresholds crossed "
            "since recruitment. Missing starting values are reported and skipped; "
            "conflicting rank tables refuse the run. Each gang is proved before and after."
        ),
        view=initialise_action_allowances_view,
        detail_template="admin/maintenance/n26/_per_gang_detail.html",
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
        operation=Operation.RESET_SPYRER_BUILT_INS.value,
        name=Operation.RESET_SPYRER_BUILT_INS.label,
        added=date(2026, 9, 22),
        description="Remove the four mistaken Spyre Hunters built-ins, their propagated assignments and three inspected action uses.",
        view=reset_spyrer_built_ins_view,
        detail_template="admin/maintenance/n26/_per_gang_detail.html",
    )
)

register_operation(
    MaintenanceOperation(
        operation=Operation.FINISH_SPYRER_AUGMENTATIONS.value,
        name=Operation.FINISH_SPYRER_AUGMENTATIONS.label,
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
    """Clear item-level fighter-entry restrictions using the approved plan stored on the
    record. Apply the library-only repair atomically so items added after the preview
    are excluded.
    """
    from n26.library.item_restrictions import Refused, apply

    _run_recorded(
        backfill_id,
        Operation.CLEAR_ITEM_RESTRICTIONS,
        "Item restriction clearing",
        lambda: apply(_approved_plan(backfill_id)),
        Refused,
    )


@task
def order_collections(backfill_id, **said_by_whoever_enqueued_it):
    """Order variant equipment lists after the gang list through an atomic library-only
    repair.
    """
    from n26.library.collection_positions import Refused, apply, find

    _run_recorded(
        backfill_id,
        Operation.ORDER_COLLECTIONS,
        "Collection ordering",
        lambda: apply(find()),
        Refused,
    )


def _approved_plan(backfill_id):
    """Return the recorded approved plan, or None if the record or plan is missing."""
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


ORDER_COLLECTIONS_WORDS = {
    "intro": (
        "This sets the order of the equipment lists a fighter or gang holds. "
        "The Equip screen opens on the list with the lowest position. Every "
        "list starts at 0, so a list added by a variant can open before the "
        "gang's own. This sets position 100 on every list that is granted "
        "only by picks that are not gang archetypes, and leaves every other "
        "list as it is. The table lists every collection, how it reaches a "
        "card, and what applying does to it. Check it against the lists in "
        "production before applying. You can change any list's position on "
        "its authoring page afterwards."
    ),
    "nothing_heading": "Nothing to set",
    "nothing_flash": "There was nothing to set.",
    "nothing_words": (
        "Every list granted only by variant picks already has a position above 0."
    ),
    "refuses_heading": "The positions cannot be set",
    "button": "Set position 100 on the variant lists",
    "confirm": (
        "Set position 100 on the lists marked in the table? You can change "
        "any list's position on its authoring page afterwards."
    ),
}


def clear_item_restrictions_view(request):

    from n26.library.item_restrictions import find

    return _deletion_view(
        request,
        Operation.CLEAR_ITEM_RESTRICTIONS,
        find,
        clear_item_restrictions,
        CLEAR_ITEM_RESTRICTIONS_WORDS,
    )


def order_collections_view(request):

    from n26.library.collection_positions import VARIANT_POSITION, find

    operation = Operation.ORDER_COLLECTIONS
    address = reverse(f"admin:maintenance_{operation.value}")
    if request.method == "POST":
        running = running_guard(operation)
        if running is not None:
            messages.warning(request, "That run is already running.")
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[running.id])
            )
        plan = find()
        if plan.nothing_here:
            messages.info(request, ORDER_COLLECTIONS_WORDS["nothing_flash"])
            return HttpResponseRedirect(address)
        backfill = Backfill.objects.create(
            operation=operation,
            triggered_by=request.user,
            status=Backfill.Status.RUNNING,
            summary={"preview": list(plan.preview()), "attempts": 0},
        )
        order_collections.enqueue(backfill_id=str(backfill.id))
        messages.success(request, "The run has started. The result will appear below.")
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )

    plan = find()
    context = page_context(
        request,
        operation.label,
        plan=plan,
        readings=plan.readings,
        variant_position=VARIANT_POSITION,
        words=ORDER_COLLECTIONS_WORDS,
        apply_url=address,
        recent=Backfill.objects.filter(operation=operation)[:10],
    )
    return render(request, "admin/maintenance/n26/order_collections.html", context)


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


register_operation(
    MaintenanceOperation(
        operation=Operation.ORDER_COLLECTIONS.value,
        name=Operation.ORDER_COLLECTIONS.label,
        added=date(2026, 9, 12),
        description=(
            "Set position 100 on every equipment list that is granted only "
            "by picks that are not gang archetypes, so it sorts after the "
            "gang's own list on the Equip screen. Every other list keeps "
            "its position. The page lists every collection with how it "
            "reaches a card, for checking before applying."
        ),
        view=order_collections_view,
        detail_template="admin/maintenance/n26/_order_collections_detail.html",
    )
)


@task
def seed_journal_content(backfill_id, **said_by_whoever_enqueued_it):
    """Create missing gang-supertype and journal content, removing unchanged seeded boon
    placeholders. Match library rows by name and pack; added built-in members record
    propagation work for existing gangs.
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
    """Preview the seed inside a rolled-back transaction, then record and enqueue non-empty
    work. Report invalid library structures on the page.
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
            # Handle invalid library state on POST as well as GET.
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
            request,
            "The journal content update is running. This page shows its changes.",
        )
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )
    problem = ""
    try:
        lines = preview()
    except (ObjectDoesNotExist, MultipleObjectsReturned, ValidationError) as broke:
        # Show invalid library state, such as duplicate asset types, without making the
        # maintenance page inaccessible.
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


register_control_operation(
    MaintenanceOperation(
        operation=Operation.SEED_JOURNAL_CONTENT.value,
        name=Operation.SEED_JOURNAL_CONTENT.label,
        added=date(2026, 9, 7),
        description=(
            "Create the gang supertype: a hidden gang-level slot with six "
            "marker pickables, Goliath to Cawdor. It is built into each Clan "
            "House gang type with that House picked, and Clan House Outcast "
            "gangs are given it by their Clan House pickable. Create the three "
            "Underhive Journals' territories as well: eighteen territories "
            "under the Territory campaign type, each with its baseline "
            "income, and the Goliath Territories, Escher Territories and Orlock "
            "Territories tables, each given to the gangs of its House. The "
            "journal rows are staged until an author puts them live. Remove "
            "the known seeded House Controlled modifiers and unused "
            "placeholder rules. Retain and report modified or reused content "
            "and rules referenced by player history. Running this again "
            "makes no further changes. "
            "No money moves; the propagation pass gives gangs already "
            "founded their supertype pick."
        ),
        view=seed_journal_content_view,
        detail_template="admin/maintenance/n26/_seed_journal_content_detail.html",
    )
)


@task
def seed_territory_boons(backfill_id, **said_by_whoever_enqueued_it):
    """Seed baseline Income and standing territory boons in a recorded run."""
    from n26.library.territory_boons import seed_all

    _run_recorded(
        backfill_id,
        Operation.SEED_TERRITORY_BOONS,
        "Territory income and standing boons",
        seed_all,
        (),
    )


def seed_territory_boons_view(request):
    """Preview the content pass, then enqueue one recorded library transaction."""
    from n26.library.territory_boons import NOTHING_TO_DO, preview
    from n26.write_pause import SCOPE, exclusive_write_scope

    operation = Operation.SEED_TERRITORY_BOONS
    address = reverse(f"admin:maintenance_{operation.value}")
    if request.method == "POST":
        with exclusive_write_scope(SCOPE):
            running = running_guard(operation)
            if running is not None:
                messages.warning(request, "That content update is already running.")
                return HttpResponseRedirect(
                    reverse("admin:maintenance_backfill_detail", args=[running.id])
                )
            try:
                lines = preview()
            except (
                ObjectDoesNotExist,
                MultipleObjectsReturned,
                ValidationError,
            ) as broke:
                messages.error(request, f"The content update cannot run: {broke}")
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
        # Task delivery must see the committed run and released admission.
        seed_territory_boons.enqueue(backfill_id=str(backfill.id))
        messages.success(request, "The territory content update is running.")
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )
    problem = ""
    try:
        lines = preview()
    except (ObjectDoesNotExist, MultipleObjectsReturned, ValidationError) as broke:
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
    return render(request, "admin/maintenance/n26/seed_territory_boons.html", context)


register_control_operation(
    MaintenanceOperation(
        operation=Operation.SEED_TERRITORY_BOONS.value,
        name=Operation.SEED_TERRITORY_BOONS.label,
        added=date(2026, 10, 11),
        description=(
            "Add baseline Income for Settlement, the 18 core territories and "
            "the 18 journal territories. Add six supported standing boons: "
            "Generatorium and Gambling Den add 1 Reputation; Goliath gangs "
            "holding Amneo-vats gain 10 more Income; Escher gangs holding "
            "Shivver Den gain 1 Reputation; Orlock gangs holding Toll Road gain "
            "10 more Income, and those holding Container Stacks gain 1 Reputation. "
            "Preserve and report authored "
            "conflicts. New content is staged. Effects attached to existing "
            "assets apply to their current holders immediately. Credit "
            "collection, recruitment, equipment rewards and battlefield "
            "effects remain manual."
        ),
        view=seed_territory_boons_view,
        detail_template="admin/maintenance/n26/_seed_territory_boons_detail.html",
    )
)


def territory_boon_setup_links(user):
    """Authoring shortcuts to the existing superuser-only content previews."""
    if not user.is_superuser:
        return {}
    return {
        "income": reverse(f"admin:maintenance_{Operation.SEED_TERRITORY_BOONS.value}"),
        "choices": reverse(
            f"admin:maintenance_{Operation.SEED_TERRITORY_BOON_CHOICES.value}"
        ),
    }


@task
def seed_territory_boon_choices(backfill_id, **said_by_whoever_enqueued_it):
    """Record the guarded territory boon conversion and current Income picks."""
    from n26.library.territory_boon_choices import seed_all

    _run_recorded(
        backfill_id,
        Operation.SEED_TERRITORY_BOON_CHOICES,
        "Territory boon choices",
        lambda: seed_all(actor=Backfill.objects.get(pk=backfill_id).triggered_by),
        (),
    )


def seed_territory_boon_choices_view(request):
    """Preview the content pass, then enqueue one recorded library transaction."""
    from n26.library.territory_boon_choices import NOTHING_TO_DO, preview
    from n26.write_pause import SCOPE, exclusive_write_scope

    operation = Operation.SEED_TERRITORY_BOON_CHOICES
    address = reverse(f"admin:maintenance_{operation.value}")
    if request.method == "POST":
        with exclusive_write_scope(SCOPE):
            running = running_guard(operation)
            if running is not None:
                messages.warning(request, "That content update is already running.")
                return HttpResponseRedirect(
                    reverse("admin:maintenance_backfill_detail", args=[running.id])
                )
            try:
                lines = preview()
            except (
                ObjectDoesNotExist,
                MultipleObjectsReturned,
                ValidationError,
            ) as broke:
                messages.error(request, f"The content update cannot run: {broke}")
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
        # Task delivery must see the committed run and released admission.
        seed_territory_boon_choices.enqueue(backfill_id=str(backfill.id))
        messages.success(request, "The territory boon update is running.")
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )
    problem = ""
    try:
        lines = preview()
    except (ObjectDoesNotExist, MultipleObjectsReturned, ValidationError) as broke:
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
    return render(
        request, "admin/maintenance/n26/seed_territory_boon_choices.html", context
    )


register_control_operation(
    MaintenanceOperation(
        operation=Operation.SEED_TERRITORY_BOON_CHOICES.value,
        name=Operation.SEED_TERRITORY_BOON_CHOICES.label,
        added=date(2026, 10, 11),
        description=(
            "Add an Income choice and one manual cycle reward policy for 14 "
            "territories, including Settlement. Keep the existing Income "
            "modifier and select Income for current owners. Preserve and "
            "report authored conflicts. New choices inherit each asset's "
            "staging. Recruitment and equipment rewards are resolved manually."
        ),
        view=seed_territory_boon_choices_view,
        detail_template="admin/maintenance/n26/_seed_territory_boon_choices_detail.html",
    )
)


@task
def remove_published_journal_boons(backfill_id, **said_by_whoever_enqueued_it):
    """Remove unchanged published journal placeholders in a recorded run."""
    from n26.library.published_journal_boons import remove_published_journal_boons

    _run_recorded(
        backfill_id,
        Operation.REMOVE_PUBLISHED_JOURNAL_BOONS,
        "Published journal boon cleanup",
        remove_published_journal_boons,
        (),
    )


def remove_published_journal_boons_view(request):
    """Preview this cleanup independently of the journal content update."""
    from n26.library.published_journal_boons import NOTHING_TO_DO, preview
    from n26.write_pause import SCOPE, exclusive_write_scope

    operation = Operation.REMOVE_PUBLISHED_JOURNAL_BOONS
    address = reverse(f"admin:maintenance_{operation.value}")
    if request.method == "POST":
        with exclusive_write_scope(SCOPE):
            running = running_guard(operation)
            if running is not None:
                messages.warning(request, "That cleanup is already running.")
                return HttpResponseRedirect(
                    reverse("admin:maintenance_backfill_detail", args=[running.id])
                )
            try:
                lines = preview()
            except (
                ObjectDoesNotExist,
                MultipleObjectsReturned,
                ValidationError,
            ) as broke:
                messages.error(request, f"The cleanup cannot run: {broke}")
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
        # Publishing starts delivery immediately, so the run must commit first.
        remove_published_journal_boons.enqueue(backfill_id=str(backfill.id))
        messages.success(request, "The published journal boon cleanup is running.")
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )
    problem = ""
    try:
        lines = preview()
    except (ObjectDoesNotExist, MultipleObjectsReturned, ValidationError) as broke:
        lines, problem = [], str(broke)
    return render(
        request,
        "admin/maintenance/n26/remove_published_journal_boons.html",
        page_context(
            request,
            operation.label,
            preview=lines,
            nothing_to_do=bool(lines) and lines[0] == NOTHING_TO_DO,
            problem=problem,
            apply_url=address,
            recent=Backfill.objects.filter(operation=operation)[:10],
        ),
    )


register_control_operation(
    MaintenanceOperation(
        operation=Operation.REMOVE_PUBLISHED_JOURNAL_BOONS.value,
        name=Operation.REMOVE_PUBLISHED_JOURNAL_BOONS.label,
        added=date(2026, 10, 11),
        description=(
            "Remove the original Goliath Controlled and Escher Controlled "
            "territory modifiers and unused placeholder rules after publication. "
            "Retain edited or archived content, reused modifiers and rules "
            "referenced by content or player history. Preview the exact removals "
            "and skips before applying. Holdings, their history and baseline "
            "Income stay unchanged."
        ),
        view=remove_published_journal_boons_view,
        detail_template="admin/maintenance/n26/_remove_published_journal_boons_detail.html",
    )
)


@task
def delete_test_content(backfill_id, **said_by_whoever_enqueued_it):
    """Delete content with the staff test gangs holding it, using the plan approved on the
    authoring page. The repair rechecks the plan under its locks before deleting player
    data.
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
    """Remove free firing lines and delete the library row when the last affected gang is
    processed. Reconcile and commit each gang separately.
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
    """Repoint references from a duplicate library row to its survivor, one gang at a time,
    then delete the duplicate.
    """
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


#: Authoring tasks that remove firing lines or merge rows process gangs separately;
#: deleting test gangs uses one atomic repair.
AUTHORING_DELETIONS = {
    Operation.DELETE_TEST_CONTENT: delete_test_content,
    Operation.DELETE_FIRING_LINE: delete_firing_line,
    Operation.MERGE_INTO: merge_into,
}


class AnotherRunning(Exception):
    """An operation already has a running record. Reject another run because lock
    contention could acknowledge its delivery without completing its record.
    """


def start_authoring_deletion(plan, user):
    """Record the approved authoring deletion plan and enqueue the matching task, returning
    the record. Raise AnotherRunning if this operation already has a running record;
    execution rechecks the stored plan.
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
    """Return an authoring deletion record by ID, or None if no matching record exists."""
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


def N26TaskRoute(task_function, **kwargs):
    """Declare one task as an n26 writer."""
    return TaskRoute(task_function, write_scope="n26", **kwargs)


def N26PausedTaskRoute(task_function, **kwargs):
    """Declare a maintenance task admitted only for the run and pause generation recorded
    in its delivery.
    """
    return N26TaskRoute(
        task_function,
        paused_consumer=PausedTaskConsumer(
            run_id_kwarg="backfill_id",
            generation_kwarg="pause_generation",
        ),
        **kwargs,
    )


def _enqueue_counter_history(record, generation):
    transaction.on_commit(
        lambda: activate_counter_history.enqueue(
            backfill_id=str(record.pk), pause_generation=generation
        )
    )


def start_counter_history(actor):
    """Drain n26 writers and record the explicitly requested activation."""
    from n26.core.counter_activation import ActivationRefused, preview
    from n26.core.counter_tracking import is_active
    from n26.write_pause import (
        SCOPE,
        exclusive_write_scope,
        pause_scope,
    )

    with exclusive_write_scope(SCOPE) as pause:
        if is_active():
            raise ActivationRefused("Counter history is already active.")
        if pause.state != "OPEN":
            reason = pause.reason or "No reason was recorded."
            raise ActivationRefused(
                f"n26 writes are already paused: {reason} Resume that pause before "
                "starting counter history activation."
            )
        counts = preview()
        if counts["without_gang"]:
            raise ActivationRefused("Repair counters without a gang before activation.")
        if counts["structured_events"]:
            raise ActivationRefused(
                "Structured counter history already exists. Review it before starting activation."
            )
        record = Backfill.objects.create(
            operation=Operation.ACTIVATE_COUNTER_HISTORY,
            triggered_by=actor,
            status=Backfill.Status.RUNNING,
            summary={
                "phase": "checkpoint",
                "preview": counts,
                "readiness_confirmed_at": timezone.now().isoformat(),
            },
        )
        task_name = COUNTER_HISTORY_TASK_PATH
        pause = pause_scope(
            SCOPE,
            actor=actor,
            reason="Changes are paused while counter history is activated.",
            permitted_task_name=task_name,
            permitted_run_id=str(record.pk),
        )
        record.summary["pause_generation"] = pause.generation
        record.save(update_fields=["summary", "modified"])
        _enqueue_counter_history(record, pause.generation)
        return record


def _counter_history_run(pause, run_id, generation):
    from n26.core.counter_activation import ActivationRefused

    if (
        pause.state != "PAUSED"
        or pause.permitted_task_name != COUNTER_HISTORY_TASK_PATH
        or pause.permitted_run_id != str(run_id)
        or str(pause.generation) != str(generation)
    ):
        raise ActivationRefused("The write pause changed. Reload this page.")
    try:
        return Backfill.objects.select_for_update().get(
            pk=run_id, operation=Operation.ACTIVATE_COUNTER_HISTORY
        )
    except Backfill.DoesNotExist as exc:
        raise ActivationRefused(
            "The maintenance run no longer exists. n26 writes remain paused."
        ) from exc


def restart_counter_history(run_id, generation, *, cleanup=False):
    """Drain the old delivery before changing or retrying this run's work."""
    from n26.core.counter_activation import ActivationRefused
    from n26.core.counter_tracking import is_active
    from n26.write_pause import SCOPE, exclusive_write_scope

    with exclusive_write_scope(SCOPE) as pause:
        record = _counter_history_run(pause, run_id, generation)
        if cleanup and is_active():
            raise ActivationRefused("Counter history is active and cannot be cleared.")
        phase = "cleanup" if cleanup else record.summary["phase"]
        record.status = Backfill.Status.RUNNING
        record.error = ""
        record.summary = {
            "phase": phase,
            "preview": record.summary["preview"],
            "readiness_confirmed_at": record.summary["readiness_confirmed_at"],
            "pause_generation": pause.generation,
        }
        record.save()
        _enqueue_counter_history(record, pause.generation)
        return record


def resume_after_counter_history(run_id, generation, actor):
    """Reopen only after activation or a complete cleanup of this run."""
    from n26.core.counter_activation import ActivationRefused
    from n26.core.models import CounterTracking, LedgerEvent
    from n26.write_pause import (
        SCOPE,
        exclusive_write_scope,
        release_paused_consumer,
        resume_scope,
    )

    with exclusive_write_scope(SCOPE) as pause:
        record = _counter_history_run(pause, run_id, generation)
        if record.status != Backfill.Status.DONE:
            raise ActivationRefused(
                "Wait for the maintenance run to finish before resuming writes."
            )
        active = CounterTracking.objects.filter(activated_at__isnull=False).first()
        if record.summary["phase"] == "cleanup":
            if (
                active
                or LedgerEvent.objects.filter(
                    batch=record.pk, kind=LedgerEvent.Kind.COUNTER_CHECKPOINTED
                ).exists()
            ):
                raise ActivationRefused("Checkpoint cleanup has not finished.")
        elif active is None or str(active.activation_run) != str(record.pk):
            raise ActivationRefused("Counter history has not passed validation.")
        release_paused_consumer(
            SCOPE,
            generation=pause.generation,
            task_name=COUNTER_HISTORY_TASK_PATH,
            run_id=str(record.pk),
        )
        resume_scope(SCOPE, generation=pause.generation, actor=actor)


@task
def activate_counter_history(backfill_id, pause_generation):
    from n26.core.counter_activation import (
        ActivationRefused,
        checkpoint_gang,
        cleanup_gang,
        plan,
    )

    record = Backfill.objects.get(
        pk=backfill_id, operation=Operation.ACTIVATE_COUNTER_HISTORY
    )
    if record.status != Backfill.Status.RUNNING:
        return
    cleanup = record.summary["phase"] == "cleanup"
    apply = cleanup_gang if cleanup else checkpoint_gang
    run_per_gang(
        backfill_id,
        operation=Operation.ACTIVATE_COUNTER_HISTORY,
        what="Counter checkpoint cleanup" if cleanup else "Counter history activation",
        find=lambda: plan(backfill_id, pause_generation, cleanup=cleanup),
        apply_one=lambda gang_id: apply(gang_id, backfill_id, pause_generation),
        again=lambda: activate_counter_history.enqueue(
            backfill_id=backfill_id, pause_generation=pause_generation
        ),
        refusals=(ActivationRefused,),
    )


COUNTER_HISTORY_TASK_PATH = "n26.maintenance.activate_counter_history"


def counter_history_view(request):
    from n26.core.counter_activation import ActivationRefused, preview
    from n26.core.counter_tracking import is_active
    from n26.write_pause import SCOPE, WritesPaused, pause_status

    problem = ""
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "activate":
                if request.POST.get("ready") != "confirmed":
                    raise ActivationRefused(
                        "Confirm that every serving web and task revision supports activation and that its task route is provisioned."
                    )
                start_counter_history(request.user)
                messages.success(
                    request,
                    "Counter history activation started. Writes remain paused until you resume them.",
                )
            elif action in {"retry", "cleanup"}:
                restart_counter_history(
                    request.POST.get("run_id"),
                    request.POST.get("generation"),
                    cleanup=action == "cleanup",
                )
                messages.success(
                    request, "Counter history maintenance queued. Writes remain paused."
                )
            elif action == "resume":
                resume_after_counter_history(
                    request.POST.get("run_id"),
                    request.POST.get("generation"),
                    request.user,
                )
                messages.success(request, "n26 writes resumed.")
            else:
                raise ActivationRefused("Choose one of the actions on this page.")
        except (ActivationRefused, WritesPaused) as exc:
            problem = str(exc)
        else:
            return HttpResponseRedirect(request.path)

    pause = pause_status(SCOPE)
    run = (
        Backfill.objects.filter(
            pk=pause.permitted_run_id,
            operation=Operation.ACTIVATE_COUNTER_HISTORY,
        ).first()
        if pause.permitted_task_name == COUNTER_HISTORY_TASK_PATH
        and pause.permitted_run_id
        else None
    )
    return render(
        request,
        "admin/maintenance/n26/counter_history.html",
        page_context(
            request,
            "Activate counter history",
            pause=pause,
            run=run,
            active=is_active(),
            counts=preview(),
            problem=problem,
        ),
    )


register_control_operation(
    MaintenanceOperation(
        operation=Operation.ACTIVATE_COUNTER_HISTORY.value,
        name=Operation.ACTIVATE_COUNTER_HISTORY.label,
        added=date(2026, 9, 16),
        description=(
            "Pause n26 writes, record every counter's current balance, and check "
            "counter history before activating it. Resume writes after the job finishes."
        ),
        view=counter_history_view,
    )
)


def _require_prelaunch_cycle_flag_off(*, lock=True):
    from gyrinx.site.models import Availability, FeatureFlag
    from n26.core.cycle_reset import ResetRefused
    from n26.flags import CYCLE_TRACKING

    flags = FeatureFlag.objects.filter(slug=CYCLE_TRACKING)
    if lock:
        flags = flags.select_for_update()
    configured = flags.first()
    if configured is not None and configured.availability != Availability.OFF:
        raise ResetRefused(
            "Turn campaign cycles off before resetting prelaunch cycle data."
        )


@task
def reset_prelaunch_campaign_cycles(backfill_id, **unused):
    from n26.core.cycle_reset import ResetRefused, apply

    if not Backfill.objects.filter(
        pk=backfill_id, operation=Operation.RESET_PRELAUNCH_CAMPAIGN_CYCLES
    ).exists():
        return

    _run_recorded(
        backfill_id,
        Operation.RESET_PRELAUNCH_CAMPAIGN_CYCLES,
        "Prelaunch campaign cycle reset",
        lambda: apply(
            _approved_plan(backfill_id),
            require_disabled=_require_prelaunch_cycle_flag_off,
        ),
        (ResetRefused,),
    )


PRELAUNCH_CYCLE_RESET_WORDS = {
    "intro": (
        "Remove the captured prelaunch campaign schedules, plans, cycles, phases and transitions. "
        "Clear cycle attribution from battles, actions and ledger events while keeping their "
        "other facts and financial totals. Keep templates, battle and action receipts, notifications "
        "and campaign events. Old cycle command keys are retained and cannot replay their changes. "
        "Campaign cycles must be off. A completed reset cannot capture later schedules."
    ),
    "nothing_heading": "Nothing to reset",
    "nothing_words": "No prelaunch campaign cycle data was found.",
    "refuses_heading": "The reset cannot run",
    "button": "Reset the captured cycle data",
    "confirm": "Remove this prelaunch cycle data and clear its attribution? This cannot be undone.",
}


def reset_prelaunch_campaign_cycles_view(request):
    from n26.core.cycle_reset import ResetRefused, empty_plan, find
    from n26.write_pause import SCOPE, exclusive_write_scope

    operation = Operation.RESET_PRELAUNCH_CAMPAIGN_CYCLES
    address = reverse(f"admin:maintenance_{operation.value}")
    signer = signing.Signer(salt="n26.prelaunch-cycle-reset")
    completed = Backfill.objects.filter(
        operation=operation, status=Backfill.Status.DONE
    ).first()
    if request.method == "POST":
        try:
            with exclusive_write_scope(SCOPE):
                completed = Backfill.objects.filter(
                    operation=operation, status=Backfill.Status.DONE
                ).first()
                running = running_guard(operation)
                if completed is not None or running is not None:
                    record = completed or running
                    return HttpResponseRedirect(
                        reverse("admin:maintenance_backfill_detail", args=[record.pk])
                    )
                _require_prelaunch_cycle_flag_off()
                plan = find()
                if plan.nothing_here:
                    messages.info(
                        request, "No prelaunch campaign cycle data was found."
                    )
                    return HttpResponseRedirect(address)
                try:
                    approved = signer.unsign(request.GET.get("scope", ""))
                except signing.BadSignature:
                    raise ResetRefused(
                        "Prepare and review a prelaunch cycle reset preview first."
                    ) from None
                if approved != plan.fingerprint:
                    raise ResetRefused(
                        "Campaign cycle data changed after the preview. Prepare and review a new preview."
                    )
                record = Backfill.objects.create(
                    operation=operation,
                    triggered_by=request.user,
                    status=Backfill.Status.RUNNING,
                    summary={
                        "preview": list(plan.preview()),
                        "attempts": 0,
                        **plan.recorded(),
                    },
                )
            reset_prelaunch_campaign_cycles.enqueue(backfill_id=str(record.pk))
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[record.pk])
            )
        except (ResetRefused, WritesPaused) as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(address)
    plan = empty_plan() if completed is not None else find()
    if completed is None:
        try:
            _require_prelaunch_cycle_flag_off(lock=False)
        except ResetRefused as exc:
            plan = replace(plan, problems=(str(exc),))
    words = dict(PRELAUNCH_CYCLE_RESET_WORDS)
    if completed is not None:
        words["nothing_words"] = (
            "This reset has already finished. Later schedules are kept."
        )
    return render(
        request,
        "admin/maintenance/n26/delete.html",
        page_context(
            request,
            operation.label,
            plan=plan,
            preview=list(plan.preview()),
            words=words,
            apply_url=address
            + "?"
            + urlencode({"scope": signer.sign(plan.fingerprint)}),
            recent=Backfill.objects.filter(operation=operation)[:10],
        ),
    )


register_control_operation(
    MaintenanceOperation(
        operation=Operation.RESET_PRELAUNCH_CAMPAIGN_CYCLES.value,
        name=Operation.RESET_PRELAUNCH_CAMPAIGN_CYCLES.label,
        added=date(2026, 11, 13),
        description=PRELAUNCH_CYCLE_RESET_WORDS["intro"],
        view=reset_prelaunch_campaign_cycles_view,
    )
)


#: The task registry imports these routes through n26/core/tasks.py. Keep long-running
#: acknowledgement deadlines aligned with the deployed request timeout (--timeout in
#: cloudbuild.yaml) to avoid redelivery while work still holds its lock. Cloud Scheduler
#: provisions the propagation sweep; the local backend does not run schedules.
task_routes = [
    N26TaskRoute(
        reset_prelaunch_campaign_cycles, exclusive_write=True, ack_deadline=600
    ),
    N26TaskRoute(repair_campaign_reputation, ack_deadline=600),
    N26TaskRoute(reset_spyrer_built_ins, ack_deadline=600),
    N26PausedTaskRoute(activate_counter_history, ack_deadline=600),
    N26TaskRoute(delete_test_content, ack_deadline=600, min_retry_delay=60),
    N26TaskRoute(delete_firing_line, ack_deadline=600, min_retry_delay=60),
    N26TaskRoute(merge_into, ack_deadline=600, min_retry_delay=60),
    N26TaskRoute(delete_nameless_gang_type, ack_deadline=600, min_retry_delay=60),
    N26TaskRoute(convert_outcast_affiliation, ack_deadline=600, min_retry_delay=60),
    N26TaskRoute(convert_chaos_god, ack_deadline=600, min_retry_delay=60),
    N26TaskRoute(convert_variant, ack_deadline=600, min_retry_delay=60),
    N26TaskRoute(propagate_built_ins, ack_deadline=600),
    N26TaskRoute(sweep_built_in_propagations, schedule="*/5 * * * *"),
    N26TaskRoute(audit_reconcile),
    N26TaskRoute(repair_doubled_refunds, ack_deadline=600, min_retry_delay=60),
    N26TaskRoute(backfill_built_ins, ack_deadline=600),
    N26TaskRoute(drop_duplicate_grants, ack_deadline=600),
    N26TaskRoute(rehost_gang_picks, ack_deadline=600, min_retry_delay=60),
    N26TaskRoute(repoint_champion_picks, ack_deadline=600, min_retry_delay=60),
    N26TaskRoute(
        delete_legacy_affiliation_assignments,
        ack_deadline=600,
        min_retry_delay=60,
    ),
    N26TaskRoute(delete_empty_affiliations, ack_deadline=600, min_retry_delay=60),
    N26TaskRoute(open_founding_actions, ack_deadline=600),
    N26TaskRoute(
        seed_journal_content,
        exclusive_write=True,
        ack_deadline=600,
        min_retry_delay=60,
    ),
    N26TaskRoute(
        seed_territory_boons,
        exclusive_write=True,
        ack_deadline=600,
        min_retry_delay=60,
    ),
    N26TaskRoute(
        seed_territory_boon_choices,
        exclusive_write=True,
        ack_deadline=600,
        min_retry_delay=60,
    ),
    N26TaskRoute(
        remove_published_journal_boons,
        exclusive_write=True,
        ack_deadline=600,
        min_retry_delay=60,
    ),
    N26TaskRoute(clear_item_restrictions, ack_deadline=600, min_retry_delay=60),
    N26TaskRoute(order_collections, ack_deadline=600, min_retry_delay=60),
    N26TaskRoute(initialise_action_allowances, ack_deadline=600),
    N26TaskRoute(preview_action_allowances, ack_deadline=600),
]


# Keep completed, non-recurring operations registered without a view so historical
# records retain their labels.
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
