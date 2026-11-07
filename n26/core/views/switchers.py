"""Paged switcher results and search as JSON.

switcher_rows owns each list's contents and access checks.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from n26.core.navigation import switcher_rows

#: Cap search input before building the query.
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
