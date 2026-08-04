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
from django.utils import timezone

from n23.core.maintenance.persistent_stash import (
    SKIP_REASONS,
    apply as apply_persistent_stash,
    find_candidates as find_persistent_stash_candidates,
)
from n23.core.maintenance.stat_advancements import (
    SITUATION_LABELS,
    build_messages,
    build_plan,
    run as run_stat_advancements,
)
from n23.core.maintenance.statlines import (
    build_format_plan,
    build_statline_plan,
    run_materialise,
    run_normalise,
)
from n23.core.models import Backfill
from n23.core.models.list import ListFighterEquipmentAssignment, PinState
from n23.core.tasks import backfill_pins, reconcile_all_lists

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
    a stale RUNNING record, mark it Failed in the Backfills admin first —
    except for the stat-advancement cleanup, which reads its own records to
    know what it already touched and ignores only Cancelled ones.)
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
                "maintenance/stat-advancements/",
                self.admin_view(_superuser_only(self.stat_advancements_view)),
                name="maintenance_stat_advancements",
            ),
            path(
                "maintenance/normalise-stat-formats/",
                self.admin_view(_superuser_only(self.normalise_stat_formats_view)),
                name="maintenance_normalise_stat_formats",
            ),
            path(
                "maintenance/materialise-statlines/",
                self.admin_view(_superuser_only(self.materialise_statlines_view)),
                name="maintenance_materialise_statlines",
            ),
            path(
                "maintenance/backfill/<uuid:pk>/",
                self.admin_view(_superuser_only(self.backfill_detail_view)),
                name="maintenance_backfill_detail",
            ),
            path(
                "maintenance/backfill/<uuid:pk>/cancel/",
                self.admin_view(_superuser_only(self.backfill_cancel_view)),
                name="maintenance_backfill_cancel",
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
            {
                "key": Backfill.Operation.FIX_STAT_ADVANCEMENTS.value,
                "name": Backfill.Operation.FIX_STAT_ADVANCEMENTS.label,
                "url": reverse("admin:maintenance_stat_advancements"),
                "description": (
                    "Finish moving stat advancements onto the mod system: "
                    "back-compute manual edits so cards do not move, switch on "
                    "advancements that were bought but showing nothing, and "
                    "remove improvements being counted twice. Notifies every "
                    "affected player once. Preview before applying."
                ),
            },
            {
                "key": Backfill.Operation.NORMALISE_STAT_FORMATS.value,
                "name": Backfill.Operation.NORMALISE_STAT_FORMATS.label,
                "url": reverse("admin:maintenance_normalise_stat_formats"),
                "description": (
                    'Add the missing + or " suffix to bare-number stat values '
                    "on templates without a statline (a visible cosmetic "
                    "correction). Run BEFORE materialising statlines, so they "
                    "are built from clean values."
                ),
            },
            {
                "key": Backfill.Operation.MATERIALISE_STATLINES.value,
                "name": Backfill.Operation.MATERIALISE_STATLINES.label,
                "url": reverse("admin:maintenance_materialise_statlines"),
                "description": (
                    "Create a statline on the Fighter type for every template "
                    "that lacks one, copying the legacy column values verbatim "
                    "(blanks become dashes). Display-preserving; run AFTER "
                    "normalising formats. #1861 Track C1."
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
        from n23.core.models.list import List

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
        from n23.core.models.list import List

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

    def stat_advancements_view(self, request):
        """Preview, then run, the #2070 stat-advancement cleanup."""
        if request.method == "POST":
            running = _running_guard(Backfill.Operation.FIX_STAT_ADVANCEMENTS)
            if running:
                # Idempotency keeps the data safe, but a second concurrent run
                # would send every affected player a duplicate message.
                messages.error(
                    request,
                    "A run is already in progress. Wait for it to finish, or "
                    "if it died, mark it Cancelled in the Backfills admin — "
                    "Cancelled is the only status this operation ignores, so "
                    "any other would leave its pairs suppressed for good.",
                )
                return HttpResponseRedirect(
                    reverse("admin:maintenance_backfill_detail", args=[running.id])
                )
            notify = request.POST.get("notify") == "on"
            try:
                # run() writes its own Backfill record: a later run reads it to
                # recognise the repairs it already made, so that write cannot be
                # left to the caller.
                result = run_stat_advancements(notify=notify, triggered_by=request.user)
                backfill = result.backfill
                # Messages go out on commit, so the count only exists on the
                # record once that has happened.
                backfill.refresh_from_db()
                sent = (backfill.summary or {}).get("messages_sent", 0)
                note = (
                    f"Changed {result.changed} fighter/stat pair(s); "
                    f"{result.visible} visible to players; {sent} message(s) sent."
                )
                if result.skipped:
                    note += (
                        f" Skipped {result.skipped} pair(s) that someone edited "
                        "while the run was in progress — re-run to pick them up."
                    )
                messages.success(request, note)
            except Exception as e:
                logger.exception("Stat-advancement cleanup failed")
                Backfill.objects.create(
                    operation=Backfill.Operation.FIX_STAT_ADVANCEMENTS,
                    triggered_by=request.user,
                    status=Backfill.Status.FAILED,
                    error=f"{e}\n\n{traceback.format_exc()}",
                )
                messages.error(request, f"Cleanup failed: {e}")
                return HttpResponseRedirect(
                    reverse("admin:maintenance_stat_advancements")
                )
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[backfill.id])
            )

        plan = build_plan()
        ctx = {
            **self.each_context(request),
            "title": "Finish the stat-advancement cleanup",
            "counts": [
                (situation, SITUATION_LABELS[situation], count)
                for situation, count in plan.by_situation().items()
            ],
            "to_change": len(plan.acted_on),
            "visible": sorted(
                plan.visible, key=lambda c: (c.list_name, c.fighter_name)
            ),
            "message_count": len(build_messages(plan)),
        }
        return render(request, "admin/maintenance/stat_advancements.html", ctx)

    def normalise_stat_formats_view(self, request):
        """Preview, then apply, the stat-format normalisation (#1861 C0)."""
        if request.method == "POST":
            running = _running_guard(Backfill.Operation.NORMALISE_STAT_FORMATS)
            if running:
                messages.error(request, "A run is already in progress.")
                return HttpResponseRedirect(
                    reverse("admin:maintenance_backfill_detail", args=[running.id])
                )
            try:
                record, applied, skipped = run_normalise(triggered_by=request.user)
                note = f"Normalised {len(applied)} value(s)."
                if skipped:
                    note += (
                        f" Skipped {len(skipped)} edited while the run was in "
                        "progress — re-open to pick them up."
                    )
                messages.success(request, note)
            except Exception as e:
                # run_normalise already recorded the run as FAILED
                logger.exception("Stat-format normalisation failed")
                messages.error(request, f"Normalisation failed: {e}")
                return HttpResponseRedirect(
                    reverse("admin:maintenance_normalise_stat_formats")
                )
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[record.id])
            )

        fixes = build_format_plan()
        ctx = {
            **self.each_context(request),
            "title": "Normalise legacy stat-column formats",
            "fixes": fixes,
        }
        return render(request, "admin/maintenance/normalise_stat_formats.html", ctx)

    def materialise_statlines_view(self, request):
        """Preview, then apply, the statline materialisation (#1861 C1)."""
        if request.method == "POST":
            running = _running_guard(Backfill.Operation.MATERIALISE_STATLINES)
            if running:
                messages.error(request, "A run is already in progress.")
                return HttpResponseRedirect(
                    reverse("admin:maintenance_backfill_detail", args=[running.id])
                )
            # Run order is one-way: once a template has a statline, this tool
            # can no longer normalise its values — a wrong order silently and
            # permanently loses the normalisation. Refuse unless forced.
            if build_format_plan() and request.POST.get("force") != "on":
                messages.error(
                    request,
                    "Un-normalised values remain. Run the format "
                    "normalisation first, or tick the override to copy "
                    "them verbatim anyway.",
                )
                return HttpResponseRedirect(
                    reverse("admin:maintenance_materialise_statlines")
                )
            try:
                record, created, skipped = run_materialise(triggered_by=request.user)
                note = f"Created {len(created)} statline(s)."
                if skipped:
                    note += (
                        f" Skipped {len(skipped)} template(s) that gained a "
                        "statline while the run was in progress."
                    )
                messages.success(request, note)
            except Exception as e:
                # run_materialise already recorded the run as FAILED
                logger.exception("Statline materialisation failed")
                messages.error(request, f"Materialisation failed: {e}")
                return HttpResponseRedirect(
                    reverse("admin:maintenance_materialise_statlines")
                )
            return HttpResponseRedirect(
                reverse("admin:maintenance_backfill_detail", args=[record.id])
            )

        entries = build_statline_plan()
        remaining_formats = build_format_plan()
        # A ListFighterStatOverride on a statline-less template is inert
        # today, but the moment the statline exists it outranks the legacy
        # override and the card changes. The display-preservation claim
        # rests on this being zero; the operator must see it if not.
        from n23.core.models.list import ListFighterStatOverride

        orphan_eav = ListFighterStatOverride.objects.filter(
            list_fighter__content_fighter__custom_statline__isnull=True
        ).count()
        ctx = {
            **self.each_context(request),
            "title": "Materialise statlines for legacy templates",
            "entries": entries,
            "all_blank": sum(1 for e in entries if e.blank_count == 12),
            # Surfaced so the operator sees un-normalised values before they
            # get copied verbatim into the new statlines.
            "remaining_formats": remaining_formats,
            "orphan_eav": orphan_eav,
        }
        return render(request, "admin/maintenance/materialise_statlines.html", ctx)

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

    def backfill_cancel_view(self, request, pk):
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


# Install on the live admin site. Order in INSTALLED_APPS must place this app
# AFTER gyrinx.analytics so the chain composes (analytics's routes survive).
admin.site.__class__ = MaintenanceAdminSite
