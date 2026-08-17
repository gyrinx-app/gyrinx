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

__all__ = ["Operation", "convert_specialisation", "task_routes"]

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


def _plan():
    from n26.library.conversion import plan_specialisation

    return plan_specialisation()


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


@task
def convert_specialisation(backfill_id, keep=True):
    """Run the Specialisation conversion, once, and write down the outcome.

    With ``keep=False`` it rehearses: the whole conversion performed and
    every page proven, then unwound on purpose, so a database holding
    real gangs can be asked whether this works without being changed by
    the answer.

    Never raises: a task that fails is redelivered, and there is nowhere
    for a raised error to go but round again. Every ending — refused,
    broken, already running — is recorded on the audit record instead.
    """
    from n26.library.conversion import ConversionRefused, apply

    # The lock comes first, and nothing is recorded before it is held. A
    # redelivery arriving while the first copy is still working must leave
    # no trace at all: count its arrival as an attempt and a long run could
    # be declared failed out from under itself.
    with _single_flight() as mine:
        if not mine:
            logger.info(
                "Specialisation conversion already running; this copy stands down"
            )
            return

        may_start, why_not = _claim(backfill_id)
        if not may_start:
            logger.info("Specialisation conversion not started: %s", why_not)
            _write(
                backfill_id,
                status=Backfill.Status.FAILED,
                error=f"Not started: {why_not}",
            )
            return

        try:
            report = apply(_plan(), keep=keep)
        except ConversionRefused as refused:
            # A refusal is the discipline working: nothing was written,
            # and the reason is already in words.
            _write(backfill_id, status=Backfill.Status.FAILED, error=str(refused))
            return
        except Exception as broke:  # noqa: BLE001 — the ending must be recorded
            logger.exception("Specialisation conversion broke")
            _write(
                backfill_id,
                status=Backfill.Status.FAILED,
                error=f"{broke}\n\n{traceback.format_exc()}",
            )
            return

        _write(
            backfill_id,
            status=Backfill.Status.DONE,
            summary_patch={"report": list(report), "kept": bool(keep)},
        )


def convert_specialisation_view(request):
    if request.method == "POST":
        running = running_guard(Operation.CONVERT_SPECIALISATION)
        if running is not None:
            messages.warning(request, "That conversion is already running.")
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[running.id])
            )
        plan = _plan()
        if plan.nothing_here:
            # A page left open across someone else's run, most likely.
            # Recording a run that would do nothing only clutters the
            # history of what was really done.
            messages.info(request, "There is nothing to convert.")
            return HttpResponseRedirect(
                reverse("admin:maintenance_n26_convert_specialisation")
            )
        if not plan.ok:
            # Refusing here rather than in the task keeps the reason on
            # the screen of whoever asked for it.
            messages.error(
                request, "The conversion refuses: " + "; ".join(plan.problems)
            )
            return HttpResponseRedirect(
                reverse("admin:maintenance_n26_convert_specialisation")
            )
        # Keeping the work is the thing that must be asked for. A request
        # that does not say so — a page from before there were two
        # buttons, something calling the address directly — rehearses,
        # which is the ending nobody has to undo.
        keep = request.POST.get("keep") == "yes"
        backfill = Backfill.objects.create(
            operation=Operation.CONVERT_SPECIALISATION,
            triggered_by=request.user,
            status=Backfill.Status.RUNNING,
            summary={"preview": list(plan.preview()), "attempts": 0, "kept": keep},
        )
        convert_specialisation.enqueue(backfill_id=str(backfill.id), keep=keep)
        messages.success(
            request,
            "The conversion is running. This page shows what it did."
            if keep
            else "The rehearsal is running. Nothing will be kept.",
        )
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )

    plan = _plan()
    context = page_context(
        request,
        Operation.CONVERT_SPECIALISATION.label,
        plan=plan,
        preview=list(plan.preview()),
        gangs=len(plan.gang_ids),
        apply_url=reverse("admin:maintenance_n26_convert_specialisation"),
        recent=Backfill.objects.filter(operation=Operation.CONVERT_SPECIALISATION)[:10],
    )
    return render(request, "admin/maintenance/n26/convert_specialisation.html", context)


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

#: Declared for the task registry, which reads this from ``n26/core/tasks.py``.
#: The deadline is the longest Pub/Sub allows, because a conversion holds one
#: transaction for as long as proving every affected gang takes. It is also
#: the request timeout the service is deployed with, and the two belong
#: together: a run outliving its deadline is delivered again while the first
#: copy is still working, and the second — standing down at the lock — answers
#: successfully and acknowledges the message out from under it. Change one and
#: change the other (``--timeout`` in ``cloudbuild.yaml``).
task_routes = [TaskRoute(convert_specialisation, ack_deadline=600, min_retry_delay=60)]
