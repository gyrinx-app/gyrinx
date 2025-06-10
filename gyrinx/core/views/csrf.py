from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
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

    # Validate the referer URL
    if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts={request.get_host()}
    ):
        # Redirect back to the form page
        return HttpResponseRedirect(referer)

    # If no valid referer, redirect to home page
    return HttpResponseRedirect(reverse("core:index"))
