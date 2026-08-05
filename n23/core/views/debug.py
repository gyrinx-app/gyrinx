"""Edition debug views."""

from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from n23.core.cost.balance_sheet import build_balance_sheet
from n23.core.models import List


def _get_debug_list_or_404(request, list_id):
    """Fetch a list for the internal debug views.

    Staff may view any list in any environment — these views double as
    production support tooling. Everyone else gets them only in development,
    and only for lists they own; anonymous users and non-owners get a 404
    rather than another list's data. (AnonymousUser has is_staff=False, so
    the staff branch never matches logged-out requests.)
    """
    if request.user.is_staff:
        return get_object_or_404(List, id=list_id)
    if settings.DEBUG and request.user.is_authenticated:
        return get_object_or_404(List, id=list_id, owner=request.user)
    raise Http404("List not found")


def debug_list_balance_sheet(request, list_id):
    """Itemised cost balance sheet for a list, with reconciliation problems.

    The read-only companion to debug_list_actions: decomposes every fighter
    and assignment into priced component lines, compares computed values with
    the caches, and checks the credits ledger and action-chain continuity.
    Part of the cost-pinning programme (#1826).
    """
    lst = _get_debug_list_or_404(request, list_id)

    sheet = build_balance_sheet(lst)
    problems = sheet.reconcile()

    return render(
        request,
        "core/debug/list_balance_sheet.html",
        {
            "list": lst,
            "sheet": sheet,
            "problems": problems,
            "all_fighters": sheet.all_fighters,
        },
    )


def debug_list_actions(request, list_id):
    """Display all actions for a list, sorted newest first."""
    lst = _get_debug_list_or_404(request, list_id)
    actions = lst.actions.select_related("user", "list_fighter").order_by("-created")

    return render(
        request,
        "core/debug/list_actions.html",
        {"list": lst, "actions": actions},
    )
