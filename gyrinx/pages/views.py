from django.conf import settings
from django.contrib.flatpages import views
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.shortcuts import get_current_site
from django.http import Http404, HttpResponsePermanentRedirect
from django.shortcuts import get_object_or_404

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
