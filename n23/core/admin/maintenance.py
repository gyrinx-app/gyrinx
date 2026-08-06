"""This edition's repairs, and the pages that trigger them.

The console shell — index, audit records, detail, cancel — is platform code in
``gyrinx.maintenance``. What it can repair is here: each operation registers a
name, a description for the index, the view for its own trigger page, and the
template that renders its summary on a record's detail page.

Every view is a plain function. The platform mounts them and applies the
superuser gate, so nothing here can publish an ungated page.

Do NOT import ``gyrinx.maintenance.admin`` from this module. It patches
``admin.site.__class__`` on import and must run after ``gyrinx.analytics.admin``;
this module is autodiscovered first, so importing it here would silently drop
every maintenance route. ``registry`` and ``views`` are the safe imports.

Imported by ``n23.core.admin``; drop that import and the console goes empty.
"""

import logging
import traceback

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

from gyrinx.maintenance.models import Backfill
from gyrinx.maintenance.registry import MaintenanceOperation, register_operation
from gyrinx.maintenance.views import (
    clean_list_scope,
    page_context,
    running_guard,
)
from n23.core.maintenance.operations import RETIRED, Operation
from n23.core.maintenance.persistent_stash import (
    SKIP_REASONS,
    apply as apply_persistent_stash,
    find_candidates as find_persistent_stash_candidates,
)
from n23.core.models.list import ListFighterEquipmentAssignment, PinState
from n23.core.tasks import backfill_pins, reconcile_all_lists

logger = logging.getLogger(__name__)

__all__ = []


# ---------------------------------------------------------------------- views


def persistent_stash_view(request):
    list_id = (
        request.POST.get("list_id") or request.GET.get("list_id") or ""
    ).strip() or None
    if request.method == "POST":
        try:
            result = apply_persistent_stash(list_id=list_id, triggered_by=request.user)
            backfill = Backfill.objects.create(
                operation=Operation.MIGRATE_PERSISTENT_STASH,
                triggered_by=request.user,
                list_id_scope=list_id,
                status=Backfill.Status.DONE,
                summary=result.as_dict(),
            )
            messages.success(
                request,
                f"Moved {result.moved} item(s) across {result.affected_lists} list(s).",
            )
        except Exception as e:
            logger.exception("Persistent-stash backfill failed")
            Backfill.objects.create(
                operation=Operation.MIGRATE_PERSISTENT_STASH,
                triggered_by=request.user,
                list_id_scope=list_id,
                status=Backfill.Status.FAILED,
                error=f"{e}\n\n{traceback.format_exc()}",
            )
            messages.error(request, f"Backfill failed: {e}")
            return HttpResponseRedirect(reverse("admin:maintenance_persistent_stash"))
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )

    candidates = find_persistent_stash_candidates(list_id=list_id)
    summary = {"would_move": 0, **{r: 0 for r in SKIP_REASONS}}
    for c in candidates:
        if c.decision == "move":
            summary["would_move"] += 1
        else:
            summary[c.decision] += 1
    ctx = page_context(
        request,
        Operation.MIGRATE_PERSISTENT_STASH.label,
        moves=[c for c in candidates if c.decision == "move"],
        skips=[c for c in candidates if c.decision != "move"],
        summary=summary,
        list_id=list_id or "",
        apply_url=reverse("admin:maintenance_persistent_stash"),
    )
    return render(request, "admin/maintenance/n23/persistent_stash.html", ctx)


def reconcile_lists_view(request):
    from n23.core.models.list import List

    list_id, scope_error = clean_list_scope(request)
    if scope_error:
        messages.error(request, scope_error)
        return HttpResponseRedirect(reverse("admin:maintenance_reconcile_lists"))
    if request.method == "POST":
        if list_id and not List.objects.filter(pk=list_id).exists():
            messages.error(request, f"No list with id {list_id}.")
            return HttpResponseRedirect(reverse("admin:maintenance_reconcile_lists"))
        running = running_guard(Operation.RECONCILE_LISTS)
        if running:
            messages.error(
                request,
                "A reconcile run is already RUNNING — one chain at a "
                "time. If the task runner died and this is stale, mark "
                "that record Failed in the Backfills admin first.",
            )
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[running.id])
            )
        backfill = Backfill.objects.create(
            operation=Operation.RECONCILE_LISTS,
            triggered_by=request.user,
            list_id_scope=list_id,
            status=Backfill.Status.RUNNING,
        )
        reconcile_all_lists.enqueue(
            backfill_id=str(backfill.id),
            user_id=request.user.pk,
            list_id=list_id,
        )
        messages.success(
            request,
            "Reconcile started on the task runner — progress below (refresh to update).",
        )
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )

    scoped = List.objects.filter(pk=list_id) if list_id else List.objects
    ctx = page_context(
        request,
        Operation.RECONCILE_LISTS.label,
        list_id=list_id or "",
        list_count=scoped.count(),
        recent=Backfill.objects.filter(operation=Operation.RECONCILE_LISTS).order_by(
            "-created"
        )[:10],
        apply_url=reverse("admin:maintenance_reconcile_lists"),
    )
    return render(request, "admin/maintenance/n23/reconcile_lists.html", ctx)


