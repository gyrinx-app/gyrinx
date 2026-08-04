"""Edition debug routes, served under the /n23/ prefix with the rest of n23.

The platform's debug routes (test plans, design system) stay at the root in
gyrinx/urls.py — they are about the tooling, not the game.
"""

from django.urls import path

from n23.core.views import debug as debug_views
from n23.core.views import print_lab as print_lab_views

patterns = [
    path(
        "_debug/list/<uuid:list_id>/actions/",
        debug_views.debug_list_actions,
        name="debug_list_actions",
    ),
    path(
        "_debug/list/<uuid:list_id>/balance-sheet/",
        debug_views.debug_list_balance_sheet,
        name="debug_list_balance_sheet",
    ),
    path("_debug/print-lab/", print_lab_views.print_lab, name="debug_print_lab"),
    path(
        "_debug/print-lab/sheet/",
        print_lab_views.print_lab_sheet,
        name="debug_print_lab_sheet",
    ),
]
