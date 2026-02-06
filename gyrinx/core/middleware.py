"""
Custom middleware for the Gyrinx application.
"""

from django.core.exceptions import RequestDataTooBig
from django.http import HttpResponse
from django.shortcuts import render
from django.template import TemplateDoesNotExist, TemplateSyntaxError


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
