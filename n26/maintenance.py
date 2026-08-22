"""The repairs this edition offers the maintenance console, and the one
door it offers them through.

The console is the site's: a superuser-gated index, one audit record per
run, a detail page, a cancel button. What there is to repair is edition
knowledge, so an edition registers its own operations rather than the
console knowing about either of them. This module is the whole of n26's
dependency on it — the registry, the audit record, the page furniture and
the background-task route are imported here and nowhere else in ``n26/``,
so the seam can be read and moved in one place.

Most of what it registers is conversions. A conversion moves a
hand-built choice system onto slots and picks and proves, before
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
from datetime import date

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
    "clear_spare_answers",
    "convert_archetype",
    "sweep_archived",
    "convert_gang_legacy",
    "convert_skill_tree",
    "convert_specialisation",
    "delete_nameless_gang_type",
    "delete_retired_kinds",
    "retire_gang_legacy_pilot",
    "task_routes",
]

#: How many times a run may be started before the record gives up. A
#: conversion that exhausts the request budget leaves nothing behind and
#: is redelivered, so without a cap a run too large to finish would
#: repeat for ever, each attempt paying the whole cost again.
MAX_ATTEMPTS = 2

#: The locks a run holds for as long as it is working — one per
#: operation, declared beside their operations below. A lock fences the
#: redeliveries of one operation's own run; shared between operations it
#: would do worse than fence: the view's running-guard only sees its own
#: operation's records, so one conversion could enqueue while another
#: held the lock, stand down there without writing, acknowledge its
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


#: See the note on locks above: one per operation, never shared.
LOCK_KEYS = {
    Operation.CONVERT_SPECIALISATION: 826_020_601,
    Operation.CONVERT_SKILL_TREE: 826_020_602,
    Operation.CONVERT_GANG_LEGACY: 826_020_603,
    Operation.RETIRE_GANG_LEGACY_PILOT: 826_020_604,
    Operation.CONVERT_ARCHETYPE: 826_020_605,
    Operation.DELETE_NAMELESS_GANG_TYPE: 826_020_606,
    Operation.SWEEP_ARCHIVED: 826_020_607,
    Operation.CLEAR_SPARE_ANSWERS: 826_020_608,
    Operation.DELETE_RETIRED_KINDS: 826_020_609,
}


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


def _plan(system):
    from n26.library.conversion import SYSTEMS

    return SYSTEMS[system]()


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
def convert_specialisation(backfill_id, **said_by_whoever_enqueued_it):
    """The Specialisation conversion, as a task — see ``_run_conversion``."""
    _run_conversion(
        backfill_id,
        Operation.CONVERT_SPECIALISATION,
        "specialisation",
        **said_by_whoever_enqueued_it,
    )


@task
def convert_skill_tree(backfill_id, **said_by_whoever_enqueued_it):
    """The Skill Tree conversion, as a task — see ``_run_conversion``."""
    _run_conversion(
        backfill_id,
        Operation.CONVERT_SKILL_TREE,
        "skill_tree",
        **said_by_whoever_enqueued_it,
    )


@task
def convert_gang_legacy(backfill_id, **said_by_whoever_enqueued_it):
    """The Gang Legacy conversion, as a task — see ``_run_conversion``."""
    _run_conversion(
        backfill_id,
        Operation.CONVERT_GANG_LEGACY,
        "gang_legacy",
        **said_by_whoever_enqueued_it,
    )


@task
def convert_archetype(backfill_id, **said_by_whoever_enqueued_it):
    """The Archetype conversion, as a task — see ``_run_conversion``."""
    _run_conversion(
        backfill_id,
        Operation.CONVERT_ARCHETYPE,
        "archetype",
        **said_by_whoever_enqueued_it,
    )


@task
def sweep_archived(backfill_id, **said_by_whoever_enqueued_it):
    """Rewrite the archived answers, once, and write down the outcome.

    The same runner as a conversion, over a plan and apply of its own:
    what it proves is the history rather than the pages, an answer
    already taken back drawing nothing on either.
    """
    from n26.library.conversion import ConversionRefused
    from n26.library.conversion.archived import apply_archived, plan_archived

    _run_recorded(
        backfill_id,
        Operation.SWEEP_ARCHIVED,
        "Archived answers sweep",
        lambda: apply_archived(plan_archived()),
        ConversionRefused,
    )


@task
def retire_gang_legacy_pilot(backfill_id, **said_by_whoever_enqueued_it):
    """Retire the Gang Legacy slot pilot, once, and write down the outcome.

    The same runner discipline as a conversion — the lock, the claim,
    every ending recorded — but the work is the pilot module's own
    find/apply: this deletes, which a conversion never does.
    """
    from n26.library.gang_legacy_pilot import Refused, apply, find

    _run_recorded(
        backfill_id,
        Operation.RETIRE_GANG_LEGACY_PILOT,
        "Pilot retirement",
        lambda: apply(find()),
        Refused,
    )


@task
def clear_spare_answers(backfill_id, **said_by_whoever_enqueued_it):
    """Clear the answers a doubled click left behind, and record it.

    The runner discipline of a conversion around work that deletes a
    player's rows and means to change their pages — so what it proves is
    that the pages changed in exactly the way it said and no other.
    """
    from n26.library.spare_answers import Refused, apply, find

    _run_recorded(
        backfill_id,
        Operation.CLEAR_SPARE_ANSWERS,
        "Spare answers clearing",
        lambda: apply(find()),
        Refused,
    )


@task
def delete_retired_kinds(backfill_id, **said_by_whoever_enqueued_it):
    """Delete what the conversions left standing, and record it.

    The runner discipline of a conversion around work that deletes
    library rows only. Nothing a player holds is touched, which is why
    what it proves is that no page moves at all.
    """
    from n26.library.retired_kinds import Refused, apply, find

    _run_recorded(
        backfill_id,
        Operation.DELETE_RETIRED_KINDS,
        "Retired kinds deletion",
        lambda: apply(find()),
        Refused,
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

    The same runner discipline as a conversion — the lock, the claim,
    every ending recorded — around work that deletes and rewrites a
    player's gang, which is why the module it calls reads every gang
    before it touches one.
    """
    from n26.library.nameless_gang_type import Refused, apply, find

    _run_recorded(
        backfill_id,
        Operation.DELETE_NAMELESS_GANG_TYPE,
        "Nameless gang type retirement",
        lambda: apply(find(), actor=_who_asked(backfill_id)),
        Refused,
    )


