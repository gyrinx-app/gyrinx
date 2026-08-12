"""The edition's player-facing views, one module per screen.

Split by screen rather than kept in one file: every feature added lands
in exactly one of these, so two people can build two screens without
meeting in the same file. The names mirror the pipeline they draw on —
``views.hire`` is the web face of ``core.hire``, ``views.equip`` of
``core.browse`` — so where a view lives is a thing to guess rather than
remember.

Re-exported here because ``n26/urls.py`` reads ``views.dashboard`` and
friends off the package: the split is invisible to callers, which is
what makes it a move rather than a change.
"""

from n26.core.views.api import preview_view
from n26.core.views.choose import choose
from n26.core.views.edit import edit_fighter
from n26.core.views.equip import equip
from n26.core.views.gangs import (
    create_gang,
    dashboard,
    delete_fighter,
    delete_gang,
    gang_sheet,
    gangs,
    refund_fighter,
    rename_fighter,
)
from n26.core.views.hire import hire_fighter
from n26.core.views.learn import learn
from n26.core.views.owned import (
    reassign_assignment,
    refund_assignment,
    remove_assignment,
    sell_assignment,
)
from n26.core.views.printing import print_gang, print_setup

__all__ = [
    "choose",
    "create_gang",
    "dashboard",
    "delete_fighter",
    "delete_gang",
    "edit_fighter",
    "equip",
    "gang_sheet",
    "gangs",
    "hire_fighter",
    "learn",
    "preview_view",
    "print_gang",
    "print_setup",
    "reassign_assignment",
    "refund_assignment",
    "refund_fighter",
    "remove_assignment",
    "rename_fighter",
    "sell_assignment",
]
