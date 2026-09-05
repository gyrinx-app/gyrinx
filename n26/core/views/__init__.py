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
from n26.core.views.campaigns import (
    add_asset,
    add_battle,
    add_gang,
    add_participant,
    answer_invitation,
    archive_campaign,
    campaign,
    campaign_log,
    campaigns,
    create_campaign,
    drop_asset,
    edit_campaign,
    grant_asset,
    remove_battle,
    remove_gang,
    remove_participant,
    take_away_asset,
)
from n26.core.views.changelog import changelog, changelog_entry
from n26.core.views.choose import choose
from n26.core.views.edit import edit_fighter
from n26.core.views.equip import equip, equip_gang
from n26.core.views.gangs import (
    create_gang,
    dashboard,
    delete_fighter,
    delete_gang,
    edit_gang,
    gang_founding_action,
    gang_lore,
    gang_notes,
    gang_sheet,
    gang_trade_points,
    gangs,
    refund_fighter,
    rename_fighter,
)
from n26.core.views.hire import hire_card, hire_fighter
from n26.core.views.history import gang_history
from n26.core.views.options import fighter_options
from n26.core.views.owned import (
    accessorise_assignment,
    reassign_assignment,
    rechoose_assignment,
    refund_assignment,
    remove_assignment,
    sell_assignment,
    tally_counter,
)
from n26.core.views.printing import print_gang, print_setup
from n26.core.views.skills import skills

__all__ = [
    "accessorise_assignment",
    "campaign",
    "campaign_log",
    "campaigns",
    "changelog",
    "changelog_entry",
    "choose",
    "create_campaign",
    "create_gang",
    "dashboard",
    "add_battle",
    "add_participant",
    "answer_invitation",
    "add_gang",
    "add_asset",
    "drop_asset",
    "grant_asset",
    "take_away_asset",
    "archive_campaign",
    "delete_fighter",
    "delete_gang",
    "edit_campaign",
    "remove_battle",
    "remove_gang",
    "remove_participant",
    "edit_fighter",
    "edit_gang",
    "equip",
    "equip_gang",
    "fighter_options",
    "gang_founding_action",
    "gang_history",
    "gang_lore",
    "gang_notes",
    "gang_sheet",
    "gang_trade_points",
    "gangs",
    "hire_card",
    "hire_fighter",
    "skills",
    "preview_view",
    "print_gang",
    "print_setup",
    "reassign_assignment",
    "rechoose_assignment",
    "refund_assignment",
    "refund_fighter",
    "remove_assignment",
    "rename_fighter",
    "sell_assignment",
    "tally_counter",
]
