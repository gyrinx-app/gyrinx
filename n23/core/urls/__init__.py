from django.http import HttpResponsePermanentRedirect
from django.urls import include, path, re_path
from django.views.generic import RedirectView

from .campaign import patterns as campaign_patterns
from .debug import patterns as debug_patterns
from .fighter import patterns as fighter_patterns
from .list import patterns as list_patterns
from .misc import patterns as misc_patterns
from .notification import patterns as notification_patterns
from .pack import patterns as pack_patterns

# Name new URLs like this:
# * Transaction pages: noun[-noun]-verb
# * Index pages should pluralize the noun: noun[-noun]s
# * Detail pages should be singular: noun[-noun]
#
# This module is the includer for the per-domain url submodules. Each submodule
# exports a plain ``patterns`` list (no ``app_name``).

app_name = "core"

# Edition routes — everything that is about playing Necromunda 2023. These live
# under /n23/ so a second edition can own its own prefix. They are included as a
# plain list, NOT a nested namespace, so every route name still resolves as
# ``core:...`` and no reverse() or {% url %} call site changes.
EDITION_PREFIX = "n23/"
edition_patterns = (
    list_patterns
    + fighter_patterns
    + campaign_patterns
    + pack_patterns
    + debug_patterns
)

# The seven top-level prefixes those 234 routes occupy. Old links — bookmarks,
# Discord posts, search results — are permanently redirected to the prefixed
# path, tail and query string preserved, rather than 404ing.
LEGACY_PREFIXES = ["list", "lists", "campaign", "campaigns", "battle", "pack", "packs"]


class _Redirect308(HttpResponsePermanentRedirect):
    """308 rather than 301.

    A 301 lets the browser re-issue the request as a GET, dropping the method
    and body. These redirects catch every verb, so somebody who still has a
    pre-deploy page open and submits its form would have the POST silently
    turned into a GET and their edit lost. 308 preserves both.
    """

    status_code = 308


class LegacyEditionRedirect(RedirectView):
    permanent = True
    query_string = True
    response_class = _Redirect308

    def get(self, request, *args, **kwargs):
        return self.response_class(self.get_redirect_url(*args, **kwargs))


legacy_redirects = [
    re_path(
        r"^(?P<rest>(?:%s)(?:/.*)?)$" % "|".join(LEGACY_PREFIXES),  # noqa: UP031
        LegacyEditionRedirect.as_view(url=f"/{EDITION_PREFIX}%(rest)s"),
    )
]

# Platform routes stay at the root: the index, account pages, badges, dice,
# impersonation, the TinyMCE upload endpoint, banners and notifications.
urlpatterns = (
    misc_patterns
    + notification_patterns
    + [path(EDITION_PREFIX, include(edition_patterns))]
    + legacy_redirects
)