#: What a conversion's page says about its own proof. Each operation
#: proves something different, and a page that named the wrong one would
#: promise a safety nobody is being given.
def _proof_words(plan):
    return {
        "reach_words": (
            f"It reaches {plan.reaches} gang"
            f"{'' if plan.reaches == 1 else 's'}, and proves "
            f"{len(plan.gang_ids)} of them read the same before committing — "
            "a spread wide enough to hold every shape the system comes in. "
            "Proving all of them would mean holding the whole library for "
            "minutes while players are using it."
        ),
        "confirm_words": (
            f"Convert {plan.reaches} gang(s)? It writes nothing unless every "
            "page it proves reads the same."
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
        # Two different numbers, and confusing them on a page with an
        # apply button would tell an operator the change is smaller than
        # it is: one is how many gangs it reaches, the other how many of
        # them it proves before committing.
        reaches=plan.reaches,
        proven=len(plan.gang_ids),
        apply_url=address,
        recent=Backfill.objects.filter(operation=operation)[:10],
        **_proof_words(plan),
    )
    return render(request, "admin/maintenance/n26/convert.html", context)


def convert_specialisation_view(request):
    return _conversion_view(
        request,
        Operation.CONVERT_SPECIALISATION,
        "specialisation",
        convert_specialisation,
    )


def convert_skill_tree_view(request):
    return _conversion_view(
        request,
        Operation.CONVERT_SKILL_TREE,
        "skill_tree",
        convert_skill_tree,
    )


def convert_gang_legacy_view(request):
    return _conversion_view(
        request,
        Operation.CONVERT_GANG_LEGACY,
        "gang_legacy",
        convert_gang_legacy,
    )


def convert_archetype_view(request):
    return _conversion_view(
        request,
        Operation.CONVERT_ARCHETYPE,
        "archetype",
        convert_archetype,
    )


#: The words one deletion page says for itself. Everything else about
#: the page — the plan, the refusals, the apply button, the recent runs —
#: is the same for every deletion, so only these differ.
PILOT_WORDS = {
    "noun": "retirement",
    "intro": (
        "This deletes library rows and the assignments answering them. The "
        "pilot was a hand-built experiment whose pickables carry nothing, and its rows "
        "squat on the names the real Gang Legacy conversion needs. Every row "
        "it would delete is listed below; it refuses if anything outside the "
        "pilot has come to depend on them."
    ),
    "nothing_heading": "Nothing to retire",
    "nothing_flash": "There was nothing to retire.",
    "nothing_words": (
        "No slot type of the pilot's name stands. It has been retired "
        "already, or was never here."
    ),
    "refuses_heading": "The retirement refuses",
    "button": "Retire the pilot",
    "confirm": "Delete the pilot? This cannot be undone.",
}

SPARE_WORDS = {
    "noun": "clearing",
    "intro": (
        "This deletes player rows, and it means to change what those "
        "players see: each spare draws a line on a model's gear list named "
        "after a sort of question rather than a thing anybody owns. Every "
        "line it would take away is named below, and it refuses unless the "
        "pages afterwards read exactly as they do now but for those. A row "
        "that was paid for, that counts towards what a gang is worth, that "
        "has anything hanging off it, or whose question nothing else "
        "answers, is not a spare and is left alone."
    ),
    "nothing_heading": "Nothing to clear",
    "nothing_flash": "There was nothing to clear.",
    "nothing_words": "No question is answered twice over.",
    "refuses_heading": "The clearing refuses",
    "button": "Clear the spares",
    "confirm": "Delete these spare answers? This cannot be undone.",
}

RETIRED_KIND_WORDS = {
    "noun": "deletion",
    "intro": (
        "This deletes library rows and nothing a player holds: the kind rows "
        "the conversions emptied, the menus those kinds were chosen from, and "
        "the offers nothing carries. Every row it would delete is listed "
        "below, along with anything it leaves alone and why. Because none of "
        "it is in use, no page should move at all — and that is what it "
        "proves before committing. It refuses while any answer still names a "
        "retired kind, which the sweep and the clearing deal with first."
    ),
    "nothing_heading": "Nothing to delete",
    "nothing_flash": "There was nothing to delete.",
    "nothing_words": "The retired kinds have gone already.",
    "refuses_heading": "The deletion refuses",
    "button": "Delete what is left",
    "confirm": "Delete these library rows? This cannot be undone.",
}

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
    conversion view's — a running guard, nothing recorded for a run with
    nothing to do, a refusal shown to whoever asked for it rather than
    filed as a failure — and only ``words`` differs between pages.
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


def _spares_left():
    """What this sweep does not reach, said plainly on its own page.

    A doubled click leaves a live answer beside the one that settled the
    question, and the conversions left those exactly as they were. They
    are live, so this sweep — which is for what was taken back — does not
    touch them, and while they stand the kinds they name still cannot be
    retired.
    """
    from n26.core.models import Assignment
    from n26.library.conversion.archived import OLD_COLUMNS

    live = Assignment.objects.filter(archived=False).exclude(removes=True)
    standing = sum(
        live.filter(**{f"{column}__isnull": False}).count() for column in OLD_COLUMNS
    )
    if not standing:
        return ""
    return (
        f"{standing} live answer{'' if standing == 1 else 's'} still name a "
        "retired kind and are left as they are: spares from a click that "
        "landed twice, which are somebody's page rather than history. "
        "Retiring those kinds has to deal with them separately."
    )


def sweep_archived_view(request):
    """Preview the sweep (GET), or record a run and enqueue it (POST)."""
    from n26.library.conversion.archived import plan_archived

    operation = Operation.SWEEP_ARCHIVED
    address = reverse(f"admin:maintenance_{operation.value}")
    if request.method == "POST":
        running = running_guard(operation)
        if running is not None:
            messages.warning(request, "That sweep is already running.")
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[running.id])
            )
        plan = plan_archived()
        if plan.nothing_here:
            messages.info(request, "There is nothing left to sweep.")
            return HttpResponseRedirect(address)
        if not plan.ok:
            messages.error(request, "The sweep refuses: " + "; ".join(plan.problems))
            return HttpResponseRedirect(address)
        backfill = Backfill.objects.create(
            operation=operation,
            triggered_by=request.user,
            status=Backfill.Status.RUNNING,
            summary={"preview": list(plan.preview()), "attempts": 0},
        )
        sweep_archived.enqueue(backfill_id=str(backfill.id))
        messages.success(request, "The sweep is running. This page shows what it did.")
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )

    plan = plan_archived()
    context = page_context(
        request,
        operation.label,
        plan=plan,
        preview=list(plan.preview()),
        reaches=plan.reaches,
        proven=plan.reaches,
        apply_url=address,
        recent=Backfill.objects.filter(operation=operation)[:10],
        reach_words=(
            f"It reaches {plan.reaches} gang"
            f"{'' if plan.reaches == 1 else 's'} and proves every one of them, "
            "not a spread: what it rewrites are answers already taken back, "
            "which draw nothing on any card, so what is read twice is each "
            "gang's history rather than its pages. Folding a story costs a "
            "fraction of what building the pages costs, which is what makes "
            "proving all of them affordable."
        ),
        confirm_words=(
            f"Rewrite {len(plan.steps)} archived answer(s)? It writes nothing "
            "unless every gang's history reads the same afterwards"
            + (
                ", but for the rewording listed above, which it counts before "
                "you agree to it."
                if plan.rewords
                else "."
            )
        ),
        button_words="Apply sweep",
        leaves_behind=_spares_left(),
    )
    return render(request, "admin/maintenance/n26/convert.html", context)


