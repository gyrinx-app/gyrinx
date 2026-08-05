"""Notification inbox views and per-row / bulk actions.

All state (bucket, read/unread filter, type, search) is URL-driven via the query
string; the server renders the right subset. All mutations are POST + CSRF, with
one deliberate exception: the row title link is a GET "open" proxy that marks
the notification read before redirecting to its target — following a
notification is itself the act of reading it.
"""

import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views import generic
from django.views.decorators.http import require_POST

from gyrinx.http import safe_redirect
from n23.core.models.notification import Notification, NotificationType

VALID_BUCKETS = {"inbox", "archived"}
VALID_STATUSES = {"all", "unread", "read"}
VALID_TYPES = {value for value, _ in NotificationType.choices}
BULK_ACTIONS = {"mark_read", "mark_unread", "archive", "delete"}


def apply_inbox_filters(qs, params):
    """Apply the URL-driven inbox filters to a recipient-scoped queryset.

    ``params`` is a request GET/POST QueryDict. Returns the filtered queryset plus
    a dict of the resolved (validated) filter values for echoing back to the template.
    """
    bucket = params.get("bucket", "inbox")
    if bucket not in VALID_BUCKETS:
        bucket = "inbox"
    status = params.get("status", "all")
    if status not in VALID_STATUSES:
        status = "all"
    type_ = params.get("type", "")
    if type_ not in VALID_TYPES:
        type_ = ""
    q = (params.get("q") or "").strip()

    qs = qs.archived_bucket() if bucket == "archived" else qs.active()
    if status == "unread":
        qs = qs.filter(is_read=False)
    elif status == "read":
        qs = qs.filter(is_read=True)
    if type_:
        qs = qs.filter(notification_type=type_)
    if q:
        qs = qs.filter(Q(subject__icontains=q) | Q(content__icontains=q))

    resolved = {"bucket": bucket, "status": status, "type": type_, "q": q}
    return qs, resolved


class NotificationInboxView(LoginRequiredMixin, generic.ListView):
    """The user's notification inbox with URL-driven filters and pagination."""

    template_name = "core/notifications.html"
    context_object_name = "notifications"
    paginate_by = 25

    def get_queryset(self):
        # `target` / `scope` are prefetched, not select_related: they are generic
        # relations, so Django batches them one query per content type. Without
        # this, `target_url` dereferences each row's target individually and the
        # inbox issues a query per notification.
        qs = (
            Notification.objects.for_recipient(self.request.user)
            .select_related("sender")
            .prefetch_related("target", "scope")
        )
        qs, self._resolved_filters = apply_inbox_filters(qs, self.request.GET)
        return qs.order_by("-created")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self._resolved_filters)
        context["type_choices"] = NotificationType.choices
        # Unread count within the active (inbox) bucket, for the "mark all read" affordance.
        context["inbox_unread_count"] = Notification.objects.unread_count_for(
            self.request.user
        )
        return context


def _get_owned(request, id):
    """Fetch a live notification scoped to the requesting user (404 otherwise)."""
    return get_object_or_404(
        Notification, id=id, owner=request.user, deleted_at__isnull=True
    )


def _back(request):
    """Redirect back to the posted ``next`` (validated) or the inbox."""
    return safe_redirect(
        request,
        request.POST.get("next"),
        fallback_url=reverse("core:notifications"),
    )


@login_required
def notification_open(request, id):
    """Title-click proxy: mark the notification read, then follow its link.

    A GET mutation is acceptable here because it is owner-scoped, idempotent,
    and benign — the worst a forged or prefetched request can do is mark the
    user's own notification read. The redirect target is the server-derived
    ``target_url`` (never user input), falling back to the inbox for rows with
    no related object.
    """
    n = _get_owned(request, id)
    n.mark_read()
    return HttpResponseRedirect(n.target_url or reverse("core:notifications"))


@login_required
@require_POST
def notification_read(request, id):
    _get_owned(request, id).mark_read()
    return _back(request)


@login_required
@require_POST
def notification_unread(request, id):
    _get_owned(request, id).mark_unread()
    return _back(request)


@login_required
@require_POST
def notification_archive(request, id):
    _get_owned(request, id).archive()
    return _back(request)


@login_required
@require_POST
def notification_unarchive(request, id):
    _get_owned(request, id).unarchive()
    return _back(request)


@login_required
@require_POST
def notification_delete(request, id):
    n = _get_owned(request, id)
    n.deleted_at = timezone.now()
    n.save(update_fields=["deleted_at", "modified"])
    return _back(request)


@login_required
@require_POST
def notification_dismiss_banner(request, id):
    """In-page banner dismiss: persistent dismiss == mark read."""
    _get_owned(request, id).mark_read()
    return _back(request)


@login_required
@require_POST
def notifications_bulk(request):
    """Apply a bulk action to selected rows (``ids``) or the whole filter (``all=1``)."""
    action = request.POST.get("action")
    if action not in BULK_ACTIONS:
        messages.error(request, "Unknown action.")
        return _back(request)

    qs = Notification.objects.for_recipient(request.user)
    if request.POST.get("all") == "1":
        # Re-derive the same filtered set the user is looking at.
        qs, _ = apply_inbox_filters(qs, request.POST)
    else:
        # Coerce to UUIDs and drop anything malformed so a bad POST can't 500.
        ids = []
        for raw in request.POST.getlist("ids"):
            try:
                ids.append(uuid.UUID(str(raw)))
            except (ValueError, TypeError):
                continue
        if not ids:
            messages.info(request, "No notifications selected.")
            return _back(request)
        # Never act on already-deleted rows.
        qs = qs.filter(id__in=ids, deleted_at__isnull=True)

    now = timezone.now()
    if action == "mark_read":
        count = qs.filter(is_read=False).update(is_read=True, read_at=now, modified=now)
        messages.success(request, f"Marked {count} as read.")
    elif action == "mark_unread":
        count = qs.filter(is_read=True).update(
            is_read=False, read_at=None, modified=now
        )
        messages.success(request, f"Marked {count} as unread.")
    elif action == "archive":
        count = qs.filter(archived=False).update(
            archived=True, archived_at=now, modified=now
        )
        messages.success(request, f"Archived {count}.")
    elif action == "delete":
        count = qs.update(deleted_at=now, modified=now)
        messages.success(request, f"Deleted {count}.")

    return _back(request)
