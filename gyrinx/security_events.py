"""Small, bounded audit records for rejected HTTP requests."""

import hashlib
import hmac
import logging
import re
import sys
from uuid import uuid4

from django.conf import settings
from django.core import signals
from django.dispatch import receiver
from psycopg_pool import PoolTimeout

from gyrinx.client_ip import get_client_ip
from gyrinx.tracker import track

_TRACE_ID = re.compile(r"^[0-9a-fA-F]{32}$")


def request_route(request):
    """Use a route pattern, never a URL containing user input or query data."""
    match = getattr(request, "resolver_match", None)
    return match.route if match else "unresolved"


def request_id(request):
    if not hasattr(request, "_security_request_id"):
        request._security_request_id = uuid4().hex
    return request._security_request_id


def trace_id(request):
    raw = request.META.get("HTTP_X_CLOUD_TRACE_CONTEXT", "").split("/", 1)[0]
    return raw.lower() if _TRACE_ID.fullmatch(raw) else None


def login_target_fingerprint(request):
    """Link rejected attempts against one login without logging its identifier."""
    try:
        raw = request.POST.get("login")
    except Exception:
        # An invalid or oversized body must not turn a rejection into a 500.
        return None
    if not isinstance(raw, str):
        return None
    normalized = raw.strip().casefold()
    if not normalized or len(normalized) > 512:
        return None
    return hmac.new(
        settings.SECRET_KEY.encode(),
        b"login-target\0" + normalized.encode(),
        hashlib.sha256,
    ).hexdigest()


def record_security_event(
    request, action, reason, *, outcome="rejected", response_status=None
):
    user = getattr(request, "user", None)
    track(
        "security_request",
        action=action,
        outcome=outcome,
        reason=reason,
        response_status=response_status,
        route=request_route(request),
        method=request.method,
        actor_id=str(user.pk) if user is not None and user.is_authenticated else None,
        target_fingerprint=login_target_fingerprint(request)
        if action == "login"
        else None,
        client_ip=get_client_ip(request),
        request_id=request_id(request),
        trace_id=trace_id(request),
    )


def has_pool_timeout(exception):
    """Find a pool timeout behind Django's database exception wrapper."""
    seen = set()
    while exception is not None and id(exception) not in seen:
        if isinstance(exception, PoolTimeout):
            return True
        seen.add(id(exception))
        exception = exception.__cause__ or exception.__context__
    return False


def emit_pool_timeout(request):
    """Record a failed database checkout without exception or request contents."""
    track(
        "db_pool_timeout",
        route=request_route(request),
        request_id=request_id(request),
        trace_id=trace_id(request),
    )


class InvalidHostAuditHandler(logging.Handler):
    """Audit host validation failures even before application middleware runs."""

    def emit(self, record):
        request = getattr(record, "request", None)
        if request is not None:
            record_security_event(
                request, "request", "invalid_host", response_status=400
            )


@receiver(signals.got_request_exception)
def record_pool_timeout(sender, request, **kwargs):
    """Catch unhandled view and middleware timeouts at Django's 500 boundary."""
    if has_pool_timeout(sys.exc_info()[1]):
        emit_pool_timeout(request)
