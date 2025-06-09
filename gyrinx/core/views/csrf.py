from django.contrib import messages
from django.http import HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def csrf_failure(request, reason=""):
    """
    Custom view to handle CSRF failures by redirecting back to the form
    with an error message instead of showing a 403 page.
    """
    # Add a user-friendly error message
    messages.error(
        request,
        "Your session has expired. Please try again. The form has been refreshed with a new security token.",
    )

    # Get the referer URL to redirect back to the form
    referer = request.META.get("HTTP_REFERER")

    if referer:
        # Redirect back to the form page
        return HttpResponseRedirect(referer)

    # If no referer, redirect to home page
    return HttpResponseRedirect("/")