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
from django.http import HttpResponseRedirect, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.timesince import timesince
from django.views import generic
from django.views.decorators.http import require_POST

from gyrinx.accounts.rich_text import rich_text_nodes
from gyrinx.http import safe_redirect
from gyrinx.site.models import Notification, NotificationType

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

    template_name = "account/notifications.html"
    context_object_name = "notifications"
    paginate_by = 25

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get("Accept") == "application/json":
            return JsonResponse(context["notification_inbox"])
        return super().render_to_response(context, **response_kwargs)

    def get_queryset(self):
        # `target` / `scope` are prefetched, not select_related: they are generic
        # relations, so Django batches them one query per content type. Without
        # this, `target_url` dereferences each row's target individually and the
        # inbox issues a query per notification.
        #
        # A row whose model renders its key differently from the uuid column
        # comes back unresolved from this, so the list decides whether to draw
        # a link from the stored key and leaves resolving it to the open view.
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
        query = self.request.GET.copy()

        def page_url(number):
            query["page"] = number
            return f"{reverse('core:notifications')}?{query.urlencode()}"

        page = context["page_obj"]
        context["account_tab"] = "notifications"
        context["notification_inbox"] = {
            "rows": [
                {
                    "id": str(n.id),
                    "subject": n.subject,
                    "content": rich_text_nodes(n.content),
                    "sender": n.sender_label,
                    "system": n.is_system,
                    "created": n.created.isoformat(),
                    "age": f"{timesince(n.created)} ago",
                    "type": n.get_notification_type_display(),
                    "read": n.is_read,
                    "archived": n.archived,
                    "openUrl": reverse("core:notification-open", args=[n.id])
                    if n.target_object_id or n.scope_object_id
                    else "",
                    "actions": {
                        key: reverse(f"core:notification-{key}", args=[n.id])
                        for key in ("read", "unread", "archive", "unarchive", "delete")
                    },
                }
                for n in context["notifications"]
            ],
            "filters": self._resolved_filters,
            "typeChoices": [
                {"value": value, "label": label}
                for value, label in NotificationType.choices
            ],
            "csrfToken": get_token(self.request),
            "inboxUrl": reverse("core:notifications"),
            "bulkUrl": reverse("core:notifications-bulk"),
            "returnUrl": self.request.get_full_path(),
            "unreadCount": context["inbox_unread_count"],
            "page": page.number,
            "pages": page.paginator.num_pages,
            "previousUrl": page_url(page.previous_page_number())
            if page.has_previous()
            else "",
            "nextUrl": page_url(page.next_page_number()) if page.has_next() else "",
        }
        return context


def _get_owned(request, id):
    """Fetch a live notification scoped to the requesting user (404 otherwise)."""
    return get_object_or_404(
        Notification, id=id, owner=request.user, deleted_at__isnull=True
    )


def _back(request):
    """Redirect back to the posted ``next`` (validated) or the inbox."""
    if request.headers.get("Accept") == "application/json":
        return JsonResponse({"ok": True})
    return safe_redirect(
        request,
        request.POST.get("next"),
        fallback_url=reverse("core:notifications"),
    )


def _bulk_message(request, level, text):
    if request.headers.get("Accept") != "application/json":
        messages.add_message(request, level, text)


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
        if request.headers.get("Accept") == "application/json":
            return JsonResponse({"ok": False, "error": "Unknown action."}, status=400)
        _bulk_message(request, messages.ERROR, "Unknown action.")
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
            except ValueError, TypeError:
                continue
        if not ids:
            _bulk_message(request, messages.INFO, "No notifications selected.")
            return _back(request)
        # Never act on already-deleted rows.
        qs = qs.filter(id__in=ids, deleted_at__isnull=True)

    now = timezone.now()
    if action == "mark_read":
        count = qs.filter(is_read=False).update(is_read=True, read_at=now, modified=now)
        _bulk_message(request, messages.SUCCESS, f"Marked {count} as read.")
    elif action == "mark_unread":
        count = qs.filter(is_read=True).update(
            is_read=False, read_at=None, modified=now
        )
        _bulk_message(request, messages.SUCCESS, f"Marked {count} as unread.")
    elif action == "archive":
        count = qs.filter(archived=False).update(
            archived=True, archived_at=now, modified=now
        )
        _bulk_message(request, messages.SUCCESS, f"Archived {count}.")
    elif action == "delete":
        count = qs.update(deleted_at=now, modified=now)
        _bulk_message(request, messages.SUCCESS, f"Deleted {count}.")

    return _back(request)
