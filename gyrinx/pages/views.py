from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.contrib.sites.shortcuts import get_current_site
from django.http import (
    Http404,
    HttpResponse,
    HttpResponsePermanentRedirect,
)
from django.shortcuts import get_object_or_404, render
from django.template import loader
from django.utils.functional import SimpleLazyObject
from django.utils.safestring import mark_safe
from django.views.decorators.csrf import csrf_protect

from gyrinx.pages.access import accessible_flatpages
from gyrinx.pages.presentation import build_flatpage_presentation

# Exclude Amazonbot and Bytespider, and discourage indexing fighter details,
# print views and shared N26 gang pages. Keep the paths aligned with
# edition URL configuration; test_robots.py checks that patterns resolve.
ROBOTS_TXT = """\
User-agent: Amazonbot
Disallow: /

User-agent: Bytespider
Disallow: /

User-agent: *
Disallow: /n23/list/*/fighter/
Disallow: /n23/list/*/print
Disallow: /n23/list/*/print/
Disallow: /n26/gangs/
Disallow: /accounts/
Disallow: /admin/
"""


def robots_txt(request):
    return HttpResponse(ROBOTS_TXT, content_type="text/plain")


def flatpage(request, url):
    if not url.startswith("/"):
        url = "/" + url
    site_id = get_current_site(request).id
    try:
        f = get_object_or_404(
            accessible_flatpages(site_id=site_id, user=request.user), url=url
        )
    except Http404:
        if not url.endswith("/") and settings.APPEND_SLASH:
            url += "/"
            get_object_or_404(
                accessible_flatpages(site_id=site_id, user=request.user), url=url
            )
            return HttpResponsePermanentRedirect(f"{request.path}/")
        else:
            raise

    template = None
    custom_template = False
    if f.template_name:
        selected = loader.select_template((f.template_name, "flatpages/default.html"))
        template = selected
        custom_template = selected.template.name != "flatpages/default.html"
    return render_flatpage(
        request, f, site_id=site_id, template=template, custom_template=custom_template
    )


@csrf_protect
def render_flatpage(request, page, *, site_id, template=None, custom_template=False):
    """Render an accessible page while preserving Django's flatpage contract."""
    if page.registration_required and not request.user.is_authenticated:
        return redirect_to_login(request.path)

    template = template or loader.get_template("flatpages/default.html")

    if custom_template:
        # Django's custom flatpage templates receive trusted editor HTML.
        page.title = mark_safe(page.title)  # nosec B703 B308
        page.content = mark_safe(page.content)  # nosec B703 B308

    presentation = SimpleLazyObject(
        lambda: build_flatpage_presentation(
            page=page, site_id=site_id, user=request.user
        )
    )
    return HttpResponse(
        template.render({"flatpage": page, "presentation": presentation}, request)
    )


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

    import uuid

    error_id = str(uuid.uuid4())

    # Log the displayed ID so a user report can be matched to server logs.
    import logging

    logger = logging.getLogger("django.request")
    logger.error(
        f"Error ID: {error_id} - User can reference this when reporting issues"
    )

    context = {
        "error_id": error_id,
    }
    return render(request, "500.html", context, status=500)
