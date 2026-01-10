"""
Campaign views package.

This package provides all campaign-related views organized by functionality.
"""

from gyrinx.core.views.campaign.actions import (
    CampaignActionList,
    campaign_action_outcome,
    campaign_log_action,
)
from gyrinx.core.views.campaign.assets import (
    campaign_asset_edit,
    campaign_asset_new,
    campaign_asset_remove,
    campaign_asset_transfer,
    campaign_asset_type_edit,
    campaign_asset_type_new,
    campaign_asset_type_remove,
    campaign_assets,
)
from gyrinx.core.views.campaign.battles import campaign_battles
from gyrinx.core.views.campaign.captured import (
    campaign_captured_fighters,
    fighter_release,
    fighter_return_to_owner,
    fighter_sell_to_guilders,
)
from gyrinx.core.views.campaign.common import (
    ensure_campaign_list_resources,
    get_campaign_resource_types_with_resources,
)
from gyrinx.core.views.campaign.copy import campaign_copy_from, campaign_copy_to
from gyrinx.core.views.campaign.crud import edit_campaign, new_campaign
from gyrinx.core.views.campaign.lifecycle import (
    archive_campaign,
    end_campaign,
    reopen_campaign,
    start_campaign,
)
from gyrinx.core.views.campaign.lists import campaign_add_lists, campaign_remove_list
from gyrinx.core.views.campaign.resources import (
    campaign_resource_modify,
    campaign_resource_type_edit,
    campaign_resource_type_new,
    campaign_resource_type_remove,
    campaign_resources,
)
from gyrinx.core.views.campaign.sub_assets import (
    campaign_sub_asset_edit,
    campaign_sub_asset_new,
    campaign_sub_asset_remove,
)
from gyrinx.core.views.campaign.views import CampaignDetailView, Campaigns

__all__ = [
    # views.py
    "Campaigns",
    "CampaignDetailView",
    # crud.py
    "new_campaign",
    "edit_campaign",
    # lists.py
    "campaign_add_lists",
    "campaign_remove_list",
    # lifecycle.py
    "start_campaign",
    "end_campaign",
    "reopen_campaign",
    "archive_campaign",
    # actions.py
    "campaign_log_action",
    "campaign_action_outcome",
    "CampaignActionList",
    # assets.py
    "campaign_assets",
    "campaign_asset_type_new",
    "campaign_asset_type_edit",
    "campaign_asset_type_remove",
    "campaign_asset_new",
    "campaign_asset_edit",
    "campaign_asset_transfer",
    "campaign_asset_remove",
    # resources.py
    "campaign_resources",
    "campaign_resource_type_new",
    "campaign_resource_type_edit",
    "campaign_resource_type_remove",
    "campaign_resource_modify",
    # captured.py
    "campaign_captured_fighters",
    "fighter_sell_to_guilders",
    "fighter_return_to_owner",
    "fighter_release",
    # battles.py
    "campaign_battles",
    # sub_assets.py
    "campaign_sub_asset_new",
    "campaign_sub_asset_edit",
    "campaign_sub_asset_remove",
    # copy.py
    "campaign_copy_from",
    "campaign_copy_to",
    # common.py
    "ensure_campaign_list_resources",
    "get_campaign_resource_types_with_resources",
]
