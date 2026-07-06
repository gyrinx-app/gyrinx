"""Admin-only maintenance pages for one-off data repairs.

Pattern mirrors ``gyrinx/analytics/admin.py``: subclass whatever admin.site is
currently using (so the chain composes — analytics's routes survive), add new
custom routes via ``get_urls``, then monkey-patch ``admin.site.__class__``.

For this to compose, the ``gyrinx.maintenance`` app must be listed AFTER
``gyrinx.analytics`` in ``INSTALLED_APPS``.

All maintenance views are **superuser-gated** (the standard ``admin_view``
wrapper only enforces ``is_staff``; mutation-capable views need tighter
control).
"""

import logging
import traceback

from django.contrib import admin, messages
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse

from gyrinx.core.maintenance.persistent_stash import (
    SKIP_REASONS,
    apply as apply_persistent_stash,
    find_candidates as find_persistent_stash_candidates,
)
from gyrinx.core.models import Backfill
from gyrinx.core.models.list import ListFighterEquipmentAssignment, PinState
from gyrinx.core.tasks import backfill_pins, reconcile_all_lists

logger = logging.getLogger(__name__)


def _superuser_only(view):
    """Wrap a bound-method admin view in a superuser check."""

    def wrapped(request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_superuser):
            return HttpResponseForbidden("Superuser required for maintenance views.")
        return view(request, *args, **kwargs)

    wrapped.__name__ = getattr(view, "__name__", "wrapped")
    return wrapped


def _clean_list_scope(request):
    """Validate the optional list-scope input.

    Returns (list_id_or_None, error_message_or_None). A typo'd UUID is the
    most likely input on the incremental-rollout box — it must produce a
    friendly error, not a 500 from a UUID-typed ORM lookup.
    """
    import uuid as uuid_module

    raw = (request.POST.get("list_id") or request.GET.get("list_id") or "").strip()
    if not raw:
        return None, None
    try:
        return str(uuid_module.UUID(raw)), None
    except ValueError:
        return None, f"'{raw}' is not a valid UUID."


def _running_guard(operation):
    """A RUNNING record for this operation, if any — one chain at a time.

    Idempotency makes a duplicate run harmless to the data, but it doubles
    the walk and muddles the audit trail. (If the task runner died and left
    a stale RUNNING record, mark it Failed in the Backfills admin first.)
    """
    return (
        Backfill.objects.filter(operation=operation, status=Backfill.Status.RUNNING)
        .order_by("-created")
        .first()
    )


