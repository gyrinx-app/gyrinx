"""Small, bounded audit records for rejected HTTP requests."""

import re
from uuid import uuid4

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
        client_ip=get_client_ip(request),
        request_id=request_id(request),
        trace_id=trace_id(request),
    )
