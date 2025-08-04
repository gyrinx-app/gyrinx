from django.conf import settings
from django.contrib.flatpages import views
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.shortcuts import get_current_site
from django.http import (
    Http404,
    HttpResponsePermanentRedirect,
)
from django.shortcuts import get_object_or_404, render

from gyrinx.pages.models import FlatPageVisibility


def flatpage(request, url):
    # This is copied from django.contrib.flatpages.views.flatpage
    if not url.startswith("/"):
        url = "/" + url
    site_id = get_current_site(request).id
    try:
        f = get_object_or_404(FlatPage, url=url, sites=site_id)
    except Http404:
        if not url.endswith("/") and settings.APPEND_SLASH:
            url += "/"
            f = get_object_or_404(FlatPage, url=url, sites=site_id)
            return HttpResponsePermanentRedirect("%s/" % request.path)
        else:
            raise

    # This is the new part
    # Check if the page is visible to the user
    # If the user is not authenticated, raise a 404
    visibility = FlatPageVisibility.objects.filter(page=f)
    if visibility.exists():
        if not request.user.is_authenticated:
            raise Http404
        groups = request.user.groups.all()
        if not visibility.filter(groups__in=groups).exists():
            raise Http404

    return views.render_flatpage(request, f)


def error_400(request, exception=None):
    context = {
        "error_code": 400,
        "error_message": "Bad Request",
        "error_description": "The request could not be understood by the server.",
    }
    return render(request, "errors/error.html", context, status=400)


def error_403(request, exception=None):
    context = {
        "error_code": 403,
        "error_message": "Forbidden",
        "error_description": "You don't have permission to access this resource.",
    }
    return render(request, "errors/error.html", context, status=403)


def error_404(request, exception=None):
    return render(request, "404.html", status=404)


def error_500(request):
    # Django automatically logs exceptions through django.request logger
    # See: https://docs.djangoproject.com/en/5.2/howto/error-reporting/

    # Generate a unique error ID for tracing
    import uuid

    error_id = str(uuid.uuid4())

    # Log the error ID so we can correlate with user reports
    import logging

    logger = logging.getLogger("django.request")
    logger.error(
        f"Error ID: {error_id} - User can reference this when reporting issues"
    )

    context = {
        "error_id": error_id,
    }
    return render(request, "500.html", context, status=500)