class MaintenanceAdminSite(admin.site.__class__):
    """Adds /admin/maintenance/* routes on top of whatever admin.site already is."""

    # Admin home shows a Maintenance banner to those who can use it
    # (superusers). The template extends the stock index — a different
    # template NAME, so no extends-recursion.
    index_template = "admin/maintenance/admin_index.html"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "maintenance/",
                self.admin_view(_superuser_only(self.maintenance_index_view)),
                name="maintenance_index",
            ),
            path(
                "maintenance/persistent-stash/",
                self.admin_view(_superuser_only(self.persistent_stash_view)),
                name="maintenance_persistent_stash",
            ),
            path(
                "maintenance/reconcile-lists/",
                self.admin_view(_superuser_only(self.reconcile_lists_view)),
                name="maintenance_reconcile_lists",
            ),
            path(
                "maintenance/backfill-pins/",
                self.admin_view(_superuser_only(self.backfill_pins_view)),
                name="maintenance_backfill_pins",
            ),
            path(
                "maintenance/backfill/<uuid:pk>/",
                self.admin_view(_superuser_only(self.backfill_detail_view)),
                name="maintenance_backfill_detail",
            ),
        ]
        return custom + urls

    # ---------------------------------------------------------------- views

    def maintenance_index_view(self, request):
        operations = [
            {
                "key": Backfill.Operation.MIGRATE_PERSISTENT_STASH.value,
                "name": Backfill.Operation.MIGRATE_PERSISTENT_STASH.label,
                "url": reverse("admin:maintenance_persistent_stash"),
                "description": (
                    "Move persistent-category gear off stash fighters back "
                    "to the dying Fighter where provenance is provable from "
                    "the ListAction ledger (±1s window around an "
                    "UPDATE_FIGHTER kill action on the same list)."
                ),
            },
            {
                "key": Backfill.Operation.RECONCILE_LISTS.value,
                "name": Backfill.Operation.RECONCILE_LISTS.label,
                "url": reverse("admin:maintenance_reconcile_lists"),
                "description": (
                    "True up every list's cached costs from live resolution, "
                    "recording movement as RECONCILE ledger actions. Runs on "
                    "the task runner in batches; progress on the backfill "
                    "record. Run BEFORE the receipt backfill."
                ),
            },
            {
                "key": Backfill.Operation.BACKFILL_PINS.value,
                "name": Backfill.Operation.BACKFILL_PINS.label,
                "url": reverse("admin:maintenance_backfill_pins"),
                "description": (
                    "Write acquisition receipts onto every legacy assignment "
                    "via the pinning choke point. Idempotent, resumable, "
                    "value-neutral. Run AFTER reconcile, in a quiet window."
                ),
            },
        ]
        recent = Backfill.objects.order_by("-created")[:25]
        ctx = {
            **self.each_context(request),
            "title": "Maintenance",
            "operations": operations,
            "recent_backfills": recent,
        }
        return render(request, "admin/maintenance/index.html", ctx)

    def persistent_stash_view(self, request):
        list_id = (
            request.POST.get("list_id") or request.GET.get("list_id") or ""
        ).strip() or None
        if request.method == "POST":
            try:
                result = apply_persistent_stash(
                    list_id=list_id, triggered_by=request.user
                )
                backfill = Backfill.objects.create(
                    operation=Backfill.Operation.MIGRATE_PERSISTENT_STASH,
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
                    operation=Backfill.Operation.MIGRATE_PERSISTENT_STASH,
                    triggered_by=request.user,
                    list_id_scope=list_id,
                    status=Backfill.Status.FAILED,
                    error=f"{e}\n\n{traceback.format_exc()}",
                )
                messages.error(request, f"Backfill failed: {e}")
                return HttpResponseRedirect(
                    reverse("admin:maintenance_persistent_stash")
                )
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
        moves = [c for c in candidates if c.decision == "move"]
        skips = [c for c in candidates if c.decision != "move"]
        ctx = {
            **self.each_context(request),
            "title": "Migrate persistent stash items (#1825)",
            "moves": moves,
            "skips": skips,
            "summary": summary,
            "list_id": list_id or "",
            "apply_url": reverse("admin:maintenance_persistent_stash"),
        }
        return render(request, "admin/maintenance/persistent_stash.html", ctx)

    def reconcile_lists_view(self, request):
        from gyrinx.core.models.list import List

        list_id, scope_error = _clean_list_scope(request)
        if scope_error:
            messages.error(request, scope_error)
            return HttpResponseRedirect(reverse("admin:maintenance_reconcile_lists"))
        if request.method == "POST":
            if list_id and not List.objects.filter(pk=list_id).exists():
                messages.error(request, f"No list with id {list_id}.")
                return HttpResponseRedirect(
                    reverse("admin:maintenance_reconcile_lists")
                )
            running = _running_guard(Backfill.Operation.RECONCILE_LISTS)
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
                operation=Backfill.Operation.RECONCILE_LISTS,
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
                "Reconcile started on the task runner — progress below "
                "(refresh to update).",
            )
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[backfill.id])
            )

        scoped = List.objects.filter(pk=list_id) if list_id else List.objects
        ctx = {
            **self.each_context(request),
            "title": Backfill.Operation.RECONCILE_LISTS.label,
            "list_id": list_id or "",
            "list_count": scoped.count(),
            "recent": Backfill.objects.filter(
                operation=Backfill.Operation.RECONCILE_LISTS
            ).order_by("-created")[:10],
            "apply_url": reverse("admin:maintenance_reconcile_lists"),
        }
        return render(request, "admin/maintenance/reconcile_lists.html", ctx)

    def backfill_pins_view(self, request):
        from gyrinx.core.models.list import List

        list_id, scope_error = _clean_list_scope(request)
        if scope_error:
            messages.error(request, scope_error)
            return HttpResponseRedirect(reverse("admin:maintenance_backfill_pins"))
        if request.method == "POST":
            if list_id and not List.objects.filter(pk=list_id).exists():
                messages.error(request, f"No list with id {list_id}.")
                return HttpResponseRedirect(reverse("admin:maintenance_backfill_pins"))
            running = _running_guard(Backfill.Operation.BACKFILL_PINS)
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
                operation=Backfill.Operation.BACKFILL_PINS,
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
        pin_states = {
            state.label: assignments.filter(pinned_base_state=state).count()
            for state in PinState
        }
        ctx = {
            **self.each_context(request),
            "title": Backfill.Operation.BACKFILL_PINS.label,
            "list_id": list_id or "",
            "total": assignments.count(),
            "pin_states": pin_states,
            "recent": Backfill.objects.filter(
                operation=Backfill.Operation.BACKFILL_PINS
            ).order_by("-created")[:10],
            "apply_url": reverse("admin:maintenance_backfill_pins"),
        }
        return render(request, "admin/maintenance/backfill_pins.html", ctx)

    def backfill_detail_view(self, request, pk):
        backfill = get_object_or_404(Backfill, pk=pk)
        # The detail page renders per-operation: reconcile shows rating/stash
        # movement, the persistent-stash migration shows moved items, everything
        # else falls back to a plain summary dump.
        ctx = {
            **self.each_context(request),
            "title": str(backfill),
            "backfill": backfill,
            "is_reconcile": backfill.operation == Backfill.Operation.RECONCILE_LISTS,
            "is_persistent_stash": (
                backfill.operation == Backfill.Operation.MIGRATE_PERSISTENT_STASH
            ),
        }
        return render(request, "admin/maintenance/backfill_detail.html", ctx)


# Install on the live admin site. Order in INSTALLED_APPS must place this app
# AFTER gyrinx.analytics so the chain composes (analytics's routes survive).
admin.site.__class__ = MaintenanceAdminSite