def backfill_pins_view(request):
    from n23.core.models.list import List

    list_id, scope_error = clean_list_scope(request)
    if scope_error:
        messages.error(request, scope_error)
        return HttpResponseRedirect(reverse("admin:maintenance_backfill_pins"))
    if request.method == "POST":
        if list_id and not List.objects.filter(pk=list_id).exists():
            messages.error(request, f"No list with id {list_id}.")
            return HttpResponseRedirect(reverse("admin:maintenance_backfill_pins"))
        running = running_guard(Operation.BACKFILL_PINS)
        if running:
            messages.error(
                request,
                "A receipt backfill is already RUNNING — one chain at a "
                "time. If the task runner died and this is stale, mark "
                "that record Failed in the Backfills admin first.",
            )
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[running.id])
            )
        backfill = Backfill.objects.create(
            operation=Operation.BACKFILL_PINS,
            triggered_by=request.user,
            list_id_scope=list_id,
            status=Backfill.Status.RUNNING,
        )
        backfill_pins.enqueue(backfill_id=str(backfill.id), list_id=list_id)
        messages.success(
            request,
            "Receipt backfill started on the task runner — progress "
            "below (refresh to update; the unpinned count is the "
            "progress bar).",
        )
        return HttpResponseRedirect(
            reverse("admin:maintenance_backfill_detail", args=[backfill.id])
        )

    assignments = ListFighterEquipmentAssignment.objects.all()
    if list_id:
        assignments = assignments.filter(list_fighter__list_id=list_id)
    ctx = page_context(
        request,
        Operation.BACKFILL_PINS.label,
        list_id=list_id or "",
        total=assignments.count(),
        pin_states={
            state.label: assignments.filter(pinned_base_state=state).count()
            for state in PinState
        },
        recent=Backfill.objects.filter(operation=Operation.BACKFILL_PINS).order_by(
            "-created"
        )[:10],
        apply_url=reverse("admin:maintenance_backfill_pins"),
    )
    return render(request, "admin/maintenance/n23/backfill_pins.html", ctx)


# --------------------------------------------------------------- registration

register_operation(
    MaintenanceOperation(
        operation=Operation.MIGRATE_PERSISTENT_STASH.value,
        # The published URL predates the slug, so keep them apart.
        slug="persistent_stash",
        name=Operation.MIGRATE_PERSISTENT_STASH.label,
        description=(
            "Move persistent-category gear off stash fighters back "
            "to the dying Fighter where provenance is provable from "
            "the ListAction ledger (±1s window around an "
            "UPDATE_FIGHTER kill action on the same list)."
        ),
        view=persistent_stash_view,
        detail_template="admin/maintenance/n23/_persistent_stash_detail.html",
    )
)
register_operation(
    MaintenanceOperation(
        operation=Operation.RECONCILE_LISTS.value,
        name=Operation.RECONCILE_LISTS.label,
        description=(
            "True up every list's cached costs from live resolution, "
            "recording movement as RECONCILE ledger actions. Runs on "
            "the task runner in batches; progress on the backfill "
            "record. Run BEFORE the receipt backfill."
        ),
        view=reconcile_lists_view,
        detail_template="admin/maintenance/n23/_reconcile_detail.html",
    )
)
register_operation(
    MaintenanceOperation(
        operation=Operation.BACKFILL_PINS.value,
        name=Operation.BACKFILL_PINS.label,
        description=(
            "Write acquisition receipts onto every legacy assignment "
            "via the pinning choke point. Idempotent, resumable, "
            "value-neutral. Run AFTER reconcile, in a quiet window."
        ),
        view=backfill_pins_view,
    )
)

# Label-only, so historical records keep reading as something other than a slug.
for _retired in RETIRED:
    register_operation(
        MaintenanceOperation(operation=_retired.value, name=_retired.label)
    )
