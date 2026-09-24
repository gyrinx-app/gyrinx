"""The further pages of a switcher's list.

A switcher's page carries its first rows; this answers for the rest, and for
a search over all of them. What each list holds, and who may read it, is
``n26.core.navigation.switcher_rows``'s — this only reads the request and
writes the JSON.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from n26.core.navigation import switcher_rows

#: Longer than any name, and short enough that a pasted paragraph is
#: not turned into a query.
QUERY_LIMIT = 100


@login_required
@require_GET
def switcher_page(request, source):
    params = {
        key: value for key, value in request.GET.items() if key not in ("q", "offset")
    }
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except ValueError:
        offset = 0
    items, following = switcher_rows(
        request,
        source,
        params,
        query=request.GET.get("q", "")[:QUERY_LIMIT],
        offset=offset,
    )
    return JsonResponse(
        {
            "items": [{"label": item.label, "href": item.href} for item in items],
            "next": following,
        }
    )
