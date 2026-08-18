"""The repairs this edition offers the maintenance console, and the one
door it offers them through.

The console is the site's: a superuser-gated index, one audit record per
run, a detail page, a cancel button. What there is to repair is edition
knowledge, so an edition registers its own operations rather than the
console knowing about either of them. This module is the whole of n26's
dependency on it — the registry, the audit record, the page furniture and
the background-task route are imported here and nowhere else in ``n26/``,
so the seam can be read and moved in one place.

What it registers today is the Specialisation conversion. A conversion
moves a hand-built choice system onto slots and picks and proves, before
committing, that every affected gang's pages still say the same things;
:mod:`n26.library.conversion` owns that discipline entirely, and this
module only gives it somewhere to be triggered from and somewhere to
write down what happened.

Conversions do not travel as migrations. A migration that runs live code
inherits a dependency on every column that code will ever read, and the
pin needed to express that contradicts the recorded history of any
database that already ran it — so they run after a deploy instead, on a
schema that is fully migrated by construction.

The run is one transaction, and it is deliberately all-or-nothing: the
carrier swap changes every affected page at the same instant, so there is
no gang-by-gang chunking to be had. That shapes everything here. A run
that is interrupted — a killed request, a lost connection — rolls back
whole, so an interrupted conversion is a no-op that can simply be run
again, never a half-converted library. Delivery is at-least-once, so two
guards stand between that promise and a second copy running alongside the
first: a lock only one run can hold, and a cap on how many times an
attempt may be started before the record gives up and says so.
"""

import logging
import traceback
from contextlib import contextmanager

from django.contrib import messages
from django.db import connection, models, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.tasks import task
from django.urls import reverse

from gyrinx.maintenance.models import Backfill
from gyrinx.maintenance.registry import MaintenanceOperation, register_operation
from gyrinx.maintenance.views import page_context, running_guard
from gyrinx.tasks import TaskRoute

logger = logging.getLogger(__name__)

__all__ = [
    "Operation",
    "convert_skill_tree",
    "convert_specialisation",
    "merge_wargear_into_weapon_view",
    "task_routes",
]

#: How many times a run may be started before the record gives up. A
#: conversion that exhausts the request budget leaves nothing behind and
#: is redelivered, so without a cap a run too large to finish would
#: repeat for ever, each attempt paying the whole cost again.
MAX_ATTEMPTS = 2

#: The lock a run holds for as long as it is working. Postgres releases
#: it when the connection goes, so a killed run frees it without anyone
#: intervening.
LOCK_KEY = 826_020_601


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
    MERGE_WARGEAR_INTO_WEAPON = (
        "n26_merge_wargear_into_weapon",
        "n26: duplicated wargear becomes its weapon",
    )


def _write(backfill_id, *, status=None, summary_patch=None, error=""):
    """Record what happened, under the row's own lock.

    A record that has reached an ending keeps it. Only one copy of a run
    ever works — the lock sees to that — so whatever wrote the ending was
    the run itself, and anything arriving afterwards is a redelivery with
    nothing new to say. A long run finishes close to the moment its
    delivery is retried, so the copy that finds the work already done is
    the likely case, not the exotic one: were it allowed to write, it
    would file a successful conversion as a failure.

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
def _single_flight():
    """Hold the lock for the length of a run, or yield False.

    Postgres frees an advisory lock when the connection goes, so a run
    killed mid-flight leaves nothing to clean up by hand.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_KEY])
        held = cursor.fetchone()[0]
    try:
        yield held
    finally:
        if held:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_KEY])


