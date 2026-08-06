"""The console's own pages, and the helpers an operation's page needs.

Kept out of ``admin.py`` deliberately: that module patches
``admin.site.__class__`` when imported, so an edition importing it would install
the maintenance site before ``gyrinx.analytics.admin`` runs and lose every
maintenance route (see ``gyrinx.maintenance.registry``). Everything here is
import-safe, so edition operation views can pull what they need from it.

These views are plain functions. Mounting them — including the superuser gate —
is ``admin.py``'s job, so no view can be published without the gate.
"""

import uuid as uuid_module

from django.contrib import admin, messages
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from gyrinx.maintenance.models import Backfill
from gyrinx.maintenance.registry import operations, resolve_operation

__all__ = [
    "backfill_cancel_view",
    "backfill_detail_view",
    "clean_list_scope",
    "maintenance_index_view",
    "page_context",
    "running_guard",
    "superuser_only",
]


def superuser_only(view):
    """Wrap an admin view in a superuser check.

    ``AdminSite.admin_view`` only enforces ``is_staff``; everything in the
    console can mutate production data, so it needs the tighter gate.
    """

    def wrapped(request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_superuser):
            return HttpResponseForbidden("Superuser required for maintenance views.")
        return view(request, *args, **kwargs)

    wrapped.__name__ = getattr(view, "__name__", "wrapped")
    return wrapped


def page_context(request, title, **extra):
    """Admin chrome plus a title — what every console page starts from."""
    return {**admin.site.each_context(request), "title": title, **extra}


def clean_list_scope(request):
    """Validate the optional list-scope input.

    Returns (list_id_or_None, error_message_or_None). A typo'd UUID is the
    most likely input on the incremental-rollout box — it must produce a
    friendly error, not a 500 from a UUID-typed ORM lookup.
    """
    raw = (request.POST.get("list_id") or request.GET.get("list_id") or "").strip()
    if not raw:
        return None, None
    try:
        return str(uuid_module.UUID(raw)), None
    except ValueError:
        return None, f"'{raw}' is not a valid UUID."


def running_guard(operation):
    """A RUNNING record for this operation, if any — one chain at a time.

    Idempotency makes a duplicate run harmless to the data, but it doubles
    the walk and muddles the audit trail. (If the task runner died and left
    a stale RUNNING record, mark it Failed in the Backfills admin first —
    except for the stat-advancement cleanup, which reads its own records to
    know what it already touched and ignores only Cancelled ones.)
    """
    return (
        Backfill.objects.filter(operation=operation, status=Backfill.Status.RUNNING)
        .order_by("-created")
        .first()
    )


def maintenance_index_view(request):
    ctx = page_context(
        request,
        "Maintenance",
        operations=[
            {
                "key": op.operation,
                "name": op.name,
                "url": reverse(f"admin:{op.url_name}"),
                "description": op.description,
            }
            for op in operations()
        ],
        recent_backfills=Backfill.objects.order_by("-created")[:25],
    )
    return render(request, "admin/maintenance/index.html", ctx)


def backfill_detail_view(request, pk):
    backfill = get_object_or_404(Backfill, pk=pk)
    # How a run's summary reads is operation-specific — reconcile shows
    # rating/stash movement, the stash migration shows moved items — so the
    # operation supplies that fragment. Without one, fall back to a plain dump.
    operation = resolve_operation(backfill.operation)
    ctx = page_context(
        request,
        str(backfill),
        backfill=backfill,
        detail_template=operation.detail_template if operation else None,
    )
    return render(request, "admin/maintenance/backfill_detail.html", ctx)


def backfill_cancel_view(request, pk):
    """Request a stop for a RUNNING task chain. Sets the record to CANCELLED;
    the chain checks this at the top of its next batch and bails, so the run
    winds down within one batch (no infra intervention). No-op if the record
    is already terminal."""
    backfill = get_object_or_404(Backfill, pk=pk)
    detail_url = reverse("admin:maintenance_backfill_detail", args=[backfill.id])
    if request.method != "POST":
        return HttpResponseRedirect(detail_url)
    # Atomic RUNNING->CANCELLED so we can't clobber a result the chain sets
    # concurrently (a final batch flipping the record to DONE between a read
    # and a save). Only a still-RUNNING record is affected.
    updated = Backfill.objects.filter(pk=pk, status=Backfill.Status.RUNNING).update(
        status=Backfill.Status.CANCELLED, modified=timezone.now()
    )
    if updated:
        messages.success(
            request,
            "Cancel requested. The run will stop within one batch (the task "
            "checks this before starting each batch).",
        )
    else:
        backfill.refresh_from_db()
        messages.info(
            request,
            f"Nothing to cancel — this run is already {backfill.get_status_display()}.",
        )
    return HttpResponseRedirect(detail_url)
