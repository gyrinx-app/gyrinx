"""
List views package.

Provides list-related views: CRUD, attributes, invitations.
For fighter views, import from gyrinx.core.views.fighter instead.
"""

from gyrinx.core.views import make_query_params_str

# List views
from gyrinx.core.views.list.attributes import edit_list_attribute
from gyrinx.core.views.list.common import get_clean_list_or_404
from gyrinx.core.views.list.invitations import (
    accept_invitation,
    decline_invitation,
    list_invitations,
)
from gyrinx.core.views.list.views import (
    ListAboutDetailView,
    ListCampaignClonesView,
    ListDetailView,
    ListPerformanceView,
    ListPrintView,
    ListsListView,
    archive_list,
    clone_list,
    edit_list,
    edit_list_credits,
    new_list,
    refresh_list_cost,
    show_stash,
)

__all__ = [
    # common.py
    "get_clean_list_or_404",
    # attributes.py
    "edit_list_attribute",
    # invitations.py
    "list_invitations",
    "accept_invitation",
    "decline_invitation",
    # views.py (list views)
    "ListsListView",
    "ListDetailView",
    "ListPerformanceView",
    "ListAboutDetailView",
    "ListPrintView",
    "ListCampaignClonesView",
    "new_list",
    "edit_list",
    "edit_list_credits",
    "archive_list",
    "show_stash",
    "refresh_list_cost",
    "clone_list",
    "make_query_params_str",
]