def _claim(backfill_id):
    """Count this attempt and say whether it may start.

    Written outside the conversion's own transaction, so the count
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
                f"started {attempts} times without finishing — each attempt "
                "left nothing behind. The conversion needs longer than one "
                "request allows; raise the limit before running it again."
            )
        return True, ""


def _run_conversion(backfill_id, plan_with, what, **said_by_whoever_enqueued_it):
    """Run one conversion, once, and write down the outcome.

    Takes whatever else it is handed and ignores it. Delivery outlives a
    deploy, so a message can arrive naming arguments the version that
    enqueued it had and this one does not — and a task that refuses its
    own message is retried for ever, there being nowhere for it to go.

    Never raises: a task that fails is redelivered, and there is nowhere
    for a raised error to go but round again. Every ending — refused,
    broken, already running — is recorded on the audit record instead.
    """
    from n26.library.conversion import ConversionRefused, apply

    # A message from a version that could be told not to keep its work.
    # Ignoring the instruction would turn the careful thing somebody asked
    # for into the committing one, which is the opposite of what they
    # wanted; there is no rehearsing any more, so the honest answer is to
    # decline it.
    if said_by_whoever_enqueued_it.get("keep") is False:
        _write(
            backfill_id,
            status=Backfill.Status.FAILED,
            error=(
                "This asked to be rehearsed and then thrown away, which this "
                "version cannot do. Nothing was run. Ask for it again from "
                "the page."
            ),
        )
        return

    # The lock comes first, and nothing is recorded before it is held. A
    # redelivery arriving while the first copy is still working must leave
    # no trace at all: count its arrival as an attempt and a long run could
    # be declared failed out from under itself.
    with _single_flight() as mine:
        if not mine:
            logger.info("%s conversion already running; this copy stands down", what)
            return

        may_start, why_not = _claim(backfill_id)
        if not may_start:
            logger.info("%s conversion not started: %s", what, why_not)
            _write(
                backfill_id,
                status=Backfill.Status.FAILED,
                error=f"Not started: {why_not}",
            )
            return

        try:
            report = apply(plan_with())
        except ConversionRefused as refused:
            # A refusal is the discipline working: nothing was written,
            # and the reason is already in words.
            _write(backfill_id, status=Backfill.Status.FAILED, error=str(refused))
            return
        except Exception as broke:  # noqa: BLE001 — the ending must be recorded
            logger.exception("%s conversion broke", what)
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


def _plan_specialisation():
    from n26.library.conversion import plan_specialisation

    return plan_specialisation()


def _plan_skill_tree():
    from n26.library.conversion import plan_skill_tree

    return plan_skill_tree()


@task
def convert_specialisation(backfill_id, **said_by_whoever_enqueued_it):
    """The Specialisation conversion, as a task — see ``_run_conversion``."""
    _run_conversion(
        backfill_id,
        _plan_specialisation,
        "Specialisation",
        **said_by_whoever_enqueued_it,
    )


@task
def convert_skill_tree(backfill_id, **said_by_whoever_enqueued_it):
    """The Skill Tree conversion, as a task — see ``_run_conversion``."""
    _run_conversion(
        backfill_id,
        _plan_skill_tree,
        "Skill tree",
        **said_by_whoever_enqueued_it,
    )


def _conversion_view(request, operation, plan_with, task_fn):
    """Preview a conversion (GET), or record a run and enqueue it (POST)."""
    address = reverse(f"admin:maintenance_{operation.value}")
    if request.method == "POST":
        running = running_guard(operation)
        if running is not None:
            messages.warning(request, "That conversion is already running.")
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[running.id])
            )
        plan = plan_with()
        if plan.nothing_here:
            # A page left open across someone else's run, most likely.
            # Recording a run that would do nothing only clutters the
            # history of what was really done.
            messages.info(request, "There is nothing to convert.")
            return HttpResponseRedirect(address)
        if not plan.ok:
            # Refusing here rather than in the task keeps the reason on
            # the screen of whoever asked for it.
            messages.error(
                request, "The conversion refuses: " + "; ".join(plan.problems)
            )
            return HttpResponseRedirect(address)
        if request.POST.get("keep") == "no":
            # A page open since before the rehearsal was taken away. Its
            # gentler button would land here and convert for real.
            messages.warning(
                request,
                "That page offered a rehearsal, which no longer exists. "
                "Nothing has been run — reload and apply if you mean to.",
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

    plan = plan_with()
    context = page_context(
        request,
        operation.label,
        plan=plan,
        preview=list(plan.preview()),
        # Two different numbers, and confusing them on a page with an
        # apply button would tell an operator the change is smaller than
        # it is: one is how many gangs it reaches, the other how many of
        # them it proves before committing.
        reaches=plan.reaches,
        proven=len(plan.gang_ids),
        apply_url=address,
        recent=Backfill.objects.filter(operation=operation)[:10],
    )
    return render(request, "admin/maintenance/n26/convert.html", context)


def convert_specialisation_view(request):
    return _conversion_view(
        request,
        Operation.CONVERT_SPECIALISATION,
        _plan_specialisation,
        convert_specialisation,
    )


def convert_skill_tree_view(request):
    return _conversion_view(
        request,
        Operation.CONVERT_SKILL_TREE,
        _plan_skill_tree,
        convert_skill_tree,
    )


register_operation(
    MaintenanceOperation(
        operation=Operation.CONVERT_SPECIALISATION.value,
        name=Operation.CONVERT_SPECIALISATION.label,
        description=(
            "Move the specialisations onto slots and picks: the Specialist "
            "subtype grants a slot instead of offering a choice, and every "
            "stored choice is re-said as a pick. Proves every affected "
            "gang's pages read the same, or writes nothing."
        ),
        view=convert_specialisation_view,
        detail_template="admin/maintenance/n26/_convert_detail.html",
    )
)

register_operation(
    MaintenanceOperation(
        operation=Operation.CONVERT_SKILL_TREE.value,
        name=Operation.CONVERT_SKILL_TREE.label,
        description=(
            "Move the Venator ranked skill trees onto slots and picks: each "
            "rank carrier grants a slot instead of offering a choice, and "
            "every stored choice is re-said as a pick. Proves every affected "
            "gang's pages read the same, or writes nothing."
        ),
        view=convert_skill_tree_view,
        detail_template="admin/maintenance/n26/_convert_detail.html",
    )
)

#: Declared for the task registry, which reads this from ``n26/core/tasks.py``.
#: The deadline is the longest Pub/Sub allows, because a conversion holds one
#: transaction for as long as proving its spread of gangs takes. It is also
#: the request timeout the service is deployed with, and the two belong
#: together: a run outliving its deadline is delivered again while the first
#: copy is still working, and the second — standing down at the lock — answers
#: successfully and acknowledges the message out from under it. Change one and
#: change the other (``--timeout`` in ``cloudbuild.yaml``).
task_routes = [
    TaskRoute(convert_specialisation, ack_deadline=600, min_retry_delay=60),
    TaskRoute(convert_skill_tree, ack_deadline=600, min_retry_delay=60),
]


def merge_wargear_into_weapon_view(request):
    """Preview the merge, or perform it.

    Small enough to answer in the request, unlike the conversion above: a
    few hundred rows move, and what proves the run is a reconcile per
    affected gang rather than a render of every page.
    """
    from n26.library.repair import Refused, apply, find_candidates, gangs_holding

    address = reverse("admin:maintenance_n26_merge_wargear_into_weapon")
    if request.method == "POST":
        try:
            result = apply()
        except Refused as refused:
            # The repair unwound itself rather than move a number it must
            # not. Nothing was written, and the reason is already in words.
            Backfill.objects.create(
                operation=Operation.MERGE_WARGEAR_INTO_WEAPON,
                triggered_by=request.user,
                status=Backfill.Status.FAILED,
                error=str(refused),
            )
            messages.error(request, f"The repair refuses: {refused}")
            return HttpResponseRedirect(address)
        except Exception as broke:  # noqa: BLE001 — the ending must be recorded
            logger.exception("Wargear merge broke")
            Backfill.objects.create(
                operation=Operation.MERGE_WARGEAR_INTO_WEAPON,
                triggered_by=request.user,
                status=Backfill.Status.FAILED,
                error=f"{broke}\n\n{traceback.format_exc()}",
            )
            messages.error(request, f"The repair failed: {broke}")
            return HttpResponseRedirect(address)

        if not result.merged:
            # A page left open across someone else's run, most likely.
            # Recording a run that did nothing only clutters the history.
            messages.info(request, "There is nothing to merge.")
            return HttpResponseRedirect(address)

        backfill = Backfill.objects.create(
            operation=Operation.MERGE_WARGEAR_INTO_WEAPON,
            triggered_by=request.user,
            status=Backfill.Status.DONE,
            summary=result.as_dict(),
        )
        messages.success(
            request,
            f"Merged {len(result.merged)} piece(s) of gear across "
            f"{result.gangs} gang(s).",
        )
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )

    candidates = find_candidates()
    merges = [c for c in candidates if c.merges]
    context = page_context(
        request,
        Operation.MERGE_WARGEAR_INTO_WEAPON.label,
        merges=merges,
        skips=[c for c in candidates if not c.merges],
        entries=sum(c.entries for c in merges),
        assignments=sum(c.assignments for c in merges),
        gangs=len(gangs_holding(merges)),
        apply_url=address,
        recent=Backfill.objects.filter(
            operation=Operation.MERGE_WARGEAR_INTO_WEAPON
        ).order_by("-created")[:10],
    )
    return render(
        request, "admin/maintenance/n26/merge_wargear_into_weapon.html", context
    )


register_operation(
    MaintenanceOperation(
        operation=Operation.MERGE_WARGEAR_INTO_WEAPON.value,
        name=Operation.MERGE_WARGEAR_INTO_WEAPON.label,
        description=(
            "Some gear is stored twice — once as wargear, once as the "
            "weapon carrying its firing line — so it lists twice and the "
            "wargear copy prints no statline. Moves the equipment lists "
            "and the purchases onto the weapon and drops the wargear row. "
            "Moves no money, and proves it gang by gang."
        ),
        view=merge_wargear_into_weapon_view,
        detail_template="admin/maintenance/n26/_merge_wargear_detail.html",
    )
)