def retire_gang_legacy_pilot_view(request):
    """Preview the pilot retirement (GET), or record a run and enqueue it."""
    from n26.library.gang_legacy_pilot import find

    return _deletion_view(
        request,
        Operation.RETIRE_GANG_LEGACY_PILOT,
        find,
        retire_gang_legacy_pilot,
        PILOT_WORDS,
    )


def clear_spare_answers_view(request):
    """Preview the clearing (GET), or record a run and enqueue it."""
    from n26.library.spare_answers import find

    return _deletion_view(
        request,
        Operation.CLEAR_SPARE_ANSWERS,
        find,
        clear_spare_answers,
        SPARE_WORDS,
    )


def delete_retired_kinds_view(request):
    """Preview the deletion (GET), or record a run and enqueue it."""
    from n26.library.retired_kinds import find

    return _deletion_view(
        request,
        Operation.DELETE_RETIRED_KINDS,
        find,
        delete_retired_kinds,
        RETIRED_KIND_WORDS,
    )


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


register_operation(
    MaintenanceOperation(
        operation=Operation.CONVERT_SPECIALISATION.value,
        name=Operation.CONVERT_SPECIALISATION.label,
        added=date(2026, 8, 17),
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
        added=date(2026, 8, 18),
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

register_operation(
    MaintenanceOperation(
        operation=Operation.RETIRE_GANG_LEGACY_PILOT.value,
        name=Operation.RETIRE_GANG_LEGACY_PILOT.label,
        added=date(2026, 8, 18),
        description=(
            "Delete the hand-built Gang Legacy slot experiment: its hollow "
            "pickables, its slot machinery, and the one test gang's "
            "assignments answering it. Runs before the Gang Legacy "
            "conversion, which needs the names it squats on. Refuses if "
            "anything outside the pilot has come to depend on it."
        ),
        view=retire_gang_legacy_pilot_view,
        detail_template="admin/maintenance/n26/_delete_detail.html",
    )
)

register_operation(
    MaintenanceOperation(
        operation=Operation.CONVERT_GANG_LEGACY.value,
        name=Operation.CONVERT_GANG_LEGACY.label,
        added=date(2026, 8, 18),
        description=(
            "Move the Venator house legacies onto slots and picks: the "
            "hunt profiles grant a Gang Legacy slot instead of offering "
            "an archetype, the menu's houses become pickables carrying "
            "their equipment lists, and every stored choice is re-said "
            "as a pick. Proves every affected gang's pages read the "
            "same, or writes nothing."
        ),
        view=convert_gang_legacy_view,
        detail_template="admin/maintenance/n26/_convert_detail.html",
    )
)

register_operation(
    MaintenanceOperation(
        operation=Operation.CONVERT_ARCHETYPE.value,
        name=Operation.CONVERT_ARCHETYPE.label,
        added=date(2026, 8, 20),
        description=(
            "Move the Outcast archetypes onto slots and picks: each Leader "
            "profile grants the gang's Archetype slot and the Champion "
            "profile grants its own, instead of offering a choice, and "
            "every stored choice is re-said as a pick. What an archetype "
            "does travels with it untouched. Proves every affected gang's "
            "pages read the same, or writes nothing."
        ),
        view=convert_archetype_view,
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
        operation=Operation.SWEEP_ARCHIVED.value,
        name=Operation.SWEEP_ARCHIVED.label,
        added=date(2026, 8, 22),
        description=(
            "Rewrite the answers a gang took back — archived, still "
            "naming the kinds the conversions replaced, and the last "
            "thing standing between those kinds and retirement. Reads "
            "every affected gang's history before and after and refuses "
            "on any word that moves."
        ),
        view=sweep_archived_view,
        detail_template="admin/maintenance/n26/_convert_detail.html",
    )
)

register_operation(
    MaintenanceOperation(
        operation=Operation.CLEAR_SPARE_ANSWERS.value,
        name=Operation.CLEAR_SPARE_ANSWERS.label,
        description=(
            "Delete the second answer a doubled click left standing beside "
            "the one that settled the question. Each draws a line on a "
            "model's gear list named after the question rather than a thing, "
            "and clearing it takes that line away and changes nothing else — "
            "which is what it proves before committing. Must run before the "
            "kinds those answers name can be retired."
        ),
        view=clear_spare_answers_view,
    )
)

register_operation(
    MaintenanceOperation(
        operation=Operation.DELETE_RETIRED_KINDS.value,
        name=Operation.DELETE_RETIRED_KINDS.label,
        description=(
            "Delete what the conversions left behind: the emptied kind rows, "
            "the menus nothing offers from, and the detached offers. All "
            "library, none of it in use, so it proves that no page moves at "
            "all. Runs after the sweep and the clearing, which take the last "
            "answers off those kinds."
        ),
        view=delete_retired_kinds_view,
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
    TaskRoute(convert_gang_legacy, ack_deadline=600, min_retry_delay=60),
    TaskRoute(retire_gang_legacy_pilot, ack_deadline=600, min_retry_delay=60),
    TaskRoute(convert_archetype, ack_deadline=600, min_retry_delay=60),
    TaskRoute(delete_nameless_gang_type, ack_deadline=600, min_retry_delay=60),
    TaskRoute(sweep_archived, ack_deadline=600, min_retry_delay=60),
    TaskRoute(clear_spare_answers, ack_deadline=600, min_retry_delay=60),
    TaskRoute(delete_retired_kinds, ack_deadline=600, min_retry_delay=60),
]


# Retired: it has been run, and what it repaired cannot recur. Registered
# with no view so the record of that run still reads as a name rather than
# a bare slug.
register_operation(
    MaintenanceOperation(
        operation=Operation.MERGE_WARGEAR_INTO_WEAPON.value,
        name=Operation.MERGE_WARGEAR_INTO_WEAPON.label,
        added=date(2026, 8, 18),
    )
)
