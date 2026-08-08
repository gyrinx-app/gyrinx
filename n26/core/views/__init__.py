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
from n26.core.views.equip import equip
from n26.core.views.gangs import create_gang, dashboard, gang_sheet, gangs
from n26.core.views.hire import hire_fighter
from n26.core.views.printing import print_gang, print_setup

__all__ = [
    "create_gang",
    "dashboard",
    "equip",
    "gang_sheet",
    "gangs",
    "hire_fighter",
    "preview_view",
    "print_gang",
    "print_setup",
]
