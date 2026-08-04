"""Admin impersonation start/stop views.

See :mod:`n23.core.impersonation` and
:class:`n23.core.middleware.ImpersonationMiddleware` for how the overlay works.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from n23.core.impersonation import (
    IMPERSONATE_KEY,
    IMPERSONATE_LOG_KEY,
    IMPERSONATE_SESSION_KEYS,
    IMPERSONATE_STARTED_KEY,
    can_impersonate,
    can_impersonate_target,
)
from n23.core.models import ImpersonationLog
from n23.core.utils import safe_redirect


@login_required
@require_POST
def start_impersonation(request, user_id):
    """Begin impersonating the user with id ``user_id`` (superuser only).

    ``request.user`` here is the real admin — the middleware never swaps on this
    request because no overlay is active yet.
    """
    # No nesting: if an overlay is already active, refuse. Checked first because
    # while impersonating ``request.user`` is the target, not the admin.
    if request.session.get(IMPERSONATE_KEY):
        messages.error(request, "You are already impersonating a user.")
        return safe_redirect(request, request.POST.get("next"))

    if not can_impersonate(request.user):
        return HttpResponseForbidden("You are not allowed to impersonate users.")

    target = get_object_or_404(get_user_model(), pk=user_id)

    if not can_impersonate_target(request.user, target):
        return HttpResponseForbidden("You cannot impersonate this user.")

    log = ImpersonationLog.objects.create(owner=request.user, target=target)
    request.session[IMPERSONATE_KEY] = target.pk
    request.session[IMPERSONATE_STARTED_KEY] = timezone.now().isoformat()
    request.session[IMPERSONATE_LOG_KEY] = str(log.pk)

    messages.warning(
        request,
        f"You are now impersonating {target.username}. "
        "Everything you do will be recorded as that user.",
    )
    return safe_redirect(request, request.POST.get("next"), fallback_url="/")


@login_required
@require_POST
def stop_impersonation(request):
    """Stop impersonating and return to the admin's own session.

    Works regardless of the overlay: while impersonating ``request.user`` is the
    target, but this view only reads and clears the session, so the next request
    resolves back to the admin.
    """
    was_impersonating = bool(request.session.get(IMPERSONATE_KEY))
    log_id = request.session.get(IMPERSONATE_LOG_KEY)
    if log_id:
        ImpersonationLog.objects.filter(pk=log_id, ended_at__isnull=True).update(
            ended_at=timezone.now(),
            ended_reason=ImpersonationLog.EndedReason.MANUAL,
        )
    for key in IMPERSONATE_SESSION_KEYS:
        request.session.pop(key, None)

    if was_impersonating:
        messages.success(request, "You have stopped impersonating.")
    return safe_redirect(request, request.POST.get("next"), fallback_url="/")
