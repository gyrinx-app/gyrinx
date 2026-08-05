"""Platform middleware — edition-agnostic request handling.

``ImpersonationMiddleware`` deliberately still lives in ``n23.core.middleware``:
it writes ``ImpersonationLog``, which is still an edition model. It moves here
once that model does.
"""

from django.core.exceptions import RequestDataTooBig
from django.http import HttpResponse
from django.shortcuts import render
from django.template import TemplateDoesNotExist, TemplateSyntaxError


class ClearLoggingRequestMiddleware:
    """
    Clear google.cloud.logging's per-thread request reference after each
    response.

    The upstream RequestMiddleware stores the request in a thread-local and
    never removes it. Under a threaded server (gunicorn gthread) threads are
    reused, so each pool thread would otherwise pin its most recent request —
    user, session, any in-memory upload buffer — indefinitely, and log records
    emitted on that thread outside a request would pick up the stale request
    for trace correlation. Must sit above RequestMiddleware in MIDDLEWARE so
    this clear runs after the response is fully generated.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        finally:
            from google.cloud.logging_v2.handlers.middleware.request import (
                _thread_locals,
            )

            _thread_locals.request = None


class RequestSizeExceptionMiddleware:
    """
    Middleware to catch RequestDataTooBig exceptions and return a 400 response.

    This ensures that overly large requests are properly handled as client errors
    (400 Bad Request) instead of server errors (500 Internal Server Error).

    The issue is that Django's default exception handling doesn't always properly
    convert RequestDataTooBig (a SuspiciousOperation) to a 400 response,
    especially when the exception is raised during middleware processing
    (like CSRF middleware) before the view is called.

    See: https://github.com/gyrinx-app/gyrinx/issues/1097
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        """
        Process exceptions raised during request handling.

        If the exception is RequestDataTooBig, return a 400 Bad Request response
        instead of letting it bubble up as a 500 error.
        """
        if isinstance(exception, RequestDataTooBig):
            context = {
                "error_code": 400,
                "error_message": "Request Too Large",
                "error_description": (
                    "The request body is too large. "
                    "Please reduce the size of your upload."
                ),
            }
            try:
                return render(request, "errors/error.html", context, status=400)
            except (TemplateDoesNotExist, TemplateSyntaxError):
                # Fallback to simple response if template rendering fails
                return HttpResponse(
                    "400 Bad Request: The request body is too large.",
                    status=400,
                    content_type="text/plain",
                )
        return None
