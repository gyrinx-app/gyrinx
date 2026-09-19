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

# Crawl policy. Amazonbot alone was ~70% of page traffic (2026-07-28) crawling
# every fighter page of every public list; it feeds Amazon product answers and
# brings no users, so it is excluded entirely. Bytespider (ByteDance) likewise.
# For everyone else (Googlebot, bingbot, ...) the list overview pages carry the
# search value — the per-fighter detail pages are crawl noise, so they are
# disallowed for all agents. The print views are the most expensive pages on
# the site and have no business being indexed.
#
# A gang sheet in the n26 edition is readable by whoever holds its address —
# that is what makes a roster shareable — so /n26/gangs/ is disallowed whole:
# the sheets, their print views, and the index. Somebody else's roster is not
# search material, and the print pages are as expensive here as they are there.
#
# These paths carry the /n23/ edition prefix. They MUST be kept in step with
# n23/core/urls/__init__.py: when the edition moved under /n23/ in #2110 these
# rules silently stopped matching, every fighter and print page became
# crawlable, and the resulting crawl took the site down. The test below asserts
# each pattern resolves to a real view rather than just checking the text.
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
    # This is copied from django.contrib.flatpages.views.flatpage
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
