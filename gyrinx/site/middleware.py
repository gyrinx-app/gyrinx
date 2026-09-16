"""HTTP admission and read-only notices for registered write scopes."""

import logging
from types import SimpleNamespace

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.urls import Resolver404, resolve
from django.utils.html import escape

from gyrinx.site.models import WritePause
from gyrinx.site.write_pause import (
    WritesPaused,
    pause_status,
    registered_write_scopes,
    request_gate,
)

logger = logging.getLogger(__name__)


def _scope_for_request(request):
    registrations = registered_write_scopes()
    for registration in registrations:
        if any(
            request.path_info.startswith(prefix)
            for prefix in registration.path_prefixes
        ):
            return registration.slug
    try:
        match = resolve(request.path_info)
    except Resolver404:
        return None
    explicit = getattr(match.func, "write_scope", None)
    if explicit:
        return explicit
    model_admin = getattr(match.func, "model_admin", None)
    app_label = getattr(getattr(model_admin, "opts", None), "app_label", None)
    for registration in registrations:
        if app_label in registration.admin_app_labels:
            return registration.slug
    return None


def _paused_response(request, pause):
    reason = pause.reason or "Maintenance is in progress."
    if request.headers.get("HX-Request"):
        response = HttpResponse(
            f'<div class="alert alert-warning" role="alert">{escape(reason)}</div>',
            status=503,
        )
        # HTMX does not swap error responses by default. Reload as a safe GET so
        # the page stays intact and shows the read-only notice from its layout.
        response["HX-Refresh"] = "true"
    else:
        response = HttpResponse(
            f"Changes are temporarily paused: {reason}",
            status=503,
            content_type="text/plain",
        )
    response["Retry-After"] = "30"
    return response


def _unavailable_pause():
    return SimpleNamespace(
        state=WritePause.State.PAUSED,
        State=WritePause.State,
        reason="Changes are temporarily unavailable while maintenance starts.",
    )


class WritePauseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        scope = _scope_for_request(request)
        request.write_pause = None
        if not scope:
            return self.get_response(request)
        try:
            if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                with request_gate(scope) as admission:
                    request.write_pause = admission.pause
                    if not admission.allowed:
                        logger.info(
                            "HTTP write deferred by write pause",
                            extra={
                                "write_scope": scope,
                                "request_method": request.method,
                                "request_path": request.path_info,
                                "pause_generation": admission.pause.generation,
                            },
                        )
                        return _paused_response(request, admission.pause)
                    return self.get_response(request)
            request.write_pause = pause_status(scope)
            return self.get_response(request)
        except ImproperlyConfigured:
            pause = _unavailable_pause()
            request.write_pause = pause
            if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                return _paused_response(request, pause)
            return self.get_response(request)
        except WritesPaused as exc:
            return _paused_response(request, type("Pause", (), {"reason": str(exc)})())

    def process_exception(self, request, exception):
        # Django converts view exceptions before they return through __call__.
        # This hook keeps a guarded service write friendly even on a safe-method
        # endpoint, while leaving unrelated exceptions to normal error handling.
        if isinstance(exception, WritesPaused):
            return _paused_response(
                request, type("Pause", (), {"reason": str(exception)})()
            )
        return None
