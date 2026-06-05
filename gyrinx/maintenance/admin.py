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

logger = logging.getLogger(__name__)


def _superuser_only(view):
    """Wrap a bound-method admin view in a superuser check."""

    def wrapped(request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_superuser):
            return HttpResponseForbidden("Superuser required for maintenance views.")
        return view(request, *args, **kwargs)

    wrapped.__name__ = getattr(view, "__name__", "wrapped")
    return wrapped


class MaintenanceAdminSite(admin.site.__class__):
    """Adds /admin/maintenance/* routes on top of whatever admin.site already is."""

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

    def backfill_detail_view(self, request, pk):
        backfill = get_object_or_404(Backfill, pk=pk)
        ctx = {
            **self.each_context(request),
            "title": str(backfill),
            "backfill": backfill,
        }
        return render(request, "admin/maintenance/backfill_detail.html", ctx)


# Install on the live admin site. Order in INSTALLED_APPS must place this app
# AFTER gyrinx.analytics so the chain composes (analytics's routes survive).
admin.site.__class__ = MaintenanceAdminSite
